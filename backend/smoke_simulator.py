#!/usr/bin/env python3
# smoke_simulator.py — Simulateur simple de détection fumée

import json
import os
import random
import time
from datetime import datetime

OUTPUT_DIR = "output"
OUTPUT_FILE = os.path.join(OUTPUT_DIR, "smoke_score.json")
INTERVAL_S = 1.0


def make_payload(detected, confidence, score, source="simulator"):
    return {
        "module": "smoke",
        "score": round(float(score), 1),
        "confidence": round(float(confidence), 2),
        "details": {
            "detected": bool(detected),
            "label": "SMOKE" if detected else "CLEAR",
            "source": source,
        },
        "timestamp": time.time(),
        "iso_time": datetime.now().isoformat(),
    }


def write_json(payload):
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)


def main():
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    print("=" * 60)
    print("  StadiumGuard Smoke Simulator")
    print("=" * 60)
    print(f"  Output: {os.path.abspath(OUTPUT_FILE)}")
    print(f"  Interval: {INTERVAL_S:.1f}s")
    print("  Ctrl+C pour arrêter")
    print("=" * 60)

    # Etat initial clair
    write_json(make_payload(False, 0.92, 5))

    detected = False
    try:
        while True:
            # Petite probabilité de basculer d'état pour simuler des événements
            if random.random() < 0.12:
                detected = not detected

            if detected:
                confidence = random.uniform(0.75, 0.98)
                score = random.uniform(70, 98)
            else:
                confidence = random.uniform(0.80, 0.97)
                score = random.uniform(0, 15)

            payload = make_payload(detected, confidence, score)
            write_json(payload)

            status = "SMOKE DETECTED" if detected else "CLEAR"
            print(f"[{time.strftime('%H:%M:%S')}] {status:<15} "
                  f"score={payload['score']:>5} conf={payload['confidence']:.2f}")

            time.sleep(INTERVAL_S)
    except KeyboardInterrupt:
        print("\n[Smoke Simulator] Arrêté.")


if __name__ == "__main__":
    main()
