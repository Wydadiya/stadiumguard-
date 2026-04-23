#!/usr/bin/env python
# coding: utf-8

# In[2]:
import os

# lab1_person_tracking.py — VERSION NORMALISÉE
from ultralytics import YOLO
import cv2
import time
import json  # ← NOUVEAU

model = YOLO("yolov8n.pt")
cap = cv2.VideoCapture(0)
cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)

CONF_THRESHOLD = 0.45
MIN_AREA = 2000
MAX_AREA = 300000
IOU_THRESHOLD = 0.7

prev_time = time.time()
frame_count = 0

# ─────────────────────────────────────────────────────────────
# NOUVEAU : Fonction de normalisation de sortie
# ─────────────────────────────────────────────────────────────
def get_person_score(valid_detections, confidences):
    """
    Calcule un score 0-100 basé sur la densité de personnes.
    - 0-30 : 0-2 personnes (normal)
    - 30-60 : 3-5 personnes (attention)
    - 60-100 : 6+ personnes ou confiances très basses (suspicious crowd)
    """
    if not confidences:
        return 0, 0.0
    
    avg_conf = sum(confidences) / len(confidences)
    
    if valid_detections <= 2:
        score = 10 + (valid_detections * 5)
    elif valid_detections <= 5:
        score = 30 + (valid_detections - 2) * 10
    else:
        score = 60 + min((valid_detections - 5) * 5, 40)
    
    # Pénalise si confiances moyennes sont basses (détections douteuses)
    if avg_conf < 0.5:
        score = min(score + 15, 100)
    
    return min(score, 100), round(avg_conf, 2)


def get_output_dict(valid_detections, confidences, fps):
    score, conf = get_person_score(valid_detections, confidences)
    return {
        "module": "person",
        "score": score,
        "confidence": conf,
        "details": {
            "person_count": valid_detections,
            "fps": round(fps, 1),
            "avg_confidence": conf
        },
        "timestamp": time.time()
    }
# ─────────────────────────────────────────────────────────────

print("▶ LAB 1 — TRACKING ENABLED | Press 'q' to quit")
while cap.isOpened():
    ret, frame = cap.read()
    if not ret: break
    
    results = model.track(frame, persist=True, conf=CONF_THRESHOLD, 
                         iou=IOU_THRESHOLD, classes=[0], verbose=False)
    r = results[0]
    
    valid_detections = 0
    confidences = []  # ← NOUVEAU : collecte des confiances
    
    for box in r.boxes:
        if box.id is None: continue
        
        x1, y1, x2, y2 = map(int, box.xyxy[0])
        conf = float(box.conf[0])
        track_id = int(box.id[0])
        area = (x2-x1) * (y2-y1)
        
        if not (MIN_AREA < area < MAX_AREA): continue
        
        valid_detections += 1
        confidences.append(conf)  # ← NOUVEAU
        
        color = (0, 255, 0) if conf > 0.6 else (0, 165, 255)
        cv2.rectangle(frame, (x1,y1), (x2,y2), color, 2)
        cv2.putText(frame, f"ID:{track_id} {conf:.2f}", (x1, y1-10), 
                   cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 1)
    
    # FPS Counter
    frame_count += 1
    if frame_count % 30 == 0:
        curr_time = time.time()
        fps = 30 / (curr_time - prev_time)
        prev_time = curr_time
        cv2.putText(frame, f"FPS: {fps:.1f}", (10, 30), 
                   cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255,255,0), 2)
    else:
        fps = 0  # fallback
    
    cv2.putText(frame, f"Persons: {valid_detections}", (10, 60), 
               cv2.FONT_HERSHEY_SIMPLEX, 1, (255,0,0), 2)
    
    cv2.imshow("Lab1: Person Tracking (StadiumGuard)", frame)
    
    # ─────────────────────────────────────────────────────────
    # NOUVEAU : Affiche/écrit la sortie normalisée toutes les 500ms
    # ─────────────────────────────────────────────────────────
    if frame_count % 15 == 0:  # ~500ms à 30 FPS
        output = get_output_dict(valid_detections, confidences, fps if fps else 30.0)
        print(json.dumps(output, ensure_ascii=False))  # ← Sortie JSON lisible
        
        # Optionnel : écrire dans un fichier pour l'orchestrateur
        with open("output/person_score.json", "w") as f:
            json.dump(output, f)
    
    if cv2.waitKey(1) & 0xFF == ord('q'): break

cap.release()
cv2.destroyAllWindows()

# In[ ]: