#!/usr/bin/env python
# coding: utf-8
import os
# In[2]:


# lab2_fall_detection.py — VERSION NORMALISÉE
import cv2
import numpy as np
import time
from ultralytics import YOLO
from collections import deque
import json  # ← NOUVEAU

# ─────────────────────────────────────────────────────────────
# CONFIG (inchangé)
# ─────────────────────────────────────────────────────────────
CONF_THRESHOLD = 0.35
MIN_HEIGHT = 40
FLOW_SCALE = 0.4
FLOW_SMOOTHING = 0.6
LYING_RATIO_THRESH = 0.60
LYING_VSPAN_THRESH = 0.38
CONF_MIN = 0.25
VELOCITY_THRESH = 180
VSPAN_DROP_THRESH = 0.28
CONFIRM_FALL_TIME = 1.0
CONFIRM_LIE_TIME = 2.0
ALERT_TIME = 4.0
LOST_TIMEOUT = 4.0
IOU_THRESH = 0.20
MAX_CENTROID_DIST = 180
HISTORY = 10
ALERT_COOLDOWN = 4.0

# ─────────────────────────────────────────────────────────────
# NOUVEAU : Fonctions de normalisation de sortie
# ─────────────────────────────────────────────────────────────
def get_fall_score(persons):
    """
    Calcule un score 0-100 basé sur l'état des personnes détectées.
    - STANDING : 0-20
    - UNSTABLE : 30-50
    - FALL/LYING : 70-100 (selon alert_timer)
    """
    if not persons:
        return 0, 1.0
    
    max_score = 0
    max_conf = 0.0
    
    for p in persons:
        if p.status == "STANDING":
            score = 10
        elif p.status == "UNSTABLE":
            score = 40
        elif p.status in ("FALL", "LYING"):
            # Score augmente avec alert_timer (0→4s = 70→100)
            score = 70 + min(p.alert_timer / ALERT_TIME * 30, 30)
        else:
            score = 20
        
        # Confiance basée sur la stabilité du statut
        conf = min(0.5 + p.frames * 0.02, 1.0) if p.status != "STANDING" else 0.9
        
        if score > max_score:
            max_score = score
            max_conf = conf
    
    return min(max_score, 100), round(max_conf, 2)


def get_output_dict(persons, scene_dy):
    score, conf = get_fall_score(persons)
    
    # Détails pour debug
    details = {
        "tracked_persons": len(persons),
        "statuses": {p.id: p.status for p in persons},
        "scene_motion_y": round(scene_dy, 1)
    }
    
    return {
        "module": "fall",
        "score": score,
        "confidence": conf,
        "details": details,
        "timestamp": time.time()
    }
# ─────────────────────────────────────────────────────────────

# ─────────────────────────────────────────────────────────────
# CLASSES & FONCTIONS (inchangées — copier depuis ton code original)
# ─────────────────────────────────────────────────────────────
class Person:
    def __init__(self, pid, cx, cy, h, w, box):
        self.id = pid; self.cx = cx; self.cy = cy
        self.pcx = cx; self.pcy = cy
        self.h = h; self.w = w; self.box = box
        self.frames = 0; self.last_seen = time.time()
        self.vspan_history = deque(maxlen=HISTORY)
        self.prev_vspan = None
        self.fall_timer = 0.0; self.lie_timer = 0.0
        self.alert_timer = 0.0; self.last_beep = 0.0
        self.status = "STANDING"
    
    def update(self, cx, cy, h, w, box, dt):
        self.pcx, self.pcy = self.cx, self.cy
        self.cx, self.cy = cx, cy
        self.h, self.w = h, w; self.box = box
        self.frames += 1; self.last_seen = time.time()

def compute_vspan(kps, conf, box_h):
    ys = [kps[i][1] for i in range(len(kps)) 
          if conf[i] >= CONF_MIN and kps[i][1] > 0]
    if len(ys) < 2: return None
    return float((max(ys) - min(ys)) / max(box_h, 1))

def is_lying(ratio, vspan):
    ratio_signal = ratio < LYING_RATIO_THRESH
    vspan_signal = (vspan is not None) and (vspan < LYING_VSPAN_THRESH)
    if ratio_signal and vspan_signal: return True, "ratio+vspan"
    elif ratio_signal: return True, "ratio"
    elif vspan_signal: return True, "vspan"
    return False, ""

class MotionCompensator:
    def __init__(self):
        self.prev_gray = None; self.sdx = 0.0; self.sdy = 0.0
    def estimate(self, frame):
        small = cv2.resize(frame, (0,0), fx=FLOW_SCALE, fy=FLOW_SCALE)
        gray = cv2.cvtColor(small, cv2.COLOR_BGR2GRAY)
        if self.prev_gray is None or self.prev_gray.shape != gray.shape:
            self.prev_gray = gray; return 0.0, 0.0
        flow = cv2.calcOpticalFlowFarneback(
            self.prev_gray, gray, None, pyr_scale=0.5, levels=3, winsize=13,
            iterations=3, poly_n=5, poly_sigma=1.2, flags=0)
        self.prev_gray = gray
        raw_dx = float(np.median(flow[...,0])) / FLOW_SCALE
        raw_dy = float(np.median(flow[...,1])) / FLOW_SCALE
        self.sdx = FLOW_SMOOTHING * self.sdx + (1-FLOW_SMOOTHING) * raw_dx
        self.sdy = FLOW_SMOOTHING * self.sdy + (1-FLOW_SMOOTHING) * raw_dy
        return self.sdx, self.sdy

def iou(b1, b2):
    xi1, yi1 = max(b1[0],b2[0]), max(b1[1],b2[1])
    xi2, yi2 = min(b1[2],b2[2]), min(b1[3],b2[3])
    inter = max(0, xi2-xi1) * max(0, yi2-yi1)
    a1, a2 = (b1[2]-b1[0])*(b1[3]-b1[1]), (b2[2]-b2[0])*(b2[3]-b2[1])
    return inter / max(a1+a2-inter, 1)

def draw_alert(frame, pid):
    h,w = frame.shape[:2]
    cv2.rectangle(frame, (0,0), (w,h), (0,0,220), 8)
    cv2.putText(frame, f"!! PERSON {pid} DOWN — CHECK NOW !!",
                (w//2-240, 45), cv2.FONT_HERSHEY_DUPLEX, 0.9, (0,0,255), 2)

def maybe_beep(p):
    now = time.time()
    if now - p.last_beep > ALERT_COOLDOWN:
        try: import winsound; winsound.Beep(880, 400)
        except: pass
        p.last_beep = now
# ─────────────────────────────────────────────────────────────

# ─────────────────────────────────────────────────────────────
# MAIN LOOP (inchangé sauf ajout de la sortie normalisée)
# ─────────────────────────────────────────────────────────────
print("Loading YOLOv8m-pose …")
model = YOLO("yolov8m-pose.pt")
cap = cv2.VideoCapture(0)
cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)

compensator = MotionCompensator()
tracks = {}; next_id = 0; last_time = time.time()
frame_count = 0  # ← NOUVEAU pour cadencer la sortie JSON

print("Fall Detection v5 (calibrated + instant clear) — press 'q' to quit")

while cap.isOpened():
    ret, frame = cap.read()
    if not ret: break
    
    curr_time = time.time()
    dt = max(curr_time - last_time, 0.001)
    last_time = curr_time
    
    scene_dx, scene_dy = compensator.estimate(frame)
    
    results = model(frame, conf=CONF_THRESHOLD, verbose=False)[0]
    detections = []
    
    if results.boxes is not None:
        for i, box in enumerate(results.boxes):
            x1,y1,x2,y2 = map(int, box.xyxy[0])
            h,w = y2-y1, x2-x1
            if h < MIN_HEIGHT: continue
            cx,cy = (x1+x2)/2.0, (y1+y2)/2.0
            kps, conf = None, None
            if results.keypoints is not None:
                kps = results.keypoints.xy[i].cpu().numpy()
                conf = (results.keypoints.conf[i].cpu().numpy() 
                        if results.keypoints.conf is not None 
                        else np.ones(len(kps)))
            detections.append({
                "cx":cx,"cy":cy,"h":h,"w":w,"x1":x1,"y1":y1,"x2":x2,"y2":y2,
                "box":(x1,y1,x2,y2), "kps":kps, "conf":conf
            })
    
    # Tracking (inchangé)
    matched, used_dets = set(), set()
    iou_scores = {}
    for pid, p in tracks.items():
        for di, det in enumerate(detections):
            s = iou(p.box, det['box'])
            if s > IOU_THRESH: iou_scores[(pid, di)] = s
    
    for (pid, di), s in sorted(iou_scores.items(), key=lambda x:-x[1]):
        if pid in matched or di in used_dets: continue
        tracks[pid].update(detections[di]['cx'], detections[di]['cy'],
                          detections[di]['h'], detections[di]['w'],
                          detections[di]['box'], dt)
        detections[di]['id'] = pid; matched.add(pid); used_dets.add(di)
    
    for di, det in enumerate(detections):
        if di in used_dets: continue
        best_id, best_d = None, MAX_CENTROID_DIST**2
        for pid, p in tracks.items():
            if pid in matched: continue
            d = (p.cx-det['cx'])**2 + (p.cy-det['cy'])**2
            if d < best_d: best_d = d; best_id = pid
        if best_id is not None:
            tracks[best_id].update(det['cx'],det['cy'],det['h'],det['w'],det['box'],dt)
            det['id'] = best_id; matched.add(best_id)
        else:
            next_id += 1
            tracks[next_id] = Person(next_id, det['cx'],det['cy'],det['h'],det['w'],det['box'])
            det['id'] = next_id
    
    for pid in list(tracks.keys()):
        if curr_time - tracks[pid].last_seen > LOST_TIMEOUT:
            del tracks[pid]
    
    # Fall/Lying logic (inchangé)
    for det in detections:
        p = tracks[det['id']]
        ratio = p.h / max(p.w, 1)
        comp_vy = (p.cy - p.pcy) / dt - scene_dy / dt
        comp_move = np.sqrt((p.cx-p.pcx-scene_dx)**2 + (p.cy-p.pcy-scene_dy)**2)
        
        vspan = None
        if det['kps'] is not None and det['conf'] is not None:
            vspan = compute_vspan(det['kps'], det['conf'], det['h'])
        
        p.vspan_history.append(vspan if vspan is not None else 0.5)
        avg_vspan = float(np.mean(p.vspan_history))
        
        vspan_drop = False
        if vspan is not None and p.prev_vspan is not None:
            if (p.prev_vspan - vspan) > VSPAN_DROP_THRESH: vspan_drop = True
        if vspan is not None: p.prev_vspan = vspan
        
        lying_pose, lie_reason = is_lying(ratio, avg_vspan)
        fast_down = comp_vy > VELOCITY_THRESH
        fall_signal = (fast_down or vspan_drop) and avg_vspan < 0.50
        clearly_standing = (ratio > LYING_RATIO_THRESH + 0.15 and 
                           avg_vspan > LYING_VSPAN_THRESH + 0.15)
        
        status, color = "STANDING", (0,200,0)
        
        if fall_signal: p.fall_timer += dt
        else:
            drain = 2.0 if clearly_standing else 0.4
            p.fall_timer = max(0.0, p.fall_timer - dt*drain)
        if p.fall_timer >= CONFIRM_FALL_TIME:
            status = "FALL" if comp_move < 12 else "UNSTABLE"
            color = (0,0,255) if status=="FALL" else (0,140,255)
        
        if lying_pose:
            if comp_move < 12: p.lie_timer += dt
            else: p.lie_timer = max(0.0, p.lie_timer - dt*0.5)
        else:
            drain = 3.0 if clearly_standing else 0.3
            p.lie_timer = max(0.0, p.lie_timer - dt*drain)
        if p.lie_timer >= CONFIRM_LIE_TIME:
            status = "LYING"; color = (200,0,200)
        
        if status in ("FALL","LYING"): p.alert_timer += dt
        elif clearly_standing: p.alert_timer = 0.0
        else: p.alert_timer = max(0.0, p.alert_timer - dt)
        
        p.status = status
        
        # Drawing (inchangé)
        x1,y1,x2,y2 = det['x1'],det['y1'],det['x2'],det['y2']
        cv2.rectangle(frame, (x1,y1),(x2,y2), color, 2)
        vs_str = f"{avg_vspan:.2f}" if avg_vspan else "?"
        label = f"ID:{p.id} {status} r={ratio:.2f} vs={vs_str} lt={p.lie_timer:.1f}s"
        cv2.putText(frame, label, (x1, max(y1-8,12)), cv2.FONT_HERSHEY_SIMPLEX, 0.40, color, 1)
        
        if det['kps'] is not None and det['conf'] is not None:
            for idx in range(len(det['kps'])):
                if det['conf'][idx] >= CONF_MIN:
                    kx,ky = int(det['kps'][idx][0]), int(det['kps'][idx][1])
                    dot = (0,255,255) if status!="STANDING" else (80,200,80)
                    cv2.circle(frame, (kx,ky), 3, dot, -1)
        
        if p.alert_timer >= ALERT_TIME:
            draw_alert(frame, p.id); maybe_beep(p)
    
    # HUD (inchangé)
    cv2.putText(frame, f"People:{len(detections)}  sdy={scene_dy:.1f}",
                (10,22), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (200,200,200), 1)
    
    cv2.imshow("Fall Detection v5", frame)
    
    # ─────────────────────────────────────────────────────────
    # NOUVEAU : Sortie normalisée toutes les 500ms (~15 frames à 30 FPS)
    # ─────────────────────────────────────────────────────────
    frame_count += 1
    if frame_count % 15 == 0:
        output = get_output_dict(list(tracks.values()), scene_dy)
        print(json.dumps(output, ensure_ascii=False))
        # Optionnel : 
        with open("output/fall_score.json","w") as f: json.dump(output,f)
    
    if cv2.waitKey(1) & 0xFF == ord('q'): break

cap.release()
cv2.destroyAllWindows()

# In[ ]: