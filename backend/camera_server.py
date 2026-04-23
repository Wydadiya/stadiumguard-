#!/usr/bin/env python
# coding: utf-8
"""
camera_server.py — Orchestrateur StadiumGuard + Streaming MJPEG
================================================================
Lance les 3 modules d'analyse (Lab1, Lab2, Lab3) en parallèle
sur UN SEUL flux caméra, via des threads séparés.
Intègre un serveur Flask pour le streaming MJPEG vers le frontend.

Architecture :
    CameraThread  →  FrameQueue  →  Lab1Thread  → annotated JPEG → /api/stream/lab1
                  →  FrameQueue  →  Lab2Thread  → annotated JPEG → /api/stream/lab2
                  →  FrameQueue  →  Lab3Thread  → annotated JPEG → /api/stream/lab3

Mode headless (HEADLESS_MODE=True) : pas de fenêtres cv2, streaming web uniquement.
Arrêt : Ctrl+C ou 'q' dans une fenêtre (si headless=False).
"""

import cv2
import time
import threading
import queue
import os
import sys
import json
import shutil
import subprocess
import io
import math
from pathlib import Path
from datetime import datetime

# ─── Mode headless : True = pas de fenêtres cv2, streaming web uniquement ────
HEADLESS_MODE = True

# ─── Assurer que le dossier output existe ────────────────────────────────────
os.makedirs("output", exist_ok=True)

# ─── Cache local des modèles YOLO pour éviter les re-téléchargements ────────
MODELS_DIR = Path(__file__).resolve().parent / "models"
MODELS_DIR.mkdir(parents=True, exist_ok=True)


def resolve_model_path(model_name: str) -> str:
    """
    Retourne un chemin local vers le modèle YOLO.
    - Si backend/models/<model_name> existe, on l'utilise directement.
    - Sinon on laisse Ultralytics le résoudre/télécharger une fois,
      puis on copie le poids dans backend/models pour les prochains démarrages.
    """
    local_model = MODELS_DIR / model_name
    if local_model.exists():
        print(f"[Model] Local cache trouvé: {local_model}")
        return str(local_model)

    from ultralytics import YOLO

    print(f"[Model] Préparation de {model_name} (premier démarrage)...")
    model = YOLO(model_name)
    ckpt_path = getattr(model, "ckpt_path", None)
    if ckpt_path:
        resolved = Path(ckpt_path)
        if resolved.exists():
            shutil.copy2(resolved, local_model)
            print(f"[Model] Modèle mis en cache local: {local_model}")
            return str(local_model)

    # Fallback sûr si la copie locale échoue.
    return model_name

# ─── Flag d'arrêt global ─────────────────────────────────────────────────────
stop_event = threading.Event()

# ─── Queues de frames (maxsize=2 pour éviter l'accumulation / latence) ───────
q_lab1 = queue.Queue(maxsize=2)
q_lab2 = queue.Queue(maxsize=2)
q_lab3 = queue.Queue(maxsize=2)

# ─── Buffers de frames JPEG pour le streaming MJPEG ──────────────────────────
latest_frame_lab1 = None
latest_frame_lab2 = None
latest_frame_lab3 = None
lock_lab1 = threading.Lock()
lock_lab2 = threading.Lock()
lock_lab3 = threading.Lock()


# ═══════════════════════════════════════════════════════════════════════════════
# THREAD CAMÉRA — capture unique, distribue à tous les labs
# ═══════════════════════════════════════════════════════════════════════════════
def camera_thread():
    while not stop_event.is_set():
        cap = cv2.VideoCapture(0)
        cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
        cap.set(cv2.CAP_PROP_FRAME_WIDTH,  640)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)

        if not cap.isOpened():
            # Keep backend API alive even when no camera is attached.
            # This allows ESP32 endpoints (/api/robot/audio-stream, /api/esp32/*) to keep working.
            print("[ERREUR] Impossible d'ouvrir la caméra. Mode API-only activé (pas de flux vidéo). Retry dans 2s...")
            cap.release()
            time.sleep(2.0)
            continue

        print("[Camera] Démarrage de la capture...")

        while not stop_event.is_set():
            ret, frame = cap.read()
            if not ret:
                print("[Camera] Flux interrompu. Tentative de reconnexion...")
                break

            # Distribue à chaque lab — on écrase la frame la plus ancienne si le
            # worker est trop lent (politique "drop oldest").
            for q in (q_lab1, q_lab2, q_lab3):
                if q.full():
                    try:
                        q.get_nowait()   # retire l'ancienne frame
                    except queue.Empty:
                        pass
                q.put(frame.copy())

        cap.release()
        if not stop_event.is_set():
            time.sleep(1.0)

    print("[Camera] Arrêtée.")


# ═══════════════════════════════════════════════════════════════════════════════
# LAB 1 — Person Tracking
# ═══════════════════════════════════════════════════════════════════════════════
def lab1_thread():
    """
    Reprend exactement la logique de lab1.py.
    Seul changement : cap.read() est remplacé par q_lab1.get().
    """
    import json
    from ultralytics import YOLO

    CONF_THRESHOLD = 0.45
    MIN_AREA       = 2000
    MAX_AREA       = 300000
    IOU_THRESHOLD  = 0.7

    model = YOLO(resolve_model_path("yolov8n.pt"))

    prev_time   = time.time()
    frame_count = 0
    fps         = 30.0

    # ── fonctions de scoring (identiques à lab1.py) ──────────────────────────
    def get_person_score(valid_detections, confidences):
        if not confidences:
            return 0, 0.0
        avg_conf = sum(confidences) / len(confidences)
        if valid_detections <= 2:
            score = 10 + (valid_detections * 5)
        elif valid_detections <= 5:
            score = 30 + (valid_detections - 2) * 10
        else:
            score = 60 + min((valid_detections - 5) * 5, 40)
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
                "person_count":   valid_detections,
                "fps":            round(fps, 1),
                "avg_confidence": conf
            },
            "timestamp": time.time()
        }

    print("[Lab1] Démarré — Person Tracking")

    while not stop_event.is_set():
        try:
            frame = q_lab1.get(timeout=1.0)
        except queue.Empty:
            continue

        results = model.track(frame, persist=True, conf=CONF_THRESHOLD,
                              iou=IOU_THRESHOLD, classes=[0], verbose=False)
        r = results[0]

        valid_detections = 0
        confidences      = []

        for box in r.boxes:
            if box.id is None:
                continue
            x1, y1, x2, y2 = map(int, box.xyxy[0])
            conf     = float(box.conf[0])
            track_id = int(box.id[0])
            area     = (x2 - x1) * (y2 - y1)
            if not (MIN_AREA < area < MAX_AREA):
                continue
            valid_detections += 1
            confidences.append(conf)
            color = (0, 255, 0) if conf > 0.6 else (0, 165, 255)
            cv2.rectangle(frame, (x1, y1), (x2, y2), color, 2)
            cv2.putText(frame, f"ID:{track_id} {conf:.2f}",
                        (x1, y1 - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 1)

        frame_count += 1
        if frame_count % 30 == 0:
            curr_time = time.time()
            fps       = 30 / (curr_time - prev_time)
            prev_time = curr_time

        cv2.putText(frame, f"FPS: {fps:.1f}", (10, 30),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 0), 2)
        cv2.putText(frame, f"Persons: {valid_detections}", (10, 60),
                    cv2.FONT_HERSHEY_SIMPLEX, 1, (255, 0, 0), 2)

        # ── Stocker la frame pour le streaming MJPEG ─────────────────────
        global latest_frame_lab1
        _, jpeg = cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, 75])
        with lock_lab1:
            latest_frame_lab1 = jpeg.tobytes()

        if not HEADLESS_MODE:
            cv2.imshow("Lab1: Person Tracking (StadiumGuard)", frame)

        if frame_count % 15 == 0:
            output = get_output_dict(valid_detections, confidences, fps)
            print(json.dumps(output, ensure_ascii=False))
            with open("output/person_score.json", "w") as f:
                json.dump(output, f)

        if not HEADLESS_MODE:
            key = cv2.waitKey(1) & 0xFF
            if key == ord('q'):
                stop_event.set()

    print("[Lab1] Arrêté.")


# ═══════════════════════════════════════════════════════════════════════════════
# LAB 2 — Fall Detection
# ═══════════════════════════════════════════════════════════════════════════════
def lab2_thread():
    """
    Reprend exactement la logique de lab2.py.
    Seul changement : cap.read() est remplacé par q_lab2.get().
    """
    import json
    import numpy as np
    from ultralytics import YOLO
    from collections import deque

    # ── Config ────────────────────────────────────────────────────────────────
    CONF_THRESHOLD      = 0.35
    MIN_HEIGHT          = 40
    FLOW_SCALE          = 0.4
    FLOW_SMOOTHING      = 0.6
    LYING_RATIO_THRESH  = 0.60
    LYING_VSPAN_THRESH  = 0.38
    CONF_MIN            = 0.25
    VELOCITY_THRESH     = 180
    VSPAN_DROP_THRESH   = 0.28
    CONFIRM_FALL_TIME   = 1.0
    CONFIRM_LIE_TIME    = 2.0
    ALERT_TIME          = 4.0
    LOST_TIMEOUT        = 4.0
    IOU_THRESH          = 0.20
    MAX_CENTROID_DIST   = 180
    HISTORY             = 10
    ALERT_COOLDOWN      = 4.0

    # ── Classes & helpers (identiques à lab2.py) ──────────────────────────────
    class Person:
        def __init__(self, pid, cx, cy, h, w, box):
            self.id = pid; self.cx = cx; self.cy = cy
            self.pcx = cx; self.pcy = cy
            self.h = h; self.w = w; self.box = box
            self.frames = 0; self.last_seen = time.time()
            self.vspan_history = deque(maxlen=HISTORY)
            self.prev_vspan = None
            self.fall_timer  = 0.0; self.lie_timer  = 0.0
            self.alert_timer = 0.0; self.last_beep  = 0.0
            self.status = "STANDING"

        def update(self, cx, cy, h, w, box, dt):
            self.pcx, self.pcy = self.cx, self.cy
            self.cx, self.cy   = cx, cy
            self.h, self.w     = h, w
            self.box = box
            self.frames    += 1
            self.last_seen  = time.time()

    def compute_vspan(kps, conf, box_h):
        ys = [kps[i][1] for i in range(len(kps))
              if conf[i] >= CONF_MIN and kps[i][1] > 0]
        if len(ys) < 2:
            return None
        return float((max(ys) - min(ys)) / max(box_h, 1))

    def is_lying(ratio, vspan):
        ratio_signal = ratio < LYING_RATIO_THRESH
        vspan_signal = (vspan is not None) and (vspan < LYING_VSPAN_THRESH)
        if ratio_signal and vspan_signal: return True, "ratio+vspan"
        elif ratio_signal:                return True, "ratio"
        elif vspan_signal:                return True, "vspan"
        return False, ""

    class MotionCompensator:
        def __init__(self):
            self.prev_gray = None; self.sdx = 0.0; self.sdy = 0.0

        def estimate(self, frame):
            small = cv2.resize(frame, (0, 0), fx=FLOW_SCALE, fy=FLOW_SCALE)
            gray  = cv2.cvtColor(small, cv2.COLOR_BGR2GRAY)
            if self.prev_gray is None or self.prev_gray.shape != gray.shape:
                self.prev_gray = gray; return 0.0, 0.0
            flow = cv2.calcOpticalFlowFarneback(
                self.prev_gray, gray, None, pyr_scale=0.5, levels=3,
                winsize=13, iterations=3, poly_n=5, poly_sigma=1.2, flags=0)
            self.prev_gray = gray
            raw_dx = float(np.median(flow[..., 0])) / FLOW_SCALE
            raw_dy = float(np.median(flow[..., 1])) / FLOW_SCALE
            self.sdx = FLOW_SMOOTHING * self.sdx + (1 - FLOW_SMOOTHING) * raw_dx
            self.sdy = FLOW_SMOOTHING * self.sdy + (1 - FLOW_SMOOTHING) * raw_dy
            return self.sdx, self.sdy

    def iou(b1, b2):
        xi1, yi1 = max(b1[0], b2[0]), max(b1[1], b2[1])
        xi2, yi2 = min(b1[2], b2[2]), min(b1[3], b2[3])
        inter = max(0, xi2 - xi1) * max(0, yi2 - yi1)
        a1 = (b1[2] - b1[0]) * (b1[3] - b1[1])
        a2 = (b2[2] - b2[0]) * (b2[3] - b2[1])
        return inter / max(a1 + a2 - inter, 1)

    def draw_alert(frame, pid):
        h, w = frame.shape[:2]
        cv2.rectangle(frame, (0, 0), (w, h), (0, 0, 220), 8)
        cv2.putText(frame, f"!! PERSON {pid} DOWN — CHECK NOW !!",
                    (w // 2 - 240, 45), cv2.FONT_HERSHEY_DUPLEX, 0.9, (0, 0, 255), 2)

    def maybe_beep(p):
        now = time.time()
        if now - p.last_beep > ALERT_COOLDOWN:
            try:
                import winsound; winsound.Beep(880, 400)
            except:
                pass
            p.last_beep = now

    def get_fall_score(persons):
        if not persons:
            return 0, 1.0
        max_score = 0; max_conf = 0.0
        for p in persons:
            if p.status == "STANDING":
                score = 10
            elif p.status == "UNSTABLE":
                score = 40
            elif p.status in ("FALL", "LYING"):
                score = 70 + min(p.alert_timer / ALERT_TIME * 30, 30)
            else:
                score = 20
            conf = min(0.5 + p.frames * 0.02, 1.0) if p.status != "STANDING" else 0.9
            if score > max_score:
                max_score = score; max_conf = conf
        return min(max_score, 100), round(max_conf, 2)

    def get_output_dict(persons, scene_dy):
        score, conf = get_fall_score(persons)
        return {
            "module": "fall",
            "score":  score,
            "confidence": conf,
            "details": {
                "tracked_persons": len(persons),
                "statuses":        {p.id: p.status for p in persons},
                "scene_motion_y":  round(scene_dy, 1)
            },
            "timestamp": time.time()
        }

    # ── Init ──────────────────────────────────────────────────────────────────
    print("[Lab2] Chargement YOLOv8m-pose …")
    model       = YOLO(resolve_model_path("yolov8m-pose.pt"))
    compensator = MotionCompensator()
    tracks      = {}; next_id = 0
    last_time   = time.time(); frame_count = 0

    print("[Lab2] Démarré — Fall Detection")

    while not stop_event.is_set():
        try:
            frame = q_lab2.get(timeout=1.0)
        except queue.Empty:
            continue

        curr_time = time.time()
        dt        = max(curr_time - last_time, 0.001)
        last_time = curr_time

        scene_dx, scene_dy = compensator.estimate(frame)
        results    = model(frame, conf=CONF_THRESHOLD, verbose=False)[0]
        detections = []

        if results.boxes is not None:
            for i, box in enumerate(results.boxes):
                x1, y1, x2, y2 = map(int, box.xyxy[0])
                h, w = y2 - y1, x2 - x1
                if h < MIN_HEIGHT:
                    continue
                cx, cy = (x1 + x2) / 2.0, (y1 + y2) / 2.0
                kps = conf_kp = None
                if results.keypoints is not None:
                    kps     = results.keypoints.xy[i].cpu().numpy()
                    conf_kp = (results.keypoints.conf[i].cpu().numpy()
                               if results.keypoints.conf is not None
                               else np.ones(len(kps)))
                detections.append({
                    "cx": cx, "cy": cy, "h": h, "w": w,
                    "x1": x1, "y1": y1, "x2": x2, "y2": y2,
                    "box": (x1, y1, x2, y2), "kps": kps, "conf": conf_kp
                })

        # Tracking
        matched = set(); used_dets = set(); iou_scores = {}
        for pid, p in tracks.items():
            for di, det in enumerate(detections):
                s = iou(p.box, det['box'])
                if s > IOU_THRESH:
                    iou_scores[(pid, di)] = s

        for (pid, di), s in sorted(iou_scores.items(), key=lambda x: -x[1]):
            if pid in matched or di in used_dets:
                continue
            tracks[pid].update(detections[di]['cx'], detections[di]['cy'],
                               detections[di]['h'],  detections[di]['w'],
                               detections[di]['box'], dt)
            detections[di]['id'] = pid; matched.add(pid); used_dets.add(di)

        for di, det in enumerate(detections):
            if di in used_dets:
                continue
            best_id = None; best_d = MAX_CENTROID_DIST ** 2
            for pid, p in tracks.items():
                if pid in matched:
                    continue
                d = (p.cx - det['cx']) ** 2 + (p.cy - det['cy']) ** 2
                if d < best_d:
                    best_d = d; best_id = pid
            if best_id is not None:
                tracks[best_id].update(det['cx'], det['cy'], det['h'],
                                       det['w'], det['box'], dt)
                det['id'] = best_id; matched.add(best_id)
            else:
                next_id += 1
                tracks[next_id] = Person(next_id, det['cx'], det['cy'],
                                         det['h'], det['w'], det['box'])
                det['id'] = next_id

        for pid in list(tracks.keys()):
            if curr_time - tracks[pid].last_seen > LOST_TIMEOUT:
                del tracks[pid]

        # Fall/Lying logic
        for det in detections:
            p        = tracks[det['id']]
            ratio    = p.h / max(p.w, 1)
            comp_vy  = (p.cy - p.pcy) / dt - scene_dy / dt
            comp_move = np.sqrt((p.cx - p.pcx - scene_dx) ** 2 +
                                (p.cy - p.pcy - scene_dy) ** 2)

            vspan = None
            if det['kps'] is not None and det['conf'] is not None:
                vspan = compute_vspan(det['kps'], det['conf'], det['h'])

            p.vspan_history.append(vspan if vspan is not None else 0.5)
            avg_vspan = float(np.mean(p.vspan_history))

            vspan_drop = False
            if vspan is not None and p.prev_vspan is not None:
                if (p.prev_vspan - vspan) > VSPAN_DROP_THRESH:
                    vspan_drop = True
            if vspan is not None:
                p.prev_vspan = vspan

            lying_pose, _ = is_lying(ratio, avg_vspan)
            fast_down     = comp_vy > VELOCITY_THRESH
            fall_signal   = (fast_down or vspan_drop) and avg_vspan < 0.50
            clearly_standing = (ratio > LYING_RATIO_THRESH + 0.15 and
                                avg_vspan > LYING_VSPAN_THRESH + 0.15)

            status = "STANDING"; color = (0, 200, 0)

            if fall_signal:
                p.fall_timer += dt
            else:
                drain = 2.0 if clearly_standing else 0.4
                p.fall_timer = max(0.0, p.fall_timer - dt * drain)
            if p.fall_timer >= CONFIRM_FALL_TIME:
                status = "FALL" if comp_move < 12 else "UNSTABLE"
                color  = (0, 0, 255) if status == "FALL" else (0, 140, 255)

            if lying_pose:
                if comp_move < 12: p.lie_timer += dt
                else:              p.lie_timer = max(0.0, p.lie_timer - dt * 0.5)
            else:
                drain = 3.0 if clearly_standing else 0.3
                p.lie_timer = max(0.0, p.lie_timer - dt * drain)
            if p.lie_timer >= CONFIRM_LIE_TIME:
                status = "LYING"; color = (200, 0, 200)

            if status in ("FALL", "LYING"): p.alert_timer += dt
            elif clearly_standing:          p.alert_timer  = 0.0
            else:                           p.alert_timer  = max(0.0, p.alert_timer - dt)

            p.status = status

            x1, y1, x2, y2 = det['x1'], det['y1'], det['x2'], det['y2']
            cv2.rectangle(frame, (x1, y1), (x2, y2), color, 2)
            vs_str = f"{avg_vspan:.2f}" if avg_vspan else "?"
            label  = (f"ID:{p.id} {status} r={ratio:.2f} "
                      f"vs={vs_str} lt={p.lie_timer:.1f}s")
            cv2.putText(frame, label, (x1, max(y1 - 8, 12)),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.40, color, 1)

            if det['kps'] is not None and det['conf'] is not None:
                for idx in range(len(det['kps'])):
                    if det['conf'][idx] >= CONF_MIN:
                        kx, ky = int(det['kps'][idx][0]), int(det['kps'][idx][1])
                        dot = (0, 255, 255) if status != "STANDING" else (80, 200, 80)
                        cv2.circle(frame, (kx, ky), 3, dot, -1)

            if p.alert_timer >= ALERT_TIME:
                draw_alert(frame, p.id); maybe_beep(p)

        cv2.putText(frame, f"People:{len(detections)}  sdy={scene_dy:.1f}",
                    (10, 22), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (200, 200, 200), 1)

        # ── Stocker la frame pour le streaming MJPEG ─────────────────────
        global latest_frame_lab2
        _, jpeg = cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, 75])
        with lock_lab2:
            latest_frame_lab2 = jpeg.tobytes()

        if not HEADLESS_MODE:
            cv2.imshow("Fall Detection v5", frame)

        frame_count += 1
        if frame_count % 15 == 0:
            output = get_output_dict(list(tracks.values()), scene_dy)
            print(json.dumps(output, ensure_ascii=False))
            with open("output/fall_score.json", "w") as f:
                json.dump(output, f)

        if not HEADLESS_MODE:
            key = cv2.waitKey(1) & 0xFF
            if key == ord('q'):
                stop_event.set()

    print("[Lab2] Arrêté.")


# ═══════════════════════════════════════════════════════════════════════════════
# LAB 3 — Motion Classifier
# ═══════════════════════════════════════════════════════════════════════════════
def lab3_thread():
    """
    Reprend exactement la logique de lab3.py.
    Seul changement : cap.read() est remplacé par q_lab3.get().
    Import dynamique pour éviter les conflits de namespace avec lab1/lab2.
    """
    # On importe lab3 comme module — ses globals restent dans son propre namespace
    import importlib.util, sys, pathlib

    spec = importlib.util.spec_from_file_location(
        "lab3",
        pathlib.Path(__file__).parent / "lab3.py"
    )

    # lab3.py a une boucle principale au niveau module : on ne peut pas l'importer
    # directement sans l'exécuter.  La solution propre est donc de copier ici
    # uniquement la boucle principale en remplaçant cap.read() par q_lab3.get().
    # Les classes (MotionClassifier, etc.) sont définies dans lab3.py et doivent
    # être disponibles.  On utilise exec() dans un namespace isolé.

    import json
    import numpy as np
    from collections import deque

    # ── Constantes (identiques à lab3.py) ─────────────────────────────────────
    FLOW_SCALE         = 0.5; FLOW_LEVELS = 3; FLOW_WINSIZE = 15
    FLOW_ITERATIONS    = 3;   FLOW_POLY_N = 5; FLOW_POLY_SIGMA = 1.2
    GRID_COLS          = 8;   GRID_ROWS   = 6; CAM_COMP_SMOOTHING = 0.55
    BASELINE_WARMUP_S  = 30.0; BASELINE_WINDOW_S = 120.0
    BASELINE_FPS_EST   = 25;   BASELINE_MIN_STD  = 0.05
    FREEZE_ZSCORE_THRESH  = 2.5; FREEZE_RELEASE_S   = 10.0
    ALERT_ZSCORE_FIGHT    = 4.5; ALERT_ZSCORE_STAMPEDE = 5.0
    SIGNAL_WEIGHTS = {
        "h_ratio": 2.0, "spikiness": 2.0, "spike": 2.5,
        "smoothness": -2.0, "hot_coh": -2.5, "rhythm": -3.0,
        "coherence": 3.5, "mean_mag": 1.5
    }
    CELL_COHERENCE_CELEB_THRESH  = 0.55
    CELL_COHERENCE_FIGHT_THRESH  = 0.30
    RHYTHM_MIN_PERIOD_FRAMES = 8;  RHYTHM_MAX_PERIOD_FRAMES = 90
    SPIKE_WINDOW_S  = 0.6; SPIKE_RISE_THRESH = 2.5
    HISTORY_FRAMES  = 20;  SMOOTH_ALPHA      = 0.20
    ALERT_FIGHT_S   = 4.0; ALERT_STAMP_S     = 5.0
    VECTOR_SCALE    = 4.0; VECTOR_STEP       = 30

    LABEL_STYLE = {
        "LEARNING":    {"text":"LEARNING...",     "desc":"Building baseline",       "bar_color":(180,180,60), "bg_color":(30,30,0),   "text_color":(220,210,60), "border":False},
        "CALM":        {"text":"CALM",            "desc":"No unusual activity",     "bar_color":(60,200,60),  "bg_color":(15,40,15),  "text_color":(60,230,60),  "border":False},
        "CELEBRATION": {"text":"CELEBRATION",     "desc":"Fans cheering",           "bar_color":(0,210,210),  "bg_color":(0,40,40),   "text_color":(0,220,220),  "border":False},
        "FIGHT":       {"text":"FIGHT DETECTED",  "desc":"Localized violent motion","bar_color":(0,50,220),   "bg_color":(40,0,0),    "text_color":(60,80,255),  "border":True},
        "STAMPEDE":    {"text":"STAMPEDE",        "desc":"Mass directional movement","bar_color":(0,130,255), "bg_color":(0,20,50),   "text_color":(40,160,255), "border":True},
    }

    # ── helpers ───────────────────────────────────────────────────────────────
    def safe(v):
        return float(np.nan_to_num(v, nan=0.0, posinf=0.0, neginf=0.0))
    def safe_clamp(v, lo=0.0, hi=1.0):
        return float(np.clip(safe(v), lo, hi))
    def circular_coherence(angles):
        if len(angles) < 2: return 0.0
        return safe(np.sqrt(np.mean(np.sin(angles))**2 + np.mean(np.cos(angles))**2))

    # ── Classes (identiques à lab3.py) ────────────────────────────────────────
    class AdaptiveBaseline:
        def __init__(self):
            maxlen = int(BASELINE_WINDOW_S * BASELINE_FPS_EST)
            self._data  = {k: deque(maxlen=maxlen) for k in SIGNAL_WEIGHTS}
            self._means = {k: None for k in SIGNAL_WEIGHTS}
            self._stds  = {k: BASELINE_MIN_STD for k in SIGNAL_WEIGHTS}
            self._frozen = False; self._freeze_time = 0.0
            self.start_time = time.time(); self.n_samples = 0
        @property
        def age_s(self): return time.time() - self.start_time
        @property
        def warmed_up(self): return self.age_s >= BASELINE_WARMUP_S and self.n_samples >= 30
        @property
        def frozen(self): return self._frozen
        def update(self, signals: dict):
            if self._frozen:
                if time.time() - self._freeze_time > FREEZE_RELEASE_S: self._frozen = False
                return
            for k, v in signals.items():
                if k in self._data: self._data[k].append(safe(v))
            for k in self._data:
                arr = np.array(self._data[k], dtype=np.float32)
                if len(arr) >= 5:
                    self._means[k] = float(np.mean(arr))
                    self._stds[k]  = max(float(np.std(arr)), BASELINE_MIN_STD)
            self.n_samples += 1
        def freeze(self):
            if not self._frozen: self._frozen = True; self._freeze_time = time.time()
        def unfreeze(self): self._frozen = False
        def zscore(self, name: str, val: float) -> float:
            if self._means[name] is None: return 0.0
            return safe((safe(val) - self._means[name]) / self._stds[name])
        def get_stats(self, name: str):
            m, s = self._means[name], self._stds[name]
            return (m if m is not None else 0.0), s

    class CameraCompensator:
        def __init__(self): self.gdx = 0.0; self.gdy = 0.0
        def compensate(self, flow):
            raw_dx = float(np.clip(np.median(flow[..., 0]), -20, 20))
            raw_dy = float(np.clip(np.median(flow[..., 1]), -20, 20))
            s = CAM_COMP_SMOOTHING
            self.gdx = s*self.gdx + (1-s)*raw_dx
            self.gdy = s*self.gdy + (1-s)*raw_dy
            comp = flow.copy(); comp[..., 0] -= self.gdx; comp[..., 1] -= self.gdy
            return comp, self.gdx, self.gdy

    def compute_axis_ratio(fx, fy, mask):
        if not np.any(mask): return 0.5
        mx = safe(np.mean(np.abs(fx[mask]))); my = safe(np.mean(np.abs(fy[mask])))
        t = mx + my; return mx / t if t > 0.01 else 0.5

    def compute_cell_grid(fx, fy, fh, fw):
        mag = np.sqrt(fx**2 + fy**2); angle = np.arctan2(fy, fx)
        cell_mags = np.zeros((GRID_ROWS, GRID_COLS), dtype=np.float32)
        cell_cohs = np.zeros((GRID_ROWS, GRID_COLS), dtype=np.float32)
        for r in range(GRID_ROWS):
            for c in range(GRID_COLS):
                y0, y1 = int(r*fh/GRID_ROWS), int((r+1)*fh/GRID_ROWS)
                x0, x1 = int(c*fw/GRID_COLS), int((c+1)*fw/GRID_COLS)
                cm, ca = mag[y0:y1, x0:x1], angle[y0:y1, x0:x1]
                if cm.size == 0: continue
                cell_mags[r, c] = float(np.mean(cm))
                mv = cm > 0.4
                cell_cohs[r, c] = circular_coherence(ca[mv].ravel()) if mv.sum() > 4 else 0.0
        cell_mags = np.nan_to_num(cell_mags, nan=0.0)
        cell_cohs = np.nan_to_num(cell_cohs, nan=0.0)
        mean_m = float(np.mean(cell_mags)); max_m = float(np.max(cell_mags))
        if mean_m < 0.1:
            return cell_mags, cell_cohs, cell_mags < 0, 0.0, 0.0, 0.0
        spikiness  = safe(max_m / mean_m)
        hot_mask   = cell_mags > (mean_m * 1.8)
        hot_count  = int(np.sum(hot_mask))
        hot_coh    = float(np.mean(cell_cohs[hot_mask])) if hot_count > 0 else 0.0
        mean_coh   = float(np.mean(cell_cohs))
        return cell_mags, cell_cohs, hot_mask, spikiness, hot_coh, mean_coh

    class RhythmDetector:
        def __init__(self):
            self.mag_history = deque(maxlen=RHYTHM_MAX_PERIOD_FRAMES * 2)
        def update(self, mean_mag: float) -> float:
            self.mag_history.append(safe(mean_mag))
            if len(self.mag_history) < RHYTHM_MIN_PERIOD_FRAMES * 2:
                return 0.0
            arr = np.array(self.mag_history, dtype=np.float32)
            arr = arr - np.mean(arr)
            if np.std(arr) < 0.05: return 0.0
            acorr = np.correlate(arr, arr, mode='full')
            acorr = acorr[len(acorr)//2:]
            acorr /= max(acorr[0], 1e-6)
            search = acorr[RHYTHM_MIN_PERIOD_FRAMES:RHYTHM_MAX_PERIOD_FRAMES]
            if len(search) == 0: return 0.0
            peak = float(np.max(search))
            return safe_clamp(peak, 0.0, 1.0)

    class SpikeDetector:
        def __init__(self):
            self.recent = deque(maxlen=int(SPIKE_WINDOW_S * BASELINE_FPS_EST * 2))
            self.baseline_mag = deque(maxlen=int(BASELINE_WINDOW_S * BASELINE_FPS_EST))
        def update(self, mean_mag: float) -> float:
            self.recent.append(safe(mean_mag))
            self.baseline_mag.append(safe(mean_mag))
            if len(self.recent) < 3 or len(self.baseline_mag) < 20: return 0.0
            arr = np.array(self.recent, dtype=np.float32)
            bsl = np.array(self.baseline_mag, dtype=np.float32)
            bsl_mean = float(np.mean(bsl)); bsl_std = max(float(np.std(bsl)), 0.1)
            curr = float(np.max(arr[-int(SPIKE_WINDOW_S*BASELINE_FPS_EST):]))
            z = (curr - bsl_mean) / bsl_std
            return safe_clamp((z - 1.0) / (SPIKE_RISE_THRESH - 1.0))

    class SmoothedSignals:
        def __init__(self):
            self._vals = {}
        def update(self, key: str, val: float) -> float:
            prev = self._vals.get(key, safe(val))
            smoothed = SMOOTH_ALPHA * safe(val) + (1 - SMOOTH_ALPHA) * prev
            self._vals[key] = smoothed
            return smoothed
        def get(self, key: str) -> float:
            return self._vals.get(key, 0.0)

    class MotionClassifier:
        def __init__(self):
            self.baseline   = AdaptiveBaseline()
            self.compensator= CameraCompensator()
            self.rhythm     = RhythmDetector()
            self.spike_det  = SpikeDetector()
            self.smoother   = SmoothedSignals()
            self.danger_timer   = 0.0
            self.last_label     = "LEARNING"
            self.last_time      = time.time()

        def classify(self, flow, fh, fw):
            now = time.time(); dt = max(now - self.last_time, 0.001); self.last_time = now
            comp_flow, cam_dx, cam_dy = self.compensator.compensate(flow)
            fx = comp_flow[..., 0]; fy = comp_flow[..., 1]
            mag = np.sqrt(fx**2 + fy**2)
            mean_mag  = safe_clamp(safe(np.mean(mag)), 0.0, 20.0)
            h_ratio   = safe_clamp(compute_axis_ratio(fx, fy, mag > 0.3))
            cell_mags, cell_cohs, hot_mask, spikiness, hot_coh, coherence = \
                compute_cell_grid(fx, fy, *flow.shape[:2])
            rhythm   = self.rhythm.update(mean_mag)
            spike    = self.spike_det.update(mean_mag)
            smoothness = safe_clamp(1.0 - safe(np.std(mag) / max(mean_mag, 0.1)), 0.0, 1.0) \
                         if mean_mag > 0.3 else 1.0

            raw_signals = {
                "h_ratio":    h_ratio,
                "spikiness":  safe_clamp(spikiness / 5.0),
                "spike":      spike,
                "smoothness": smoothness,
                "hot_coh":    hot_coh,
                "rhythm":     rhythm,
                "coherence":  coherence,
                "mean_mag":   safe_clamp(mean_mag / 5.0)
            }
            signals = {k: self.smoother.update(k, v) for k, v in raw_signals.items()}

            if not self.baseline.warmed_up:
                self.baseline.update(signals)
                label = "LEARNING"
                metrics = {**signals, "cam_dx": cam_dx, "cam_dy": cam_dy,
                           "cell_mags": cell_mags, "cell_cohs": cell_cohs,
                           "hot_mask": hot_mask, "warmed_up": False,
                           "fight_z": 0.0, "stampede_z": 0.0, "composite_z": 0.0,
                           "danger_s": 0.0, "age_s": self.baseline.age_s}
                return label, metrics

            zscores = {k: self.baseline.zscore(k, v) for k, v in signals.items()}
            composite_z = sum(zscores[k] * w for k, w in SIGNAL_WEIGHTS.items())
            fight_z     = (zscores["spikiness"] * 2.0 + zscores["spike"] * 2.0 +
                           zscores["h_ratio"] * 1.5 + (1 - hot_coh) * 2.0)
            stampede_z  = (zscores["coherence"] * 3.0 + zscores["mean_mag"] * 2.0 +
                           zscores["smoothness"] * (-1.0) + zscores["h_ratio"] * 1.5)

            freeze_z = abs(composite_z)
            if freeze_z > FREEZE_ZSCORE_THRESH: self.baseline.freeze()
            else:                               self.baseline.update(signals)

            if fight_z > ALERT_ZSCORE_FIGHT or stampede_z > ALERT_ZSCORE_STAMPEDE:
                self.danger_timer += dt
            else:
                self.danger_timer = max(0.0, self.danger_timer - dt * 0.5)

            if fight_z > ALERT_ZSCORE_FIGHT and self.danger_timer >= ALERT_FIGHT_S:
                label = "FIGHT"
            elif stampede_z > ALERT_ZSCORE_STAMPEDE and self.danger_timer >= ALERT_STAMP_S:
                label = "STAMPEDE"
            elif composite_z < -1.5 and rhythm > 0.4:
                label = "CELEBRATION"
            elif (abs(composite_z) < 1.5 and
                  fight_z < ALERT_ZSCORE_FIGHT * 0.7 and
                  stampede_z < ALERT_ZSCORE_STAMPEDE * 0.7):
                label = "CALM"
            else:
                label = self.last_label if self.last_label != "LEARNING" else "CALM"

            self.last_label = label
            metrics = {**signals, **zscores,
                       "cam_dx": cam_dx, "cam_dy": cam_dy,
                       "cell_mags": cell_mags, "cell_cohs": cell_cohs,
                       "hot_mask": hot_mask, "warmed_up": True,
                       "fight_z": fight_z, "stampede_z": stampede_z,
                       "composite_z": composite_z, "danger_s": self.danger_timer,
                       "age_s": self.baseline.age_s}
            return label, metrics

    # ── Fonctions de dessin (identiques à lab3.py) ────────────────────────────
    def draw_grid_overlay(frame, hot_mask, cell_mags, cell_cohs, label):
        fh, fw = frame.shape[:2]
        for r in range(GRID_ROWS):
            for c in range(GRID_COLS):
                y0, y1 = int(r*fh/GRID_ROWS), int((r+1)*fh/GRID_ROWS)
                x0, x1 = int(c*fw/GRID_COLS), int((c+1)*fw/GRID_COLS)
                m = cell_mags[r, c]; ch = cell_cohs[r, c]
                if m < 0.05: continue
                is_hot = bool(hot_mask[r, c])
                if label in ("FIGHT", "STAMPEDE") and is_hot:
                    color = (30, 30, 200)
                elif ch > CELL_COHERENCE_CELEB_THRESH:
                    color = (0, 180, 180)
                elif is_hot:
                    color = (0, 100, 180)
                else:
                    color = (40, 60, 40)
                alpha = min(0.18 + m * 0.10, 0.50)
                ov = frame[y0:y1, x0:x1].copy()
                cv2.rectangle(ov, (0,0), (x1-x0, y1-y0), color, -1)
                cv2.addWeighted(ov, alpha, frame[y0:y1, x0:x1], 1-alpha, 0, frame[y0:y1, x0:x1])
                cv2.rectangle(frame, (x0, y0), (x1, y1), color, 1)

    def draw_main_label(frame, label, metrics):
        fh, fw = frame.shape[:2]
        st = LABEL_STYLE[label]
        ov = frame.copy()
        cv2.rectangle(ov, (0, 0), (fw, 56), st["bg_color"], -1)
        cv2.addWeighted(ov, 0.7, frame, 0.3, 0, frame)
        if st["border"]:
            cv2.rectangle(frame, (0, 0), (fw, 56), st["bar_color"], 3)
        cv2.putText(frame, st["text"], (12, 36),
                    cv2.FONT_HERSHEY_DUPLEX, 1.1, st["text_color"], 2)
        cv2.putText(frame, st["desc"], (fw//2 - 80, 50),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.37, st["bar_color"], 1)
        if metrics.get("warmed_up", False):
            prog = 1.0
        else:
            prog = min(metrics.get("age_s", 0) / BASELINE_WARMUP_S, 1.0)
        bar_w = int(fw * prog)
        cv2.rectangle(frame, (0, 54), (bar_w, 56), st["bar_color"], -1)

    def draw_signal_panel(frame, metrics):
        fh, fw = frame.shape[:2]
        panel_x = fw - 185
        bg = frame.copy()
        cv2.rectangle(bg, (panel_x-4, 60), (fw, 60+len(SIGNAL_WEIGHTS)*20+4),
                      (15, 15, 15), -1)
        cv2.addWeighted(bg, 0.6, frame, 0.4, 0, frame)
        for i, (k, w) in enumerate(SIGNAL_WEIGHTS.items()):
            val  = metrics.get(k, 0.0)
            z    = metrics.get(k, 0.0)
            col  = (80,200,80) if w > 0 else (80,80,200)
            bar  = int(abs(z) * 15)
            y    = 76 + i * 20
            cv2.rectangle(frame, (panel_x, y-10), (panel_x + min(bar,80), y-2), col, -1)
            cv2.putText(frame, f"{k[:9]:<9} {val:.2f}", (panel_x, y-2),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.28, (160,160,160), 1)

    def draw_vectors(frame, flow, scale):
        h, w = flow.shape[:2]
        step = max(1, int(VECTOR_STEP / scale))
        for y in range(0, h, step):
            for x in range(0, w, step):
                fx = flow[y, x, 0]; fy = flow[y, x, 1]
                mg = np.sqrt(fx**2 + fy**2)
                if mg < 0.3: continue
                x0 = int(x * scale); y0 = int(y * scale)
                x1 = int(x0 + fx * scale * VECTOR_SCALE)
                y1_v = int(y0 + fy * scale * VECTOR_SCALE)
                t = min(1.0, mg / 6.0)
                cv2.arrowedLine(frame, (x0, y0), (x1, y1_v),
                                (int(255*(1-t)), 60, int(255*t)), 1, tipLength=0.3)

    def draw_controls(frame):
        h, w = frame.shape[:2]
        cv2.rectangle(frame, (0, h-24), (w, h), (15,15,15), -1)
        cv2.putText(frame,
                    "  [V] vectors    [G] grid    [R] reset    [T] test    [Q] quit",
                    (8, h-8), cv2.FONT_HERSHEY_SIMPLEX, 0.37, (110,110,110), 1)

    # ── Scoring (identique à lab3.py) ─────────────────────────────────────────
    def get_motion_score(label, danger_timer, fight_z, stampede_z, warmed_up):
        if not warmed_up or label == "LEARNING":
            return 0, 0.0
        base_scores = {"CALM":10,"CELEBRATION":30,"FIGHT":70,"STAMPEDE":85}
        base_conf   = {"CALM":0.9,"CELEBRATION":0.85,"FIGHT":0.7,"STAMPEDE":0.75}
        score = base_scores.get(label, 20)
        conf  = base_conf.get(label, 0.8)
        if label == "FIGHT":
            score += min((fight_z - ALERT_ZSCORE_FIGHT)*5, 20) if fight_z > ALERT_ZSCORE_FIGHT else 0
        elif label == "STAMPEDE":
            score += min((stampede_z - ALERT_ZSCORE_STAMPEDE)*4, 15) if stampede_z > ALERT_ZSCORE_STAMPEDE else 0
        if danger_timer > 2.0:
            conf = min(conf + 0.15, 1.0)
        return min(score, 100), round(conf, 2)

    def get_output_dict(label, metrics):
        score, conf = get_motion_score(
            label, metrics.get("danger_s",0), metrics.get("fight_z",0),
            metrics.get("stampede_z",0), metrics.get("warmed_up",False))
        return {
            "module": "motion",
            "score":  score,
            "confidence": conf,
            "details": {
                "label":          label,
                "fight_z":        round(metrics.get("fight_z",0),2),
                "stampede_z":     round(metrics.get("stampede_z",0),2),
                "composite_z":    round(metrics.get("composite_z",0),2),
                "danger_seconds": round(metrics.get("danger_s",0),1),
                "baseline_age":   round(metrics.get("age_s",0),0)
            },
            "timestamp": time.time()
        }

    # ── Init ──────────────────────────────────────────────────────────────────
    classifier   = MotionClassifier()
    prev_gray    = None
    show_vectors = True; show_grid = True; test_mode = False
    scale_f      = 1.0 / FLOW_SCALE
    last_time    = time.time(); frame_count = 0

    print("[Lab3] Démarré — Crowd Motion Classifier")

    while not stop_event.is_set():
        try:
            frame = q_lab3.get(timeout=1.0)
        except queue.Empty:
            continue

        fh, fw = frame.shape[:2]
        now = time.time(); dt = max(now - last_time, 0.001); last_time = now

        small = cv2.resize(frame, (0,0), fx=FLOW_SCALE, fy=FLOW_SCALE)
        gray  = cv2.cvtColor(small, cv2.COLOR_BGR2GRAY)
        if prev_gray is None or prev_gray.shape != gray.shape:
            prev_gray = gray; continue

        flow = cv2.calcOpticalFlowFarneback(
            prev_gray, gray, None, pyr_scale=0.5, levels=FLOW_LEVELS,
            winsize=FLOW_WINSIZE, iterations=FLOW_ITERATIONS,
            poly_n=FLOW_POLY_N, poly_sigma=FLOW_POLY_SIGMA, flags=0)
        prev_gray = gray

        label, metrics = classifier.classify(flow, fh, fw)

        if show_grid:
            draw_grid_overlay(frame, metrics["hot_mask"],
                              metrics["cell_mags"], metrics["cell_cohs"], label)
        if show_vectors:
            comp_flow = flow.copy()
            comp_flow[...,0] -= metrics["cam_dx"]
            comp_flow[...,1] -= metrics["cam_dy"]
            draw_vectors(frame, comp_flow, scale_f)

        draw_main_label(frame, label, metrics)
        draw_signal_panel(frame, metrics)
        draw_controls(frame)

        # ── Stocker la frame pour le streaming MJPEG ─────────────────────
        global latest_frame_lab3
        _, jpeg = cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, 75])
        with lock_lab3:
            latest_frame_lab3 = jpeg.tobytes()

        if not HEADLESS_MODE:
            cv2.imshow("LAB 3 v5 — Adaptive Crowd Classifier", frame)

        frame_count += 1
        if frame_count % 15 == 0:
            output = get_output_dict(label, metrics)
            print(json.dumps(output, ensure_ascii=False))
            with open("output/motion_score.json","w") as f:
                json.dump(output, f)

        if not HEADLESS_MODE:
            key = cv2.waitKey(1) & 0xFF
            if key == ord('q'):
                stop_event.set()
            elif key == ord('v'):
                show_vectors = not show_vectors
            elif key == ord('g'):
                show_grid = not show_grid
            elif key == ord('r'):
                classifier = MotionClassifier()
                print("\n[Lab3] Baseline reset")

    print("[Lab3] Arrêté.")


# ═══════════════════════════════════════════════════════════════════════════════
# SERVEUR FLASK — Streaming MJPEG + API JSON
# ═══════════════════════════════════════════════════════════════════════════════
from flask import Flask, Response, jsonify, request, send_file
from flask_cors import CORS

flask_app = Flask(__name__)
CORS(flask_app, resources={r"/api/*": {"origins": "*"}})

OUTPUT_DIR = "output"
ROBOT_AUDIO_DIR = os.path.join(OUTPUT_DIR, "audio_prompts")
AUDIO_EVENT_FILES = {
    "welcome": "bienvenu.wav",
    "obstacle": "attention_liberer_passage.wav",
    "gas_emergency": "alerte.wav",
    "ai_alert": "Incident.wav",
}

ESP32_AUDIO_SCORE_MAP = {
    "silence": 0.0,
    "chants supportaires": 30.0,
    "chants_supportaires": 30.0,
    "bagarre": 75.0,
    "bombes": 95.0,
}


def _normalize_esp32_timestamp(ts_value):
    """
    Normalize incoming ESP32 timestamp into server epoch seconds.
    ESP32 may send uptime seconds (millis/1000), which is not epoch.
    """
    now = time.time()
    try:
        ts = float(ts_value)
    except (TypeError, ValueError):
        return now
    # Values far below epoch are treated as uptime seconds.
    if ts < 1_600_000_000:
        return now
    # Guard against clock skew in the far future.
    if ts > now + 300:
        return now
    return ts


def _to_bool(value):
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value != 0
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "y", "on", "detected"}
    return False


def read_json_file(filename):
    path = os.path.join(OUTPUT_DIR, filename)
    if not os.path.exists(path):
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, PermissionError, IOError):
        return None


def write_json_file(filename, payload):
    path = os.path.join(OUTPUT_DIR, filename)
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)


def get_robot_audio_path(event_name):
    filename = AUDIO_EVENT_FILES.get(event_name)
    if filename is None:
        return None
    # 1) Preferred location
    preferred = os.path.join(ROBOT_AUDIO_DIR, filename)
    if os.path.exists(preferred):
        return preferred

    # 2) Backward-compatible: project root fallback
    project_root = Path(__file__).resolve().parent.parent
    root_candidate = project_root / filename
    if root_candidate.exists():
        return str(root_candidate)

    # 3) Optional extension fallback (.wav/.aac/.mp3) in both folders
    stem = Path(filename).stem
    for ext in (".wav", ".aac", ".mp3"):
        p1 = os.path.join(ROBOT_AUDIO_DIR, stem + ext)
        if os.path.exists(p1):
            return p1
        p2 = project_root / f"{stem}{ext}"
        if p2.exists():
            return str(p2)

    # Keep preferred expected path for clear 404 diagnostics
    return preferred


def _wav_is_esp32_friendly(path: str):
    """
    Returns (ok, details_dict).
    ESP32 expects: WAV PCM unsigned 8-bit, mono, 16000Hz.
    """
    try:
        import wave
        with wave.open(path, "rb") as wf:
            channels = int(wf.getnchannels())
            sample_rate = int(wf.getframerate())
            sampwidth = int(wf.getsampwidth())  # bytes per sample
            comptype = str(wf.getcomptype())
        details = {
            "channels": channels,
            "sample_rate": sample_rate,
            "sample_width_bytes": sampwidth,
            "compression": comptype,
        }
        ok = (comptype == "NONE" and channels == 1 and sample_rate == 16000 and sampwidth == 1)
        return ok, details
    except Exception as exc:
        return False, {"error": f"wav_probe_failed: {exc}"}


def _generate_u8_wav_beep(sr: int = 16000, duration_s: float = 0.65, freq_hz: int = 880, amp: float = 0.70) -> bytes:
    """
    Generate a short WAV beep: PCM unsigned 8-bit, mono, sr Hz.
    Returns full WAV file bytes (header + data).
    """
    try:
        import wave
        n = max(1, int(sr * max(0.05, float(duration_s))))
        amp = max(0.0, min(float(amp), 1.0))
        buf = bytearray(n)
        for i in range(n):
            t = i / sr
            s = math.sin(2.0 * math.pi * float(freq_hz) * t)
            v = int(128 + (127 * amp * s))
            buf[i] = max(0, min(255, v))
        out = io.BytesIO()
        with wave.open(out, "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(1)  # 8-bit
            wf.setframerate(sr)
            wf.writeframes(bytes(buf))
        return out.getvalue()
    except Exception:
        # Ultra-safe fallback: 200ms of near-silence
        import wave
        out = io.BytesIO()
        with wave.open(out, "wb") as wf:
            wf.setnchannels(1); wf.setsampwidth(1); wf.setframerate(sr)
            wf.writeframes(bytes([128] * int(sr * 0.2)))
        return out.getvalue()


def _transcode_wav_to_esp32_u8_bytes(path: str, target_sr: int = 16000) -> bytes:
    """
    Convert a WAV file to ESP32-friendly WAV bytes:
    PCM unsigned 8-bit, mono, target_sr Hz.

    This is a pure-Python fallback for WAV inputs (no ffmpeg needed).
    It supports common PCM WAVs (8/16/24/32-bit) and will try best-effort
    downmix + resample.
    """
    import wave
    import audioop

    with wave.open(path, "rb") as wf:
        nch = int(wf.getnchannels())
        sr = int(wf.getframerate())
        sw = int(wf.getsampwidth())  # bytes per sample
        comptype = str(wf.getcomptype())
        if comptype != "NONE":
            raise ValueError(f"unsupported_wav_compression:{comptype}")

        frames = wf.readframes(wf.getnframes())

    if nch == 2:
        frames = audioop.tomono(frames, sw, 0.5, 0.5)
        nch = 1
    elif nch != 1:
        raise ValueError(f"unsupported_channels:{nch}")

    if sr != int(target_sr):
        frames, _ = audioop.ratecv(frames, sw, 1, sr, int(target_sr), None)
        sr = int(target_sr)

    # Convert sample width to 8-bit (signed) then bias to unsigned.
    if sw != 1:
        frames = audioop.lin2lin(frames, sw, 1)
        sw = 1

    # audioop 8-bit samples are signed (-128..127). ESP32 expects unsigned (0..255).
    raw = frames
    u8 = bytes(((b + 128) & 0xFF) for b in raw)

    out = io.BytesIO()
    with wave.open(out, "wb") as ow:
        ow.setnchannels(1)
        ow.setsampwidth(1)
        ow.setframerate(sr)
        ow.writeframes(u8)
    return out.getvalue()


def normalize_esp32_audio_payload(payload):
    if not isinstance(payload, dict):
        raise ValueError("Payload must be a JSON object")

    audio = payload.get("audio")
    if not isinstance(audio, dict):
        raise ValueError("Missing 'audio' object")

    raw_label = str(audio.get("label", "silence")).strip()
    norm_label = raw_label.lower()
    if not norm_label:
        norm_label = "silence"

    confidence = float(audio.get("confidence", 0.0))
    score = float(audio.get("score", ESP32_AUDIO_SCORE_MAP.get(norm_label, 0.0)))
    timestamp = _normalize_esp32_timestamp(payload.get("timestamp"))

    normalized = {
        "module": "audio",
        "score": score,
        "confidence": max(0.0, min(confidence, 1.0)),
        "details": {
            "class_id": int(audio.get("class_id", -1)),
            "label": norm_label,
            "status": "active",
            "source": "esp32",
            "device_id": payload.get("device_id", "esp32-unknown"),
            "rms": round(float(audio.get("rms", 0.0)), 4),
            "centroid_hz": round(float(audio.get("centroid_hz", 0.0)), 1),
            "zcr": round(float(audio.get("zcr", 0.0)), 4),
        },
        "timestamp": timestamp,
    }
    return normalized


def normalize_esp32_gas_payload(payload):
    if not isinstance(payload, dict):
        raise ValueError("Payload must be a JSON object")

    gas = payload.get("gas")
    if not isinstance(gas, dict):
        raise ValueError("Missing 'gas' object")

    confidence = float(gas.get("confidence", 0.0))
    sensor_ppm = float(gas.get("sensor_ppm", gas.get("ppm", 0.0)))
    detected = _to_bool(gas.get("detected", sensor_ppm >= 250.0))
    score = float(gas.get("score", 75.0 if detected else 0.0))
    timestamp = _normalize_esp32_timestamp(payload.get("timestamp"))

    normalized = {
        "module": "smoke",
        "score": max(0.0, min(score, 100.0)),
        "confidence": max(0.0, min(confidence, 1.0)),
        "details": {
            "detected": detected,
            "sensor_ppm": round(sensor_ppm, 2),
            "status": "active",
            "source": "esp32",
            "device_id": payload.get("device_id", "esp32-unknown"),
        },
        "timestamp": timestamp,
        "iso_time": datetime.now().isoformat(),
    }
    return normalized


def generate_mjpeg(lock, get_frame):
    """Générateur MJPEG pour un lab donné."""
    while not stop_event.is_set():
        with lock:
            frame_bytes = get_frame()
        if frame_bytes is None:
            time.sleep(0.05)
            continue
        yield (b'--frame\r\n'
               b'Content-Type: image/jpeg\r\n\r\n' + frame_bytes + b'\r\n')
        time.sleep(0.03)  # ~30 fps max


@flask_app.route('/api/stream/lab1')
def stream_lab1():
    return Response(
        generate_mjpeg(lock_lab1, lambda: latest_frame_lab1),
        mimetype='multipart/x-mixed-replace; boundary=frame'
    )

@flask_app.route('/api/stream/lab2')
def stream_lab2():
    return Response(
        generate_mjpeg(lock_lab2, lambda: latest_frame_lab2),
        mimetype='multipart/x-mixed-replace; boundary=frame'
    )

@flask_app.route('/api/stream/lab3')
def stream_lab3():
    return Response(
        generate_mjpeg(lock_lab3, lambda: latest_frame_lab3),
        mimetype='multipart/x-mixed-replace; boundary=frame'
    )


@flask_app.route('/api/health')
def health():
    return jsonify({
        "status": "ok",
        "service": "StadiumGuard Camera + Streaming Server",
        "version": "2.0.0",
        "timestamp": time.time(),
        "iso_time": datetime.now().isoformat(),
        "streams": {
            "lab1": latest_frame_lab1 is not None,
            "lab2": latest_frame_lab2 is not None,
            "lab3": latest_frame_lab3 is not None
        },
        "headless_mode": HEADLESS_MODE
    })


@flask_app.route('/api/alert')
def get_alert():
    data = read_json_file("final_alert.json")
    if data is None:
        return jsonify({"error": "Alert data not available"}), 503
    data["is_stale"] = (time.time() - data.get("timestamp", 0)) > 5.0
    return jsonify(data)


@flask_app.route('/api/person')
def get_person():
    data = read_json_file("person_score.json")
    if data is None:
        return jsonify({"error": "Person data not available"}), 503
    return jsonify(data)


@flask_app.route('/api/fall')
def get_fall():
    data = read_json_file("fall_score.json")
    if data is None:
        return jsonify({"error": "Fall data not available"}), 503
    return jsonify(data)


@flask_app.route('/api/motion')
def get_motion():
    data = read_json_file("motion_score.json")
    if data is None:
        return jsonify({"error": "Motion data not available"}), 503
    return jsonify(data)


@flask_app.route('/api/audio')
def get_audio():
    data = read_json_file("audio_score.json")
    if data is None:
        return jsonify({"error": "Audio data not available"}), 503
    return jsonify(data)


@flask_app.route('/api/esp32/audio', methods=['POST'])
def ingest_esp32_audio():
    payload = request.get_json(silent=True)
    if payload is None:
        return jsonify({"error": "Invalid or missing JSON body"}), 400

    try:
        normalized = normalize_esp32_audio_payload(payload)
        write_json_file("audio_score.json", normalized)
    except (ValueError, TypeError):
        return jsonify({"error": "Invalid ESP32 audio payload format"}), 400
    except Exception as exc:
        return jsonify({"error": f"Failed to store ESP32 audio data: {exc}"}), 500

    return jsonify({
        "status": "ok",
        "message": "ESP32 audio ingested",
        "label": normalized["details"]["label"],
        "score": normalized["score"],
        "timestamp": normalized["timestamp"],
    }), 200


@flask_app.route('/api/esp32/gas', methods=['POST'])
def ingest_esp32_gas():
    payload = request.get_json(silent=True)
    if payload is None:
        return jsonify({"error": "Invalid or missing JSON body"}), 400

    try:
        normalized = normalize_esp32_gas_payload(payload)
        write_json_file("smoke_score.json", normalized)
    except (ValueError, TypeError):
        return jsonify({"error": "Invalid ESP32 gas payload format"}), 400
    except Exception as exc:
        return jsonify({"error": f"Failed to store ESP32 gas data: {exc}"}), 500

    return jsonify({
        "status": "ok",
        "message": "ESP32 gas ingested",
        "detected": normalized["details"]["detected"],
        "score": normalized["score"],
        "timestamp": normalized["timestamp"],
    }), 200


@flask_app.route('/api/robot/audio-events')
def robot_audio_events():
    os.makedirs(ROBOT_AUDIO_DIR, exist_ok=True)
    events = {}
    for event_name, filename in AUDIO_EVENT_FILES.items():
        resolved_path = get_robot_audio_path(event_name)
        events[event_name] = {
            "file": filename,
            "exists": bool(resolved_path and os.path.exists(resolved_path)),
            "resolved_path": str(resolved_path) if resolved_path else None,
            "url": f"/api/robot/audio-stream?event={event_name}",
        }

    return jsonify({
        "status": "ok",
        "directory": ROBOT_AUDIO_DIR,
        "required_format": "aac/mp3/wav accepted (server transcodes to wav pcm mono 8-bit 16000Hz)",
        "events": events,
    })


@flask_app.route('/api/robot/audio-stream')
def robot_audio_stream():
    event_name = str(request.args.get("event", "welcome")).strip().lower()
    audio_path = get_robot_audio_path(event_name)
    if audio_path is None:
        return jsonify({
            "error": "Unknown event",
            "supported_events": sorted(AUDIO_EVENT_FILES.keys()),
        }), 400

    if not os.path.exists(audio_path):
        # Fallback to a short beep so the ESP32 pipeline can be validated quickly.
        # Still keep the expected path in a response header for debugging.
        freq_map = {
            "welcome": 880,
            "obstacle": 1320,
            "gas_emergency": 1760,
            "ai_alert": 990,
        }
        wav_bytes = _generate_u8_wav_beep(freq_hz=freq_map.get(event_name, 880))
        resp = Response(wav_bytes, mimetype="audio/wav")
        resp.headers["X-StadiumGuard-Audio-Fallback"] = "1"
        resp.headers["X-StadiumGuard-Expected-Path"] = str(audio_path)
        return resp

    # If already WAV, serve directly only if it's ESP32-friendly.
    # Otherwise transcode as well (many WAV files are 16-bit PCM, which the ESP32 client rejects).
    if audio_path.lower().endswith(".wav"):
        ok, details = _wav_is_esp32_friendly(audio_path)
        if ok:
            return send_file(
                audio_path,
                mimetype="audio/wav",
                as_attachment=False,
                conditional=True,
            )
        # Try pure-python conversion first (no ffmpeg needed for WAV).
        try:
            wav_bytes = _transcode_wav_to_esp32_u8_bytes(audio_path, target_sr=16000)
            resp = Response(wav_bytes, mimetype="audio/wav")
            resp.headers["X-StadiumGuard-Audio-PyTranscode"] = "1"
            resp.headers["X-StadiumGuard-Input-Wav"] = os.path.basename(audio_path)
            return resp
        except Exception as exc:
            # fallthrough to ffmpeg if available (covers edge cases + non-PCM wav variants)
            pass

    # Convert on-the-fly to ESP32-friendly WAV:
    # PCM unsigned 8-bit, mono, 16kHz (requires ffmpeg)
    cmd = [
        "ffmpeg",
        "-v", "error",
        "-i", audio_path,
        "-f", "wav",
        "-acodec", "pcm_u8",
        "-ac", "1",
        "-ar", "16000",
        "pipe:1",
    ]
    try:
        proc = subprocess.run(cmd, capture_output=True, check=True)
    except FileNotFoundError:
        return jsonify({
            "error": "ffmpeg not found on server",
            "hint": "Install ffmpeg or provide preconverted wav files (mono, 8-bit unsigned PCM, 16000Hz)",
            "input_file": audio_path,
            "input_wav_details": (_wav_is_esp32_friendly(audio_path)[1]
                                  if audio_path.lower().endswith(".wav") else None),
        }), 500
    except subprocess.CalledProcessError as exc:
        return jsonify({
            "error": "ffmpeg conversion failed",
            "details": exc.stderr.decode("utf-8", errors="ignore")[:400],
            "input_file": audio_path,
            "input_wav_details": (_wav_is_esp32_friendly(audio_path)[1]
                                  if audio_path.lower().endswith(".wav") else None),
        }), 500

    return Response(proc.stdout, mimetype="audio/wav")


@flask_app.route('/api/smoke')
def get_smoke():
    data = read_json_file("smoke_score.json")
    if data is None:
        return jsonify({"error": "Smoke data not available"}), 503
    return jsonify(data)


@flask_app.route('/api/context')
def get_context():
    data = read_json_file("match_context.json")
    if data is None:
        return jsonify({"error": "Context data not available"}), 503
    return jsonify(data)


def flask_thread():
    """Lance Flask dans un thread séparé."""
    flask_app.run(host='0.0.0.0', port=5000, debug=False, threaded=True)


# ═══════════════════════════════════════════════════════════════════════════════
# POINT D'ENTRÉE
# ═══════════════════════════════════════════════════════════════════════════════
if __name__ == "__main__":
    print("=" * 62)
    print("  StadiumGuard — Orchestrateur + Streaming MJPEG")
    print("  Lab1: Person Tracking | Lab2: Fall Detection | Lab3: Motion")
    print(f"  Mode : {'Headless (web only)' if HEADLESS_MODE else 'Fenêtres + Web'}")
    print(f"  Streaming sur : http://localhost:5000")
    print("  Ctrl+C pour arrêter")
    print("=" * 62)

    threads = [
        threading.Thread(target=flask_thread, name="Flask",   daemon=True),
        threading.Thread(target=camera_thread, name="Camera", daemon=True),
        threading.Thread(target=lab1_thread,   name="Lab1",   daemon=True),
        threading.Thread(target=lab2_thread,   name="Lab2",   daemon=True),
        threading.Thread(target=lab3_thread,   name="Lab3",   daemon=True),
    ]

    for t in threads:
        t.start()

    print("\n[Main] Endpoints de streaming :")
    print("  • http://localhost:5000/api/stream/lab1  (Person Tracking)")
    print("  • http://localhost:5000/api/stream/lab2  (Fall Detection)")
    print("  • http://localhost:5000/api/stream/lab3  (Motion Classifier)")
    print("  • http://localhost:5000/api/health")
    print()

    try:
        while not stop_event.is_set():
            time.sleep(0.5)
    except KeyboardInterrupt:
        print("\n[Main] Interruption clavier — arrêt...")
        stop_event.set()

    for t in threads:
        t.join(timeout=5)

    if not HEADLESS_MODE:
        cv2.destroyAllWindows()
    print("[Main] Tous les modules arrêtés. Au revoir.")