#!/usr/bin/env python3
"""
mic_classifier.py — Classification audio en temps réel via microphone PC

Usage:
    python3 mic_classifier.py              # utilise le micro par défaut
    python3 mic_classifier.py --list       # liste les micros disponibles
    python3 mic_classifier.py --device 2   # utilise le micro n°2

Dépendances:
    pip install sounddevice numpy librosa
"""

import sys
import argparse
import json
import os
import numpy as np
from collections import deque
import time

try:
    import sounddevice as sd
except ImportError:
    print("ERREUR: sounddevice non installé.")
    print("  pip install sounddevice")
    sys.exit(1)

try:
    import librosa
except ImportError:
    print("ERREUR: librosa non installé.")
    print("  pip install librosa numpy")
    sys.exit(1)

# ─── Paramètres identiques à l'ESP32 ──────────────────────────────────────
SAMPLE_RATE       = 16000
FRAME_SIZE        = 512        # samples par fenêtre (~32ms)
VOTE_WINDOW       = 8          # frames pour vote majoritaire (~256ms)
STARTUP_DELAY_SEC = 7.0        # délai avant d'afficher la classe détectée

CENTROID_THRESH_1 = 1107.0
CENTROID_THRESH_2 = 1542.0
CENTROID_THRESH_3 = 2186.0
RMS_NOISE_FLOOR   = 0.010

CLASS_NAMES = ['silence', 'chants supportaires', 'bagarre', 'bombes']
CLASS_ICONS = ['🔇', '🎵', '⚠️ ', '💣']
OUTPUT_DIR = "output"
AUDIO_OUTPUT_FILE = os.path.join(OUTPUT_DIR, "audio_score.json")

# ─── Features ──────────────────────────────────────────────────────────────
def compute_rms(buf):
    return float(np.sqrt(np.mean(buf**2)))

def compute_zcr(buf):
    crossings = np.sum(np.diff(np.sign(buf)) != 0)
    return crossings / (len(buf) - 1)

def compute_spectral_centroid(buf, sr=SAMPLE_RATE):
    fft_mag = np.abs(np.fft.rfft(buf))
    freqs   = np.fft.rfftfreq(len(buf), 1.0/sr)
    mag_sum = np.sum(fft_mag)
    if mag_sum < 1e-8:
        return 0.0
    return float(np.dot(freqs, fft_mag) / mag_sum)

# ─── Classification ────────────────────────────────────────────────────────
def classify_frame(zcr, rms, centroid):
    if rms < RMS_NOISE_FLOOR:
        return 0  # silence
    if centroid < CENTROID_THRESH_1:
        return 0
    elif centroid < CENTROID_THRESH_2:
        return 1
    elif centroid < CENTROID_THRESH_3:
        return 2
    else:
        return 3

# ─── État global ───────────────────────────────────────────────────────────
votes      = [0, 0, 0, 0]
frame_buf  = deque()
frame_count = [0]
last_class  = [-1]
sample_buf  = np.array([], dtype=np.float32)
stream_start_time = [None]

def class_to_score(class_idx):
    """
    Mapping simple classe audio -> score de risque.
    Peut être ajusté plus tard selon vos tests terrain.
    """
    score_map = {
        0: 0.0,    # silence
        1: 30.0,   # chants supportaires
        2: 75.0,   # bagarre
        3: 95.0,   # bombes
    }
    return float(score_map.get(class_idx, 0.0))

def write_audio_output(class_idx, votes_snapshot, rms, centroid):
    total_votes = max(1, int(sum(votes_snapshot)))
    confidence = round(float(max(votes_snapshot)) / total_votes, 2)
    payload = {
        "module": "audio",
        "score": class_to_score(class_idx),
        "confidence": confidence,
        "details": {
            "class_id": int(class_idx),
            "label": CLASS_NAMES[class_idx],
            "status": "active",
            "votes": {
                "silence": int(votes_snapshot[0]),
                "chants_supportaires": int(votes_snapshot[1]),
                "bagarre": int(votes_snapshot[2]),
                "bombes": int(votes_snapshot[3]),
            },
            "rms": round(float(rms), 4),
            "centroid_hz": round(float(centroid), 1),
        },
        "timestamp": time.time(),
    }
    with open(AUDIO_OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)

def write_warming_audio_output(remaining_s):
    payload = {
        "module": "audio",
        "score": 0.0,
        "confidence": 0.0,
        "details": {
            "class_id": 0,
            "label": "silence",
            "status": "warming_up",
            "remaining_s": round(max(0.0, float(remaining_s)), 1),
        },
        "timestamp": time.time(),
    }
    with open(AUDIO_OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)

def audio_callback(indata, frames, time_info, status):
    global sample_buf, votes, frame_count, last_class, stream_start_time

    if status:
        pass  # ignorer erreurs mineures

    # Accumuler les samples
    chunk = indata[:, 0].astype(np.float32)
    sample_buf = np.concatenate([sample_buf, chunk])

    # Traiter par fenêtres de FRAME_SIZE
    while len(sample_buf) >= FRAME_SIZE:
        frame = sample_buf[:FRAME_SIZE]
        sample_buf = sample_buf[FRAME_SIZE:]

        rms      = compute_rms(frame)
        zcr      = compute_zcr(frame)
        centroid = compute_spectral_centroid(frame)
        cls      = classify_frame(zcr, rms, centroid)

        votes[cls] += 1
        frame_count[0] += 1

        # Tous les VOTE_WINDOW frames → décision
        if frame_count[0] >= VOTE_WINDOW:
            # Pendant les premières secondes, on n'affiche pas la nature du son.
            if stream_start_time[0] is not None:
                elapsed = time.perf_counter() - stream_start_time[0]
                if elapsed < STARTUP_DELAY_SEC:
                    write_warming_audio_output(STARTUP_DELAY_SEC - elapsed)
                    votes[:] = [0, 0, 0, 0]
                    frame_count[0] = 0
                    continue

            result = int(np.argmax(votes))

            if result != last_class[0]:
                ts = time.strftime("%H:%M:%S")
                print(f"\r[{ts}]  {CLASS_ICONS[result]}  {CLASS_NAMES[result].upper():<25}"
                      f"  (votes: sil={votes[0]} chant={votes[1]} bag={votes[2]} bom={votes[3]})"
                      f"  centroid≈{centroid:.0f}Hz", flush=True)
                last_class[0] = result
            else:
                # Mise à jour ligne courante
                print(f"\r[{time.strftime('%H:%M:%S')}]  {CLASS_ICONS[result]}  "
                      f"{CLASS_NAMES[result].upper():<25}"
                      f"  rms={rms:.3f} cent={centroid:.0f}Hz       ",
                      end='', flush=True)

            write_audio_output(
                class_idx=result,
                votes_snapshot=votes[:],
                rms=rms,
                centroid=centroid
            )

            # Reset
            votes[:] = [0, 0, 0, 0]
            frame_count[0] = 0

# ─── Main ──────────────────────────────────────────────────────────────────
def list_devices():
    print("\nMicros disponibles:")
    print("─" * 60)
    devs = sd.query_devices()
    for i, d in enumerate(devs):
        if d['max_input_channels'] > 0:
            marker = " ◄ défaut" if i == sd.default.device[0] else ""
            print(f"  [{i:2d}] {d['name']}{marker}")
    print("─" * 60)
    print(f"\nUtilisation: python3 mic_classifier.py --device <numéro>")

def main():
    parser = argparse.ArgumentParser(
        description='Classification audio temps réel via microphone'
    )
    parser.add_argument('--list',   action='store_true', help='Lister les micros disponibles')
    parser.add_argument('--device', type=int, default=None, help='Index du micro à utiliser')
    args = parser.parse_args()

    if args.list:
        list_devices()
        return

    os.makedirs(OUTPUT_DIR, exist_ok=True)
    write_warming_audio_output(STARTUP_DELAY_SEC)

    # Infos micro sélectionné
    device_info = sd.query_devices(args.device, 'input')
    print("╔══════════════════════════════════════════════════╗")
    print("║     ESP32 Audio Classifier — Mode Micro PC       ║")
    print("╚══════════════════════════════════════════════════╝")
    print(f"  Micro  : {device_info['name']}")
    print(f"  SR     : {SAMPLE_RATE} Hz")
    print(f"  Fenêtre: {VOTE_WINDOW * FRAME_SIZE / SAMPLE_RATE * 1000:.0f}ms")
    print()
    print("  Classes: silence | chants supportaires | bagarre | bombes")
    print()
    print("  Jouez un des 4 fichiers audio devant le micro...")
    print(f"  Délai de démarrage: {STARTUP_DELAY_SEC:.0f}s (aucune classe affichée)")
    print("  Ctrl+C pour arrêter")
    print("─" * 60)

    try:
        stream_start_time[0] = time.perf_counter()
        with sd.InputStream(
            device=args.device,
            channels=1,
            samplerate=SAMPLE_RATE,
            blocksize=256,
            dtype='float32',
            callback=audio_callback
        ):
            while True:
                sd.sleep(100)

    except KeyboardInterrupt:
        print("\n\n[Arrêt]")
    except Exception as e:
        print(f"\nERREUR: {e}")
        print("\nEssayez: python3 mic_classifier.py --list")
        print("puis   : python3 mic_classifier.py --device <numéro>")

if __name__ == "__main__":
    main()
