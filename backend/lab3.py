#!/usr/bin/env python
# coding: utf-8

# In[1]:
import os

# lab3_motion_classifier.py — VERSION NORMALISÉE
import cv2
import numpy as np
import time
from collections import deque
import json  # ← NOUVEAU

# ─────────────────────────────────────────────────────────────
# CONFIG (inchangé — copier depuis ton code original)
# ─────────────────────────────────────────────────────────────
FLOW_SCALE = 0.5; FLOW_LEVELS = 3; FLOW_WINSIZE = 15
FLOW_ITERATIONS = 3; FLOW_POLY_N = 5; FLOW_POLY_SIGMA = 1.2
GRID_COLS = 8; GRID_ROWS = 6; CAM_COMP_SMOOTHING = 0.55
BASELINE_WARMUP_S = 30.0; BASELINE_WINDOW_S = 120.0
BASELINE_FPS_EST = 25; BASELINE_MIN_STD = 0.05
FREEZE_ZSCORE_THRESH = 2.5; FREEZE_RELEASE_S = 10.0
ALERT_ZSCORE_FIGHT = 4.5; ALERT_ZSCORE_STAMPEDE = 5.0
SIGNAL_WEIGHTS = {
    "h_ratio":2.0, "spikiness":2.0, "spike":2.5,
    "smoothness":-2.0, "hot_coh":-2.5, "rhythm":-3.0,
    "coherence":3.5, "mean_mag":1.5
}
CELL_COHERENCE_CELEB_THRESH = 0.55; CELL_COHERENCE_FIGHT_THRESH = 0.30
RHYTHM_MIN_PERIOD_FRAMES = 8; RHYTHM_MAX_PERIOD_FRAMES = 90
SPIKE_WINDOW_S = 0.6; SPIKE_RISE_THRESH = 2.5
HISTORY_FRAMES = 20; SMOOTH_ALPHA = 0.20
ALERT_FIGHT_S = 4.0; ALERT_STAMP_S = 5.0
VECTOR_SCALE = 4.0; VECTOR_STEP = 30

LABEL_STYLE = {
    "LEARNING":{"text":"LEARNING...","desc":"Building baseline","bar_color":(180,180,60),"bg_color":(30,30,0),"text_color":(220,210,60),"border":False},
    "CALM":{"text":"CALM","desc":"No unusual activity","bar_color":(60,200,60),"bg_color":(15,40,15),"text_color":(60,230,60),"border":False},
    "CELEBRATION":{"text":"CELEBRATION","desc":"Fans cheering","bar_color":(0,210,210),"bg_color":(0,40,40),"text_color":(0,220,220),"border":False},
    "FIGHT":{"text":"FIGHT DETECTED","desc":"Localized violent motion","bar_color":(0,50,220),"bg_color":(40,0,0),"text_color":(60,80,255),"border":True},
    "STAMPEDE":{"text":"STAMPEDE","desc":"Mass directional movement","bar_color":(0,130,255),"bg_color":(0,20,50),"text_color":(40,160,255),"border":True},
}

# ─────────────────────────────────────────────────────────────
# NOUVEAU : Fonctions de normalisation de sortie
# ─────────────────────────────────────────────────────────────
def get_motion_score(label, danger_timer, fight_z, stampede_z, warmed_up):
    """
    Mappe le label + métriques vers un score 0-100.
    - LEARNING : 0 (pas encore fiable)
    - CALM : 0-20
    - CELEBRATION : 20-40 (attendu, pas dangereux)
    - FIGHT : 60-90 (selon fight_z et danger_timer)
    - STAMPEDE : 80-100 (selon stampede_z et danger_timer)
    """
    if not warmed_up or label == "LEARNING":
        return 0, 0.0
    
    base_scores = {"CALM":10, "CELEBRATION":30, "FIGHT":70, "STAMPEDE":85}
    base_conf = {"CALM":0.9, "CELEBRATION":0.85, "FIGHT":0.7, "STAMPEDE":0.75}
    
    score = base_scores.get(label, 20)
    conf = base_conf.get(label, 0.8)
    
    # Ajuste selon l'intensité du signal Z
    if label == "FIGHT":
        score += min((fight_z - ALERT_ZSCORE_FIGHT) * 5, 20) if fight_z > ALERT_ZSCORE_FIGHT else 0
    elif label == "STAMPEDE":
        score += min((stampede_z - ALERT_ZSCORE_STAMPEDE) * 4, 15) if stampede_z > ALERT_ZSCORE_STAMPEDE else 0
    
    # Ajuste selon le danger_timer (plus c'est soutenu, plus c'est confiant)
    if danger_timer > 2.0:
        conf = min(conf + 0.15, 1.0)
    
    return min(score, 100), round(conf, 2)


def get_output_dict(label, metrics):
    score, conf = get_motion_score(
        label, 
        metrics.get("danger_s", 0), 
        metrics.get("fight_z", 0), 
        metrics.get("stampede_z", 0),
        metrics.get("warmed_up", False)
    )
    
    return {
        "module": "motion",
        "score": score,
        "confidence": conf,
        "details": {
            "label": label,
            "fight_z": round(metrics.get("fight_z", 0), 2),
            "stampede_z": round(metrics.get("stampede_z", 0), 2),
            "composite_z": round(metrics.get("composite_z", 0), 2),
            "danger_seconds": round(metrics.get("danger_s", 0), 1),
            "baseline_age": round(metrics.get("age_s", 0), 0)
        },
        "timestamp": time.time()
    }
# ─────────────────────────────────────────────────────────────

# ─────────────────────────────────────────────────────────────
# HELPERS & CLASSES (inchangés — copier depuis ton code original)
# ─────────────────────────────────────────────────────────────
def safe(v): return float(np.nan_to_num(v, nan=0.0, posinf=0.0, neginf=0.0))
def safe_clamp(v, lo=0.0, hi=1.0): return float(np.clip(safe(v), lo, hi))
def circular_coherence(angles):
    if len(angles)<2: return 0.0
    return safe(np.sqrt(np.mean(np.sin(angles))**2 + np.mean(np.cos(angles))**2))

class AdaptiveBaseline:
    def __init__(self):
        maxlen = int(BASELINE_WINDOW_S * BASELINE_FPS_EST)
        self._data = {k:deque(maxlen=maxlen) for k in SIGNAL_WEIGHTS}
        self._means = {k:None for k in SIGNAL_WEIGHTS}
        self._stds = {k:BASELINE_MIN_STD for k in SIGNAL_WEIGHTS}
        self._frozen = False; self._freeze_time = 0.0
        self.start_time = time.time(); self.n_samples = 0
    @property
    def age_s(self): return time.time() - self.start_time
    @property
    def warmed_up(self): return self.age_s >= BASELINE_WARMUP_S and self.n_samples >= 30
    @property
    def frozen(self): return self._frozen
    def update(self, signals:dict):
        if self._frozen:
            if time.time()-self._freeze_time > FREEZE_RELEASE_S: self._frozen=False
            return
        for k,v in signals.items():
            if k in self._data: self._data[k].append(safe(v))
        for k in self._data:
            arr = np.array(self._data[k], dtype=np.float32)
            if len(arr)>=5:
                self._means[k] = float(np.mean(arr))
                self._stds[k] = max(float(np.std(arr)), BASELINE_MIN_STD)
        self.n_samples += 1
    def freeze(self):
        if not self._frozen: self._frozen=True; self._freeze_time=time.time()
    def unfreeze(self): self._frozen=False
    def zscore(self, name:str, val:float)->float:
        if self._means[name] is None: return 0.0
        return safe((safe(val)-self._means[name])/self._stds[name])
    def get_stats(self, name:str):
        m,s = self._means[name], self._stds[name]
        return (m if m is not None else 0.0), s

class CameraCompensator:
    def __init__(self): self.gdx=0.0; self.gdy=0.0
    def compensate(self, flow):
        raw_dx=float(np.clip(np.median(flow[...,0]),-20,20))
        raw_dy=float(np.clip(np.median(flow[...,1]),-20,20))
        s=CAM_COMP_SMOOTHING
        self.gdx=s*self.gdx+(1-s)*raw_dx; self.gdy=s*self.gdy+(1-s)*raw_dy
        comp=flow.copy(); comp[...,0]-=self.gdx; comp[...,1]-=self.gdy
        return comp, self.gdx, self.gdy

def compute_axis_ratio(fx,fy,mask):
    if not np.any(mask): return 0.5
    mx,my = safe(np.mean(np.abs(fx[mask]))), safe(np.mean(np.abs(fy[mask])))
    t=mx+my; return mx/t if t>0.01 else 0.5

def compute_cell_grid(fx,fy,fh,fw):
    mag=np.sqrt(fx**2+fy**2); angle=np.arctan2(fy,fx)
    cell_mags=np.zeros((GRID_ROWS,GRID_COLS),dtype=np.float32)
    cell_cohs=np.zeros((GRID_ROWS,GRID_COLS),dtype=np.float32)
    for r in range(GRID_ROWS):
        for c in range(GRID_COLS):
            y0,y1=int(r*fh/GRID_ROWS),int((r+1)*fh/GRID_ROWS)
            x0,x1=int(c*fw/GRID_COLS),int((c+1)*fw/GRID_COLS)
            cm,ca = mag[y0:y1,x0:x1], angle[y0:y1,x0:x1]
            if cm.size==0: continue
            cell_mags[r,c]=float(np.mean(cm))
            mv=cm>0.4
            cell_cohs[r,c]=circular_coherence(ca[mv].ravel()) if mv.sum()>4 else 0.0
    cell_mags=np.nan_to_num(cell_mags,nan=0.0); cell_cohs=np.nan_to_num(cell_cohs,nan=0.0)
    mean_m,max_m = float(np.mean(cell_mags)), float(np.max(cell_mags))
    if mean_m<0.1: return cell_mags,cell_cohs,cell_mags<0,0.0,0.0,0.0
    spikiness=safe(max_m/mean_m)
    hot_thresh=max(mean_m*1.5,0.5); hot_mask=cell_mags>hot_thresh
    hot_ratio=float(np.sum(hot_mask))/(GRID_ROWS*GRID_COLS)
    hot_cohs=cell_cohs[hot_mask]
    mean_hot_coh=float(np.mean(hot_cohs)) if len(hot_cohs)>0 else 0.0
    return cell_mags,cell_cohs,hot_mask,spikiness,hot_ratio,mean_hot_coh

def compute_rhythm(mag_history):
    arr=np.array(mag_history,dtype=np.float32)
    if len(arr)<20: return 0.0
    arr-=np.mean(arr); std=np.std(arr)
    if std<0.01: return 0.0
    arr/=std; n=len(arr)
    corr=np.correlate(arr,arr,mode='full')[n-1:]; corr/=max(corr[0],1e-6)
    search=corr[RHYTHM_MIN_PERIOD_FRAMES:RHYTHM_MAX_PERIOD_FRAMES]
    return safe(float(np.max(search)) if len(search)>0 else 0.0)

class SpikeDetector:
    def __init__(self,fps=25):
        wf=max(4,int(SPIKE_WINDOW_S*fps))
        self.buf=deque(maxlen=wf); self.spike_smooth=0.0; self.smooth_smooth=0.5
    def update(self,mean_mag):
        self.buf.append(mean_mag)
        arr=np.array(self.buf,dtype=np.float32)
        if len(arr)<3: return 0.0,0.5
        deltas=np.diff(arr)
        max_rise=safe_clamp(float(np.max(deltas))/max(SPIKE_RISE_THRESH,0.1))
        delta_std=float(np.std(deltas)); mean_m=float(np.mean(arr))
        smoothness=safe_clamp(1.0-(delta_std/mean_m)) if mean_m>0.2 else 0.5
        a=0.25
        self.spike_smooth=a*max_rise+(1-a)*self.spike_smooth
        self.smooth_smooth=a*smoothness+(1-a)*self.smooth_smooth
        return self.spike_smooth, self.smooth_smooth

def compute_anomaly_score(signals:dict, baseline:AdaptiveBaseline)->dict:
    z_scores={}; fight_z=0.0; stampede_z=0.0
    for name,weight in SIGNAL_WEIGHTS.items():
        val=signals.get(name,0.0); z=baseline.zscore(name,val); z_scores[name]=z
        fight_z+=weight*z
    stampede_z=(SIGNAL_WEIGHTS["coherence"]*z_scores.get("coherence",0.0)*2.0 +
                SIGNAL_WEIGHTS["mean_mag"]*z_scores.get("mean_mag",0.0)*2.0 +
                SIGNAL_WEIGHTS["h_ratio"]*z_scores.get("h_ratio",0.0)*0.5)
    composite_z=float(np.mean([abs(z) for z in z_scores.values()]))
    return {"z_scores":z_scores,"fight_z":safe(fight_z),"stampede_z":safe(stampede_z),"composite_z":safe(composite_z)}

class MotionClassifier:
    def __init__(self):
        self.label_history=deque(maxlen=HISTORY_FRAMES)
        self.mag_history=deque(maxlen=300)
        self.sig={k:0.0 for k in SIGNAL_WEIGHTS}; self.sig["smoothness"]=0.5; self.sig["hot_coh"]=0.5
        self.danger_timer=0.0; self.last_time=time.time()
        self.compensator=CameraCompensator(); self.spike_detector=SpikeDetector()
        self.baseline=AdaptiveBaseline()
    def classify(self,flow_raw,fh,fw):
        now=time.time(); dt=max(now-self.last_time,0.001); self.last_time=now
        flow_comp,gdx,gdy=self.compensator.compensate(flow_raw)
        scale=1.0/FLOW_SCALE; fx=flow_comp[...,0]*scale; fy=flow_comp[...,1]*scale
        mag=np.sqrt(fx**2+fy**2); angle=np.arctan2(fy,fx)
        moving=mag>0.5; mm,am=mag[moving],angle[moving]
        mean_mag=safe(np.mean(mm)) if len(mm)>20 else 0.0
        coherence=circular_coherence(am) if len(am)>20 else 0.0
        self.mag_history.append(mean_mag)
        hratio=compute_axis_ratio(fx,fy,moving)
        cell_mags,cell_cohs,hot_mask,spikiness,hot_ratio,mean_hot_coh=compute_cell_grid(fx,fy,int(fh*FLOW_SCALE),int(fw*FLOW_SCALE))
        rhythm=compute_rhythm(self.mag_history)
        spike,smoothness=self.spike_detector.update(mean_mag)
        raw={"mean_mag":safe(mean_mag),"coherence":safe(coherence),"h_ratio":safe(hratio),
             "spikiness":safe(spikiness),"spike":safe(spike),"smoothness":safe(smoothness),
             "hot_coh":safe(mean_hot_coh),"rhythm":safe(rhythm)}
        a=SMOOTH_ALPHA
        for k in raw: self.sig[k]=a*raw[k]+(1-a)*self.sig.get(k,raw[k])
        smoothed={k:self.sig[k] for k in raw}
        self.baseline.update(smoothed)
        anom=compute_anomaly_score(smoothed,self.baseline)
        fight_z,stampede_z,composite_z=anom["fight_z"],anom["stampede_z"],anom["composite_z"]
        if composite_z>FREEZE_ZSCORE_THRESH: self.baseline.freeze()
        elif composite_z<1.0: self.baseline.unfreeze()
        if not self.baseline.warmed_up: label="LEARNING"
        elif stampede_z>=ALERT_ZSCORE_STAMPEDE and smoothed["coherence"]>0.55: label="STAMPEDE"
        elif fight_z>=ALERT_ZSCORE_FIGHT: label="FIGHT"
        elif fight_z<=-2.0: label="CELEBRATION"
        else: label="CALM"
        self.label_history.append(label)
        counts={k:0 for k in LABEL_STYLE}
        for l in self.label_history: counts[l]=counts.get(l,0)+1
        final=max(counts,key=counts.get)
        if final in ("FIGHT","STAMPEDE"): self.danger_timer+=dt
        else: self.danger_timer=max(0.0,self.danger_timer-dt*2)
        return final,{**smoothed,"danger_s":self.danger_timer,"vote":counts,"hot_mask":hot_mask,
                      "cell_mags":cell_mags,"cell_cohs":cell_cohs,"cam_dx":gdx,"cam_dy":gdy,
                      "fight_z":fight_z,"stampede_z":stampede_z,"composite_z":composite_z,
                      "z_scores":anom["z_scores"],"baseline":self.baseline,
                      "warmed_up":self.baseline.warmed_up,"frozen":self.baseline.frozen,"age_s":self.baseline.age_s}

# Drawing functions (copier depuis ton code original — inchangées)
def draw_main_label(frame, label, metrics):
    h, w  = frame.shape[:2]
    style = LABEL_STYLE[label]

    overlay = frame.copy()
    cv2.rectangle(overlay, (0, 0), (w, 88), style["bg_color"], -1)
    cv2.addWeighted(overlay, 0.88, frame, 0.12, 0, frame)

    if style["border"] and int(time.time() * 2) % 2 == 0:
        cv2.rectangle(frame, (0, 0), (w, h), style["bar_color"], 6)

    # Large centered status text
    font = cv2.FONT_HERSHEY_DUPLEX
    txt  = style["text"]
    (tw, _), _ = cv2.getTextSize(txt, font, 1.5, 3)
    cv2.putText(frame, txt, ((w - tw) // 2, 52), font, 1.5,
                style["text_color"], 3)

    # Description
    desc = style["desc"]
    (dw, _), _ = cv2.getTextSize(desc, cv2.FONT_HERSHEY_SIMPLEX, 0.50, 1)
    cv2.putText(frame, desc, ((w - dw) // 2, 74),
                cv2.FONT_HERSHEY_SIMPLEX, 0.50, style["bar_color"], 1)

    # Learning progress bar
    if label == "LEARNING":
        age    = metrics["age_s"]
        pct    = min(1.0, age / BASELINE_WARMUP_S)
        bar_w  = int((w - 40) * pct)
        cv2.rectangle(frame, (20, 80), (w - 20, 86), (50, 50, 20), -1)
        cv2.rectangle(frame, (20, 80), (20 + bar_w, 86), (180, 210, 60), -1)
        cv2.putText(frame, f"{int(pct*100)}%  ({int(BASELINE_WARMUP_S - age)}s remaining)",
                    (20, 98), cv2.FONT_HERSHEY_SIMPLEX, 0.38, (160, 160, 60), 1)
        return

    # Z-score meters
    fz  = metrics["fight_z"]
    sz  = metrics["stampede_z"]
    cz  = metrics["composite_z"]

    # Fight Z bar
    bar_y = 82
    fz_norm = safe_clamp((fz + 3) / (ALERT_ZSCORE_FIGHT + 3))
    bw      = min(w // 3 - 20, 200)
    bx      = 10
    cv2.rectangle(frame, (bx, bar_y), (bx + bw, bar_y + 8), (40, 40, 40), -1)
    fill_c  = (0, 50, 255) if fz > ALERT_ZSCORE_FIGHT else (100, 100, 200)
    cv2.rectangle(frame, (bx, bar_y), (bx + int(bw * fz_norm), bar_y + 8), fill_c, -1)
    thresh_x = bx + int(bw * safe_clamp(ALERT_ZSCORE_FIGHT / (ALERT_ZSCORE_FIGHT + 3 + 3)))
    cv2.line(frame, (thresh_x, bar_y - 2), (thresh_x, bar_y + 10), (230, 210, 50), 1)
    cv2.putText(frame, f"Fight Z: {fz:+.1f}", (bx, bar_y - 3),
                cv2.FONT_HERSHEY_SIMPLEX, 0.35, (160, 160, 220), 1)

    # Danger timer pill
    danger = metrics["danger_s"]
    if danger > 0.5:
        alert_s = ALERT_FIGHT_S if label == "FIGHT" else ALERT_STAMP_S
        pct     = min(1.0, danger / alert_s)
        pw, px2, py2 = 140, w - 152, 8
        cv2.rectangle(frame, (px2, py2), (px2 + pw, py2 + 18), (40, 40, 40), -1)
        cv2.rectangle(frame, (px2, py2), (px2 + int(pw * pct), py2 + 18),
                      style["bar_color"], -1)
        cv2.putText(frame, f"Alert in {max(0.0, alert_s - danger):.1f}s",
                    (px2 + 4, py2 + 13),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.36, (220, 220, 220), 1)

    # Full alert text
    if style["border"] and danger > (ALERT_FIGHT_S if label == "FIGHT" else ALERT_STAMP_S):
        msg = "!! ALERT SECURITY !!" if label == "FIGHT" else "!! EVACUATE !!"
        (mw, _), _ = cv2.getTextSize(msg, cv2.FONT_HERSHEY_DUPLEX, 0.9, 2)
        cv2.putText(frame, msg, ((w - mw) // 2, h - 18),
                    cv2.FONT_HERSHEY_DUPLEX, 0.9, style["bar_color"], 2)


def draw_signal_panel(frame, metrics):
    """Right panel: Z-score bars + baseline stats + freeze indicator."""
    h, w  = frame.shape[:2]
    px, py, bw = w - 230, 100, 170

    cv2.rectangle(frame, (px - 8, py - 6), (w, py + 330), (16, 16, 16), -1)

    # Freeze / baseline status
    frozen    = metrics.get("frozen", False)
    warmed_up = metrics.get("warmed_up", False)
    age_s     = metrics.get("age_s", 0.0)

    status_txt = "FROZEN" if frozen else ("LEARNING" if not warmed_up else "ADAPTING")
    status_col = (0, 80, 255) if frozen else ((180, 180, 60) if not warmed_up else (60, 180, 60))
    cv2.putText(frame, f"Baseline: {status_txt}  ({age_s:.0f}s)",
                (px, py - 2), cv2.FONT_HERSHEY_SIMPLEX, 0.36, status_col, 1)

    z_scores = metrics.get("z_scores", {})

    def zbar(name, display, y, positive_bad=True):
        """
        Draws a Z-score bar centered at 0.
        positive_bad=True  → right side red  (fight signals)
        positive_bad=False → right side green (calm/celeb signals)
        """
        z   = z_scores.get(name, 0.0)
        z   = safe(z)
        mid = px + bw // 2
        unit = bw // 8   # 1 σ = bw/8 pixels

        # Background
        cv2.rectangle(frame, (px, y), (px + bw, y + 10), (40, 40, 40), -1)
        # Center line
        cv2.line(frame, (mid, y - 1), (mid, y + 11), (100, 100, 100), 1)

        # Fill from center
        fill_px = int(np.clip(z * unit, -bw//2, bw//2))
        if fill_px > 0:
            color = (0, 60, 220) if positive_bad else (60, 200, 60)
            cv2.rectangle(frame, (mid, y), (mid + fill_px, y + 10), color, -1)
        elif fill_px < 0:
            color = (60, 200, 60) if positive_bad else (0, 60, 220)
            cv2.rectangle(frame, (mid + fill_px, y), (mid, y + 10), color, -1)

        # Alert threshold lines
        thresh_z = ALERT_ZSCORE_FIGHT / len(SIGNAL_WEIGHTS)
        tx = int(thresh_z * unit)
        cv2.line(frame, (mid + tx, y-2), (mid + tx, y+12), (230, 210, 50), 1)
        cv2.line(frame, (mid - tx, y-2), (mid - tx, y+12), (230, 210, 50), 1)

        # Baseline mean + current value
        bl = metrics["baseline"]
        bm, bs = bl.get_stats(name)
        cv2.putText(frame, display, (px, y - 2),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.30, (150, 150, 150), 1)
        cv2.putText(frame, f"z:{z:+.1f}  μ:{bm:.2f}±{bs:.2f}",
                    (px + bw // 2 + 4, y + 9),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.28, (170, 170, 170), 1)

    zbar("h_ratio",   "H-ratio      (fight=high)",  py + 16,  positive_bad=True)
    zbar("spikiness", "Spikiness    (fight=high)",  py + 44,  positive_bad=True)
    zbar("spike",     "Spike burst  (fight=high)",  py + 72,  positive_bad=True)
    zbar("smoothness","Smoothness   (celeb=high)",  py + 100, positive_bad=False)
    zbar("hot_coh",   "Hot-cell coh (celeb=high)",  py + 128, positive_bad=False)
    zbar("rhythm",    "Rhythm       (celeb=high)",  py + 156, positive_bad=False)
    zbar("coherence", "Global coh   (stamp=high)",  py + 184, positive_bad=True)
    zbar("mean_mag",  "Magnitude",                  py + 212, positive_bad=True)

    # Composite Z + fight Z totals
    cv2.putText(frame,
                f"Fight Z: {metrics['fight_z']:+.1f}  thresh:{ALERT_ZSCORE_FIGHT:.0f}",
                (px, py + 246), cv2.FONT_HERSHEY_SIMPLEX, 0.33, (160, 160, 220), 1)
    cv2.putText(frame,
                f"Stamp Z: {metrics['stampede_z']:+.1f}  thresh:{ALERT_ZSCORE_STAMPEDE:.0f}",
                (px, py + 262), cv2.FONT_HERSHEY_SIMPLEX, 0.33, (100, 160, 255), 1)
    cv2.putText(frame,
                f"Cam  dx:{metrics['cam_dx']:+.1f}  dy:{metrics['cam_dy']:+.1f}",
                (px, py + 278), cv2.FONT_HERSHEY_SIMPLEX, 0.33, (100, 180, 255), 1)

    v = metrics["vote"]
    cv2.putText(frame,
                f"Vote C:{v.get('CALM',0)} CEL:{v.get('CELEBRATION',0)} F:{v.get('FIGHT',0)} S:{v.get('STAMPEDE',0)}",
                (px, py + 296), cv2.FONT_HERSHEY_SIMPLEX, 0.30, (140, 140, 140), 1)


def draw_grid_overlay(frame, hot_mask, cell_mags, cell_cohs, label):
    h, w  = frame.shape[:2]
    max_m = float(np.max(cell_mags)) if cell_mags.max() > 0 else 1.0
    style = LABEL_STYLE[label]

    for r in range(GRID_ROWS):
        for c in range(GRID_COLS):
            x0 = int(c * w / GRID_COLS); x1 = int((c+1) * w / GRID_COLS)
            y0 = int(r * h / GRID_ROWS); y1 = int((r+1) * h / GRID_ROWS)
            m_int = min(1.0, cell_mags[r, c] / max(max_m, 0.01))
            coh   = cell_cohs[r, c]

            if hot_mask[r, c]:
                ov = frame.copy()
                cv2.rectangle(ov, (x0, y0), (x1, y1), style["bar_color"], -1)
                cv2.addWeighted(ov, 0.22 * m_int, frame, 1 - 0.22 * m_int, 0, frame)
                tint = (0, 180, 60) if coh > CELL_COHERENCE_CELEB_THRESH else \
                       (0, 60, 200) if coh < CELL_COHERENCE_FIGHT_THRESH else None
                if tint:
                    ov2 = frame.copy()
                    cv2.rectangle(ov2, (x0, y0), (x1, y1), tint, -1)
                    cv2.addWeighted(ov2, 0.14, frame, 0.86, 0, frame)
                cv2.rectangle(frame, (x0, y0), (x1, y1), style["bar_color"], 1)
                cv2.putText(frame, f"{coh:.2f}", (x0 + 3, y0 + 13),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.28, (220, 220, 220), 1)
            else:
                cv2.rectangle(frame, (x0, y0), (x1, y1), (38, 38, 38), 1)


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
            y1 = int(y0 + fy * scale * VECTOR_SCALE)
            t  = min(1.0, mg / 6.0)
            cv2.arrowedLine(frame, (x0, y0), (x1, y1),
                            (int(255*(1-t)), 60, int(255*t)), 1, tipLength=0.3)


def draw_controls(frame):
    h, w = frame.shape[:2]
    cv2.rectangle(frame, (0, h - 24), (w, h), (15, 15, 15), -1)
    cv2.putText(frame,
                "  [V] vectors    [G] grid    [R] reset baseline    [T] test    [Q] quit",
                (8, h - 8), cv2.FONT_HERSHEY_SIMPLEX, 0.37, (110, 110, 110), 1)


# ─────────────────────────────────────────────────────────────────
# TEST SIMULATOR
# ─────────────────────────────────────────────────────────────────
class TestSimulator:
    SCENARIOS = [
        {"name": "NORMAL WALKING — horizontal",
         "desc": "You walking left/right. After baseline learns this, should stay CALM.",
         "expected": "CALM"},
        {"name": "CELEBRATION — fans jumping",
         "desc": "Vertical rhythmic motion spread everywhere. Expected: CELEBRATION",
         "expected": "CELEBRATION"},
        {"name": "FIGHT — localized brawl",
         "desc": "Horizontal chaotic bursts, 1 cluster, sudden spikes. Expected: FIGHT",
         "expected": "FIGHT"},
        {"name": "STAMPEDE — mass evacuation",
         "desc": "Strong coherent rightward flow everywhere. Expected: STAMPEDE",
         "expected": "STAMPEDE"},
        {"name": "CAM SHAKE — robot bumps",
         "desc": "Global motion only. After compensation should read CALM.",
         "expected": "CALM"},
    ]

    def __init__(self, h, w):
        self.h   = h; self.w = w
        self.idx = 0; self.t = 0.0

    def next_scenario(self):
        self.idx = (self.idx + 1) % len(self.SCENARIOS)
        self.t   = 0.0

    def generate_flow(self, dt):
        self.t += dt
        h, w   = self.h, self.w
        flow   = np.zeros((h, w, 2), dtype=np.float32)
        name   = self.SCENARIOS[self.idx]["name"].split("—")[0].strip()

        if name == "NORMAL WALKING":
            # Horizontal walking — the system should LEARN this as normal
            flow[..., 0] = 3.0 + np.random.randn(h, w).astype(np.float32) * 0.5
            flow[..., 1] = np.random.randn(h, w).astype(np.float32) * 0.3

        elif name == "CELEBRATION":
            amp = 4.5 * max(0.0, np.sin(2 * np.pi * self.t / 1.2))
            flow[..., 0] = np.random.randn(h, w).astype(np.float32) * 0.3
            flow[..., 1] = -amp + np.random.randn(h, w).astype(np.float32) * 0.4

        elif name == "FIGHT":
            burst_on = (self.t % 0.4) < 0.15
            mask     = np.zeros((h, w), dtype=np.float32)
            mask[:h//3, :w//3] = 1.0
            strength = (8.0 if burst_on else 0.8) * (0.7 + 0.3 * np.random.rand())
            flow[..., 0] = mask * np.random.randn(h, w).astype(np.float32) * strength
            flow[..., 1] = mask * np.random.randn(h, w).astype(np.float32) * strength * 0.5
            flow[..., 0] += np.random.randn(h, w).astype(np.float32) * 0.2
            flow[..., 1] += np.random.randn(h, w).astype(np.float32) * 0.2

        elif name == "STAMPEDE":
            speed = 7.0 + np.sin(self.t) * 0.5
            flow[..., 0] = speed + np.random.randn(h, w).astype(np.float32) * 0.4
            flow[..., 1] = np.random.randn(h, w).astype(np.float32) * 0.4

        elif name == "CAM SHAKE":
            flow[..., 0] = 5.0 * np.sin(2 * np.pi * self.t / 0.5) + \
                           np.random.randn(h, w).astype(np.float32) * 0.3
            flow[..., 1] = 2.0 * np.cos(2 * np.pi * self.t / 0.7) + \
                           np.random.randn(h, w).astype(np.float32) * 0.3

        return flow

    def draw_overlay(self, frame):
        h, w  = frame.shape[:2]
        sc    = self.SCENARIOS[self.idx]
        style = LABEL_STYLE[sc["expected"]]
        ov = frame.copy()
        cv2.rectangle(ov, (0, 0), (w, 106), (30, 20, 0), -1)
        cv2.addWeighted(ov, 0.7, frame, 0.3, 0, frame)
        cv2.putText(frame, "TEST MODE",
                    (10, 22), cv2.FONT_HERSHEY_SIMPLEX, 0.48, (80, 160, 255), 1)
        cv2.putText(frame, f"{self.idx+1}/{len(self.SCENARIOS)}: {sc['name']}",
                    (10, 44), cv2.FONT_HERSHEY_DUPLEX, 0.60, (220, 220, 60), 2)
        cv2.putText(frame, sc["desc"],
                    (10, 64), cv2.FONT_HERSHEY_SIMPLEX, 0.38, (160, 160, 160), 1)
        cv2.putText(frame, f"Expected: {sc['expected']}",
                    (10, 84), cv2.FONT_HERSHEY_SIMPLEX, 0.42, style["bar_color"], 1)
        cv2.putText(frame, "[T] next scenario", (w - 190, 22),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.36, (90, 90, 90), 1)


# ─────────────────────────────────────────────────────────────

# ─────────────────────────────────────────────────────────────
# MAIN LOOP (inchangé sauf ajout sortie normalisée)
# ─────────────────────────────────────────────────────────────
print("="*62)
print("  LAB 3 v5 — ADAPTIVE BASELINE Crowd Classifier")
print("="*62)
print("  R — reset baseline | V — vectors | G — grid | T — test | Q — quit")
print("="*62)

cap=cv2.VideoCapture(0); cap.set(cv2.CAP_PROP_BUFFERSIZE,1)
ret,frame0=cap.read(); fh0,fw0=frame0.shape[:2] if ret else (480,640)
classifier=MotionClassifier()
simulator=TestSimulator(int(fh0*FLOW_SCALE),int(fw0*FLOW_SCALE))
prev_gray=None; show_vectors=True; show_grid=True; test_mode=False
scale_f=1.0/FLOW_SCALE; last_time=time.time(); frame_count=0  # ← NOUVEAU

while cap.isOpened():
    ret,frame=cap.read()
    if not ret: break
    fh,fw=frame.shape[:2]; now=time.time(); dt=max(now-last_time,0.001); last_time=now
    
    if test_mode: flow=simulator.generate_flow(dt)
    else:
        small=cv2.resize(frame,(0,0),fx=FLOW_SCALE,fy=FLOW_SCALE)
        gray=cv2.cvtColor(small,cv2.COLOR_BGR2GRAY)
        if prev_gray is None or prev_gray.shape!=gray.shape: prev_gray=gray; continue
        flow=cv2.calcOpticalFlowFarneback(prev_gray,gray,None,pyr_scale=0.5,levels=FLOW_LEVELS,
                                          winsize=FLOW_WINSIZE,iterations=FLOW_ITERATIONS,
                                          poly_n=FLOW_POLY_N,poly_sigma=FLOW_POLY_SIGMA,flags=0)
        prev_gray=gray
    
    label,metrics=classifier.classify(flow,fh,fw)
    
    if show_grid: draw_grid_overlay(frame,metrics["hot_mask"],metrics["cell_mags"],metrics["cell_cohs"],label)
    if show_vectors:
        comp_flow=flow.copy(); comp_flow[...,0]-=metrics["cam_dx"]; comp_flow[...,1]-=metrics["cam_dy"]
        draw_vectors(frame,comp_flow,scale_f)
    
    draw_main_label(frame,label,metrics)
    draw_signal_panel(frame,metrics)
    if test_mode: simulator.draw_overlay(frame)
    draw_controls(frame)
    
    cv2.imshow("LAB 3 v5 — Adaptive Crowd Classifier",frame)
    
    # ─────────────────────────────────────────────────────────
    # NOUVEAU : Sortie normalisée toutes les 500ms (~15 frames)
    # ─────────────────────────────────────────────────────────
    frame_count += 1
    if frame_count % 15 == 0:
        output = get_output_dict(label, metrics)
        print(json.dumps(output, ensure_ascii=False))
        # Optionnel : 
        with open("output/motion_score.json","w") as f: json.dump(output,f)
    
    key=cv2.waitKey(1)&0xFF
    if key==ord('q'): break
    elif key==ord('v'): show_vectors=not show_vectors
    elif key==ord('g'): show_grid=not show_grid
    elif key==ord('r'): classifier=MotionClassifier(); print("\n[RESET] Baseline cleared")
    elif key==ord('t'):
        if not test_mode: test_mode=True; classifier=MotionClassifier(); print(f"\n[TEST] {simulator.SCENARIOS[0]['name']}")
        else: simulator.next_scenario(); classifier=MotionClassifier(); sc=simulator.SCENARIOS[simulator.idx]; print(f"\n[TEST] {simulator.idx+1}: {sc['name']}")

cap.release(); cv2.destroyAllWindows()

# In[ ]:
