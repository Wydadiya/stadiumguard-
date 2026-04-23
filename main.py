#!/usr/bin/env python3
"""
main.py — StadiumGuard Launcher
================================
Lance les 3 composants d'un seul coup :
  1. camera_server.py       — Lab1 + Lab2 + Lab3 (caméra + JSON output)
  2. match_context_simulator.py — Contexte match (multiplicateurs)
  3. orchestrator.py        — Fusion finale → final_alert.json

Usage :
    python main.py

Arrêt :
    Ctrl+C dans ce terminal  (arrête les 3 d'un coup)
    OU appuie sur [Q] dans une fenêtre OpenCV

Prérequis :
    - camera_server.py, match_context_simulator.py, orchestrator.py
      doivent être dans le MÊME dossier que ce main.py
    - pip install ultralytics opencv-python numpy
"""

import subprocess
import sys
import os
import time
import signal
import threading

# ─── Chemins des 3 scripts ───────────────────────────────────────────────────
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

SCRIPTS = {
    "camera_server":   os.path.join(BASE_DIR, "backend", "camera_server.py"),
    "match_context":   os.path.join(BASE_DIR, "backend", "match_context_simulator.py"),
    "orchestrator":    os.path.join(BASE_DIR, "backend", "orchestrator.py"),
}

# ─── Vérification que les fichiers existent ──────────────────────────────────
def check_files():
    missing = []
    for name, path in SCRIPTS.items():
        if not os.path.exists(path):
            missing.append(f"  ✗ {name} → {path}")
    if missing:
        print("❌ Fichiers manquants :")
        for m in missing: print(m)
        sys.exit(1)

# ─── Lancement d'un script dans un sous-processus ────────────────────────────
processes = {}

def launch(name, script_path):
    """Lance un script Python dans un sous-processus et retourne le process."""
    print(f"  ▶ Démarrage {name}...")
    proc = subprocess.Popen(
        [sys.executable, script_path],
        cwd=BASE_DIR,
        # Pas de capture stdout/stderr → sortie directe dans le terminal
        # Si tu veux des logs séparés, remplace par :
        # stdout=open(f"logs/{name}.log","w"), stderr=subprocess.STDOUT
    )
    processes[name] = proc
    return proc

def monitor(name, proc):
    """Thread qui surveille un process et affiche si il crashe."""
    proc.wait()
    if not shutting_down:
        print(f"\n⚠️  [{name}] s'est arrêté (code={proc.returncode})")
        print(f"   Redémarre avec : python {SCRIPTS[name]}")

# ─── Arrêt propre de tous les processus ──────────────────────────────────────
shutting_down = False

def shutdown(signum=None, frame=None):
    global shutting_down
    if shutting_down:
        return
    shutting_down = True

    print("\n\n🛑 Arrêt de StadiumGuard...")
    for name, proc in processes.items():
        if proc.poll() is None:   # encore en vie
            print(f"  ✗ Stop {name} (PID {proc.pid})")
            try:
                if os.name == "nt":
                    proc.terminate()      # Windows
                else:
                    proc.send_signal(signal.SIGTERM)  # Linux/macOS
            except Exception:
                pass

    # Attendre max 4s que chaque process s'arrête
    for name, proc in processes.items():
        try:
            proc.wait(timeout=4)
        except subprocess.TimeoutExpired:
            proc.kill()
            print(f"  ⚡ {name} forcé (kill)")

    print("✅ Tous les modules arrêtés. Au revoir.\n")
    sys.exit(0)


# ─── MAIN ─────────────────────────────────────────────────────────────────────
if __name__ == "__main__":

    # Intercepte Ctrl+C
    signal.signal(signal.SIGINT,  shutdown)
    signal.signal(signal.SIGTERM, shutdown)

    print("=" * 60)
    print("  StadiumGuard — Lancement système complet")
    print("=" * 60)
    print()

    # Vérifie les fichiers
    check_files()

    # Crée le dossier output si besoin
    os.makedirs(os.path.join(BASE_DIR, "output"), exist_ok=True)

    # Lance les 3 scripts
    print("🚀 Démarrage des modules :\n")
    print("ℹ️  Mode ESP32: ce launcher utilise backend/camera_server.py (API + audio-stream).")
    print("   Ne lance pas backend/api_server.py en parallèle (même port 5000).\n")

    p1 = launch("camera_server",  SCRIPTS["camera_server"])
    time.sleep(1.0)   # Laisse la caméra s'initialiser avant le reste

    p2 = launch("match_context",  SCRIPTS["match_context"])
    time.sleep(0.5)

    p3 = launch("orchestrator",   SCRIPTS["orchestrator"])

    print()
    print("=" * 60)
    print("  ✅ Tous les modules lancés")
    print()
    print("  Fenêtres OpenCV :")
    print("    • Lab1: Person Tracking")
    print("    • Lab2: Fall Detection")
    print("    • Lab3: Crowd Motion Classifier")
    print()
    print("  Fichiers JSON générés dans output/ :")
    print("    • output/person_score.json")
    print("    • output/fall_score.json")
    print("    • output/motion_score.json")
    print("    • output/match_context.json")
    print("    • output/final_alert.json  ← résultat fusionné")
    print()
    print("  Arrêt : Ctrl+C ici, ou [Q] dans une fenêtre OpenCV")
    print("=" * 60)
    print()

    # Threads de surveillance (détecte si un module crashe)
    for name, proc in [("camera_server", p1),
                        ("match_context", p2),
                        ("orchestrator",  p3)]:
        t = threading.Thread(target=monitor, args=(name, proc), daemon=True)
        t.start()

    # Boucle principale — attend que tous les processus soient vivants
    try:
        while True:
            # Vérifie si tous les processus tournent encore
            all_alive = all(p.poll() is None for p in [p1, p2, p3])
            if not all_alive:
                print("\n⚠️  Un module s'est arrêté — arrêt général.")
                shutdown()
            time.sleep(1.0)

    except KeyboardInterrupt:
        shutdown()