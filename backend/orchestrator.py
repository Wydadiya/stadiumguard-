#!/usr/bin/env python3
# orchestrator.py — StadiumGuard Fusion Engine
#
# Lit les sorties JSON de lab1, lab2, lab3, audio + match_context
# Calcule le score final fusionné selon la spec v1.0
# Affiche un dashboard terminal + écrit output/final_alert.json
#
# Architecture :
#   lab1  → output/person_score.json   (module: "person")
#   lab2  → output/fall_score.json     (module: "fall")
#   lab3  → output/motion_score.json   (module: "motion")
#   mic   → output/audio_score.json    (module: "audio")
#   sim   → output/match_context.json  (module: "match_context")
#
# Usage : python orchestrator.py
#         python orchestrator.py --output output --interval 0.5

import json
import os
import sys
import time
from datetime import datetime

# ─────────────────────────────────────────────────────────────
# CONFIG
# ─────────────────────────────────────────────────────────────
OUTPUT_DIR      = "output"
INTERVAL_S      = 0.5       # fréquence de fusion (secondes)
STALE_TIMEOUT_S = 5.0       # délai avant de considérer un module mort

# Pondérations multimodales (somme = 1.0)
# Intègre désormais le module fumée/gaz (ESP32 -> smoke_score.json).
W_PERSON = 0.12
W_FALL   = 0.25
W_MOTION = 0.25
W_AUDIO  = 0.18
W_SMOKE  = 0.20

# Part vision dans le score global (35%)
VISION_WEIGHT = 0.35

# Seuils de niveau d'alerte (Spec v1.0)
LEVEL_LOW      = 30
LEVEL_MEDIUM   = 60
LEVEL_HIGH     = 80
# >= 80 → CRITICAL

LEVEL_COLORS = {
    "LOW":      "\033[92m",   # vert
    "MEDIUM":   "\033[93m",   # jaune
    "HIGH":     "\033[91m",   # rouge
    "CRITICAL": "\033[95m",   # magenta
}
RESET = "\033[0m"
BOLD  = "\033[1m"

# ─────────────────────────────────────────────────────────────
# LECTURE JSON SÉCURISÉE
# ─────────────────────────────────────────────────────────────
def read_json(path):
    """
    Lit un fichier JSON et retourne son contenu, ou None en cas d'erreur.
    Gère les accès concurrents (fichier en cours d'écriture).
    """
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError, PermissionError):
        return None


def is_stale(data, timeout=STALE_TIMEOUT_S):
    """Retourne True si le timestamp du module est trop vieux."""
    if data is None:
        return True
    ts = data.get("timestamp", 0)
    return (time.time() - ts) > timeout


# ─────────────────────────────────────────────────────────────
# FUSION PRINCIPALE
# ─────────────────────────────────────────────────────────────
def fuse(person_data, fall_data, motion_data, audio_data, smoke_data, context_data):
    """
    Implémente la formule de fusion selon la spec v1.0 :

      raw_vision   = person_score×W_PERSON + fall_score×W_FALL + motion_score×W_MOTION
      raw_audio    = audio_score×W_AUDIO
      raw_smoke    = smoke_score×W_SMOKE
      raw_combined = raw_vision + raw_audio + raw_smoke
      final_score  = min(raw_combined × context_mult, 100)
      level       = LOW / MEDIUM / HIGH / CRITICAL

    Retourne un dict complet pour l'affichage et l'écriture JSON.
    """
    now = time.time()

    # ── Récupération des scores (0 si module absent/périmé) ──────
    person_score  = float(person_data.get("score", 0))  if (person_data  and not is_stale(person_data))  else 0.0
    fall_score    = float(fall_data.get("score",   0))  if (fall_data    and not is_stale(fall_data))    else 0.0
    motion_score  = float(motion_data.get("score", 0))  if (motion_data  and not is_stale(motion_data))  else 0.0
    audio_score   = float(audio_data.get("score",  0))  if (audio_data   and not is_stale(audio_data))   else 0.0
    smoke_score   = float(smoke_data.get("score",  0))  if (smoke_data   and not is_stale(smoke_data))   else 0.0

    person_conf   = float(person_data.get("confidence", 0))  if person_data  else 0.0
    fall_conf     = float(fall_data.get("confidence",   0))  if fall_data    else 0.0
    motion_conf   = float(motion_data.get("confidence", 0))  if motion_data  else 0.0
    audio_conf    = float(audio_data.get("confidence",  0))  if audio_data   else 0.0
    smoke_conf    = float(smoke_data.get("confidence",  0))  if smoke_data   else 0.0

    # ── Contexte match ────────────────────────────────────────────
    if context_data and not is_stale(context_data, timeout=10.0):
        context_mult  = float(context_data.get("multiplier", 1.0))
        match_state   = context_data.get("current_state", "unknown")
        match_minute  = context_data.get("match_minute", 0)
        home_score    = context_data.get("home_score", 0)
        away_score    = context_data.get("away_score", 0)
    else:
        # Pas de contexte → multiplicateur neutre
        context_mult  = 1.0
        match_state   = "no_context"
        match_minute  = 0
        home_score    = 0
        away_score    = 0

    # ── Formule de fusion (Spec v1.0) ─────────────────────────────
    raw_vision = (person_score * W_PERSON +
                  fall_score   * W_FALL   +
                  motion_score * W_MOTION)
    raw_audio = audio_score * W_AUDIO
    raw_smoke = smoke_score * W_SMOKE
    raw_combined = raw_vision + raw_audio + raw_smoke

    # Note : VISION_WEIGHT (0.35) est prévu si d'autres capteurs
    # (audio, LiDAR…) rejoignent le pipeline.
    # Pour l'instant vision = seule source → on applique sans réduction.
    # Décommente la ligne suivante si tu ajoutes d'autres modules :
    # raw_vision = raw_vision * VISION_WEIGHT

    final_score = min(raw_combined * context_mult, 100.0)

    # ── Niveau d'alerte ────────────────────────────────────────────
    if final_score < LEVEL_LOW:
        level = "LOW"
    elif final_score < LEVEL_MEDIUM:
        level = "MEDIUM"
    elif final_score < LEVEL_HIGH:
        level = "HIGH"
    else:
        level = "CRITICAL"

    # ── Confiance globale (moyenne pondérée) ────────────────────────
    global_conf = round(
        person_conf * W_PERSON +
        fall_conf   * W_FALL   +
        motion_conf * W_MOTION +
        audio_conf  * W_AUDIO  +
        smoke_conf  * W_SMOKE, 2)

    # ── Modules actifs / périmés ────────────────────────────────────
    module_status = {
        "person": "OK"    if (person_data and not is_stale(person_data)) else "STALE",
        "fall":   "OK"    if (fall_data   and not is_stale(fall_data))   else "STALE",
        "motion": "OK"    if (motion_data and not is_stale(motion_data)) else "STALE",
        "audio":  "OK"    if (audio_data  and not is_stale(audio_data))  else "STALE",
        "smoke":  "OK"    if (smoke_data  and not is_stale(smoke_data))  else "STALE",
        "context":"OK"    if (context_data and not is_stale(context_data, 10)) else "STALE",
    }

    return {
        "timestamp":     now,
        "iso_time":      datetime.now().isoformat(),
        "final_score":   round(final_score, 1),
        "level":         level,
        "global_conf":   global_conf,

        # Décomposition
        "raw_vision":    round(raw_vision, 1),
        "raw_audio":     round(raw_audio, 1),
        "raw_smoke":     round(raw_smoke, 1),
        "raw_combined":  round(raw_combined, 1),
        "context_mult":  context_mult,

        # Scores individuels
        "scores": {
            "person": round(person_score, 1),
            "fall":   round(fall_score,   1),
            "motion": round(motion_score, 1),
            "audio":  round(audio_score,  1),
            "smoke":  round(smoke_score,  1),
        },

        # Contexte match
        "match": {
            "state":        match_state,
            "minute":       match_minute,
            "score":        f"{home_score}-{away_score}",
            "multiplier":   context_mult,
        },

        # État des modules
        "modules": module_status,

        # Détails bruts pour debug
        "raw": {
            "person": person_data.get("details", {}) if person_data else {},
            "fall":   fall_data.get("details",   {}) if fall_data   else {},
            "motion": motion_data.get("details", {}) if motion_data else {},
            "audio":  audio_data.get("details",  {}) if audio_data  else {},
            "smoke":  smoke_data.get("details",  {}) if smoke_data  else {},
        }
    }


# ─────────────────────────────────────────────────────────────
# AFFICHAGE TERMINAL
# ─────────────────────────────────────────────────────────────
def draw_bar(value, width=30, max_val=100.0):
    """Barre ASCII proportionnelle à value/max_val."""
    filled = int(round(value / max_val * width))
    filled = max(0, min(filled, width))
    return "█" * filled + "░" * (width - filled)


def level_color(level):
    return LEVEL_COLORS.get(level, "")


def print_dashboard(result, cycle):
    """Affiche le dashboard de fusion dans le terminal."""
    os.system("cls" if os.name == "nt" else "clear")

    level = result["level"]
    score = result["final_score"]
    lc    = level_color(level)

    print(f"{BOLD}{'═'*62}{RESET}")
    print(f"{BOLD}  StadiumGuard — Fusion Dashboard  "
          f"[cycle #{cycle}]{RESET}")
    print(f"{'═'*62}")

    # Score principal
    bar = draw_bar(score)
    print(f"\n  Score final : {lc}{BOLD}{score:5.1f}/100{RESET}  "
          f"{lc}[{level}]{RESET}")
    print(f"  {lc}[{bar}]{RESET}\n")

    # Contexte match
    m = result["match"]
    mult_str = f"×{m['multiplier']:.1f}"
    print(f"  Match  : min {m['minute']:3d}  "
          f"{m['score']}  "
          f"État: {m['state']:<28s} {BOLD}{mult_str}{RESET}")

    # Décomposition vision
    print(f"\n  ─── Scores modules ──────────────────────────────────")
    scores = result["scores"]
    mods   = result["modules"]

    for key, label, weight in [
        ("person", "Personnes (lab1)", W_PERSON),
        ("fall",   "Chutes    (lab2)", W_FALL),
        ("motion", "Mouvement (lab3)", W_MOTION),
        ("audio",  "Audio     (mic)",  W_AUDIO),
        ("smoke",  "Fumee/Gaz (esp)",  W_SMOKE),
    ]:
        s    = scores[key]
        st   = mods[key]
        col  = "\033[92m" if st == "OK" else "\033[90m"
        bbar = draw_bar(s, width=20)
        print(f"  {label} ×{weight:.0%}  "
              f"{col}[{bbar}]{RESET} {s:5.1f}  [{st}]")

    print(f"\n  Vision brute : {result['raw_vision']:5.1f}")
    print(f"  Audio brut   : {result['raw_audio']:5.1f}")
    print(f"  Fumee brute  : {result['raw_smoke']:5.1f}")
    print(f"  Total brut   : {result['raw_combined']:5.1f}  "
          f"× contexte {m['multiplier']:.1f} = {BOLD}{score:.1f}{RESET}")
    print(f"  Confiance globale : {result['global_conf']:.2f}")

    # Modules context
    ctx_st  = mods["context"]
    ctx_col = "\033[92m" if ctx_st == "OK" else "\033[90m"
    print(f"  Contexte match    : {ctx_col}[{ctx_st}]{RESET}")

    # Détails fall si alerte
    fall_raw = result["raw"].get("fall", {})
    statuses = fall_raw.get("statuses", {})
    if statuses:
        fallen = [f"ID:{k}={v}" for k, v in statuses.items() if v != "STANDING"]
        if fallen:
            print(f"\n  ⚠  Personnes : {', '.join(fallen)}")

    # Détails motion si dangereux
    motion_raw = result["raw"].get("motion", {})
    if motion_raw.get("label") in ("FIGHT", "STAMPEDE"):
        print(f"\n  ⚠  Motion : {motion_raw['label']}  "
              f"z={motion_raw.get('fight_z', 0):.1f}  "
              f"danger={motion_raw.get('danger_seconds', 0):.1f}s")

    audio_raw = result["raw"].get("audio", {})
    audio_label = audio_raw.get("label")
    if audio_label:
        print(f"\n  🔊 Audio : {audio_label}")

    smoke_raw = result["raw"].get("smoke", {})
    if smoke_raw.get("detected"):
        print(f"\n  💨 Fumee/Gaz : DETECTE  ppm={smoke_raw.get('sensor_ppm', '?')}")

    # Alerte critique
    if level == "CRITICAL":
        print(f"\n{lc}{BOLD}  !! ALERTE CRITIQUE — INTERVENTION REQUISE !!{RESET}")
    elif level == "HIGH":
        print(f"\n{lc}{BOLD}  !! ALERTE HAUTE — SURVEILLER{RESET}")

    print(f"\n{'─'*62}")
    print(f"  {datetime.now().strftime('%H:%M:%S')}  "
          f"Prochain cycle dans {INTERVAL_S}s  |  Ctrl+C pour quitter")
    print(f"{'═'*62}")


# ─────────────────────────────────────────────────────────────
# ÉCRITURE SORTIE FINALE
# ─────────────────────────────────────────────────────────────
def write_output(result, output_dir):
    path = os.path.join(output_dir, "final_alert.json")
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(result, f, indent=2, ensure_ascii=False)
    except Exception as e:
        print(f"❌ Écriture impossible : {e}")


# ─────────────────────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────────────────────
def main():
    global OUTPUT_DIR, INTERVAL_S

    # Args optionnels
    for i, arg in enumerate(sys.argv):
        if arg == "--output" and i+1 < len(sys.argv):
            OUTPUT_DIR = sys.argv[i+1]
        elif arg == "--interval" and i+1 < len(sys.argv):
            INTERVAL_S = float(sys.argv[i+1])

    os.makedirs(OUTPUT_DIR, exist_ok=True)

    # Chemins fichiers
    paths = {
        "person":  os.path.join(OUTPUT_DIR, "person_score.json"),
        "fall":    os.path.join(OUTPUT_DIR, "fall_score.json"),
        "motion":  os.path.join(OUTPUT_DIR, "motion_score.json"),
        "audio":   os.path.join(OUTPUT_DIR, "audio_score.json"),
        "smoke":   os.path.join(OUTPUT_DIR, "smoke_score.json"),
        "context": os.path.join(OUTPUT_DIR, "match_context.json"),
    }

    print(f"{BOLD}StadiumGuard Orchestrator — démarrage{RESET}")
    print(f"Dossier : {os.path.abspath(OUTPUT_DIR)}")
    print(f"Intervalle : {INTERVAL_S}s\n")
    print("Modules attendus :")
    for k, p in paths.items():
        exists = "✅" if os.path.exists(p) else "⏳ (en attente)"
        print(f"  {k:<10} → {p}  {exists}")
    print("\nCtrl+C pour arrêter.\n")

    cycle = 0

    try:
        while True:
            cycle += 1
            t0 = time.time()

            # Lecture de tous les modules
            person_data  = read_json(paths["person"])
            fall_data    = read_json(paths["fall"])
            motion_data  = read_json(paths["motion"])
            audio_data   = read_json(paths["audio"])
            smoke_data   = read_json(paths["smoke"])
            context_data = read_json(paths["context"])

            # Fusion
            result = fuse(person_data, fall_data, motion_data, audio_data, smoke_data, context_data)

            # Affichage
            print_dashboard(result, cycle)

            # Écriture finale
            write_output(result, OUTPUT_DIR)

            # Attente précise
            elapsed = time.time() - t0
            sleep_t = max(0.0, INTERVAL_S - elapsed)
            time.sleep(sleep_t)

    except KeyboardInterrupt:
        print(f"\n{BOLD}Orchestrateur arrêté.{RESET}")


if __name__ == "__main__":
    main()
