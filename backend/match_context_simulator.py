#!/usr/bin/env python3
# match_context_simulator.py
# StadiumGuard — Match Context Engine (PC Simulation Mode)
# 
# Simule l'API football-data.org en local pour tests PC.
# Sortie: output/match_context.json toutes les 1 seconde.
# Contrôles: touches clavier pour changer d'état manuellement.

import json
import time
import os
import sys
import threading
from datetime import datetime

# ─────────────────────────────────────────────────────────────
# CONFIGURATION — Table des états + multiplicateurs (Spec v1.0)
# ─────────────────────────────────────────────────────────────
MATCH_STATES = {
    # Format: "key": {"mult": float, "desc": str, "duration_s": int}
    "normal": {
        "mult": 1.0,
        "desc": "Jeu en cours — rien de spécial",
        "duration_s": None  # Infini en mode manuel
    },
    "goal_home": {
        "mult": 0.3,
        "desc": "⚽ BUT DU MAROC — Chaos attendu, seuils ×3",
        "duration_s": 90  # Auto-return après 90s
    },
    "goal_away": {
        "mult": 0.8,
        "desc": "⚽ But adversaire — Vigilance modérée",
        "duration_s": 60
    },
    "penalty_awarded": {
        "mult": 1.5,
        "desc": "🎯 Penalty accordé — Silence tendu, vigilance max",
        "duration_s": 45
    },
    "penalty_silence": {
        "mult": 1.5,
        "desc": "🤫 Phase silencieuse penalty — Tout bruit = suspect",
        "duration_s": 30
    },
    "var_review": {
        "mult": 1.4,
        "desc": "📺 Review VAR — Agitation nerveuse",
        "duration_s": 60
    },
    "yellow_card": {
        "mult": 1.3,
        "desc": "🟨 Carton jaune — Tension monte",
        "duration_s": 45
    },
    "red_card": {
        "mult": 1.3,
        "desc": "🟥 Carton rouge — Risque confrontation",
        "duration_s": 60
    },
    "substitution": {
        "mult": 0.6,
        "desc": "🔄 Changement — Applaudissements attendus",
        "duration_s": 30
    },
    "injury_stop": {
        "mult": 1.2,
        "desc": "🏥 Arrêt jeu (blessure) — Préoccupation légitime",
        "duration_s": 90
    },
    "halftime": {
        "mult": 1.0,
        "desc": "⏸️ Mi-temps — Mouvement vers concessions",
        "duration_s": 900  # 15 minutes simulées
    },
    "final_win": {
        "mult": 0.2,
        "desc": "🏁 Victoire — Célébration massive attendue",
        "duration_s": 120
    },
    "final_loss": {
        "mult": 1.8,
        "desc": "🏁 Défaite — Frustration possible, vigilance ×2",
        "duration_s": 120
    },
    "unexplained_scream": {
        "mult": 2.0,
        "desc": "🚨 Cri sans contexte — Signal le plus dangereux",
        "duration_s": 20  # Court mais critique
    },
    "celebration_spontaneous": {
        "mult": 0.5,
        "desc": "🎉 Ovation spontanée — Applaudissements collectifs",
        "duration_s": 30
    }
}

# Contrôles clavier
KEY_BINDINGS = {
    'r': 'normal',              # Reset → normal
    'g': 'goal_home',           # G = Goal Maroc
    'a': 'goal_away',           # A = Goal adversaire
    'p': 'penalty_awarded',     # P = Penalty
    's': 'penalty_silence',     # S = Silence penalty
    'v': 'var_review',          # V = VAR
    'y': 'yellow_card',         # Y = Yellow
    'e': 'red_card',            # E = rEd card
    'c': 'substitution',        # C = Change
    'i': 'injury_stop',         # I = Injury
    'h': 'halftime',            # H = Halftime
    'w': 'final_win',           # W = Win
    'l': 'final_loss',          # L = Loss
    'u': 'unexplained_scream',  # U = Unexplained scream
    'o': 'celebration_spontaneous',  # O = Ovations
    'd': '_toggle_demo',        # D = Demo mode toggle
    'q': '_quit'                # Q = Quit
}

# Mode démo auto : cycle prédéfini pour présentation jury
DEMO_CYCLE = [
    {"state": "normal", "duration": 20},
    {"state": "goal_home", "duration": 15},
    {"state": "normal", "duration": 10},
    {"state": "penalty_silence", "duration": 12},
    {"state": "unexplained_scream", "duration": 8},
    {"state": "final_win", "duration": 20},
    {"state": "normal", "duration": 999}  # Boucle sur normal à la fin
]

# ─────────────────────────────────────────────────────────────
# CLASSE PRINCIPALE — MatchContextSimulator
# ─────────────────────────────────────────────────────────────
class MatchContextSimulator:
    def __init__(self, output_dir="output"):
        self.output_dir = output_dir
        os.makedirs(output_dir, exist_ok=True)
        
        self.current_state = "normal"
        self.multiplier = MATCH_STATES["normal"]["mult"]
        self.match_minute = 0
        self.home_score = 0
        self.away_score = 0
        self.last_event = None
        self.start_time = time.time()
        
        self.demo_mode = False
        self.demo_index = 0
        self.demo_start = None
        
        self.running = True
        self.state_expiry = None  # Pour auto-return des états temporaires
        
        # Thread pour lecture clavier (non-bloquant)
        self.key_thread = threading.Thread(target=self._key_listener, daemon=True)
        self.key_thread.start()
        
        print(f"✅ Match Context Simulator started — output: {output_dir}/match_context.json")
        self._print_controls()
    
    def _print_controls(self):
        print("\n" + "─"*60)
        print(" 🎮 CONTRÔLES CLAVIER:")
        print("   [G] But Maroc(×0.3)  [A] But adversaire(×0.8)")
        print("   [P] Penalty(×1.5)    [S] Silence penalty(×1.5)")
        print("   [V] VAR(×1.4)        [Y] Carton jaune(×1.3)")
        print("   [E] Carton rouge(×1.3) [C] Substitution(×0.6)")
        print("   [I] Blessure(×1.2)   [H] Mi-temps(×1.0)")
        print("   [W] Victoire(×0.2)   [L] Défaite(×1.8)")
        print("   [U] Cri sans contexte(×2.0) [O] Ovation(×0.5)")
        print("   [D] Toggle DEMO mode  [R] Reset normal  [Q] Quit")
        print("─"*60 + "\n")
    
    def _key_listener(self):
        """Écoute les touches en arrière-plan (Windows/Linux/macOS)"""
        try:
            # Windows
            import msvcrt
            while self.running:
                if msvcrt.kbhit():
                    key = msvcrt.getch().decode('utf-8').lower()
                    self._handle_key(key)
                time.sleep(0.05)
        except ImportError:
            # Linux/macOS — fallback simple avec input non-bloquant
            import select
            import sys
            import tty
            import termios
            
            # Sauvegarde config terminal
            fd = sys.stdin.fileno()
            old_settings = termios.tcgetattr(fd)
            
            try:
                tty.setcbreak(fd)
                while self.running:
                    if select.select([sys.stdin], [], [], 0.05)[0]:
                        key = sys.stdin.read(1).lower()
                        self._handle_key(key)
            finally:
                termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)
    
    def _handle_key(self, key):
        """Traite une touche pressée"""
        if key not in KEY_BINDINGS:
            return
        
        action = KEY_BINDINGS[key]
        
        if action == '_quit':
            print("\n👋 Exiting Match Context Simulator...")
            self.running = False
            return
        
        if action == '_toggle_demo':
            self.demo_mode = not self.demo_mode
            if self.demo_mode:
                self.demo_index = 0
                self.demo_start = time.time()
                print(f"🎬 DEMO MODE ON — Cycle: {[s['state'] for s in DEMO_CYCLE]}")
            else:
                print("🔁 DEMO MODE OFF — Retour en mode manuel")
            return
        
        # Changement d'état manuel
        if action in MATCH_STATES:
            self._set_state(action)
            state_info = MATCH_STATES[action]
            print(f"🎯 State → {action.upper()} | ×{state_info['mult']} | {state_info['desc']}")
    
    def _set_state(self, state_key):
        """Change l'état courant et programme l'auto-return si nécessaire"""
        self.current_state = state_key
        self.multiplier = MATCH_STATES[state_key]["mult"]
        self.last_event = state_key.split("_")[0] if "_" in state_key else state_key
        
        # Auto-return après duration_s si défini
        duration = MATCH_STATES[state_key].get("duration_s")
        if duration and state_key != "normal":
            self.state_expiry = time.time() + duration
            print(f"   ⏱️ Auto-return to 'normal' in {duration}s")
        else:
            self.state_expiry = None
        
        # Mise à jour score simulé pour certains événements
        if state_key == "goal_home":
            self.home_score += 1
            self.match_minute = min(self.match_minute + 5, 120)
        elif state_key == "goal_away":
            self.away_score += 1
            self.match_minute = min(self.match_minute + 5, 120)
        elif state_key == "halftime":
            self.match_minute = 45
        elif state_key in ("final_win", "final_loss"):
            self.match_minute = 90
    
    def _update_demo_mode(self):
        """Gère le cycle auto démo"""
        if not self.demo_mode or not DEMO_CYCLE:
            return
        
        now = time.time()
        if self.demo_start is None:
            self.demo_start = now
        
        # Vérifie si on doit passer au prochain état du cycle
        current_step = DEMO_CYCLE[self.demo_index]
        elapsed = now - self.demo_start
        
        if elapsed >= current_step["duration"]:
            self.demo_index = (self.demo_index + 1) % len(DEMO_CYCLE)
            self.demo_start = now
            next_state = DEMO_CYCLE[self.demo_index]["state"]
            self._set_state(next_state)
            print(f"🎬 DEMO → {next_state} (×{MATCH_STATES[next_state]['mult']})")
    
    def _update_auto_return(self):
        """Gère le retour auto à 'normal' après un état temporaire"""
        if self.state_expiry and time.time() >= self.state_expiry:
            print("🔁 Auto-return → normal")
            self._set_state("normal")
    
    def get_context_dict(self):
        """Retourne le dictionnaire de contexte au format standard"""
        return {
            "module": "match_context",
            "current_state": self.current_state,
            "multiplier": self.multiplier,
            "match_minute": self.match_minute,
            "home_score": self.home_score,
            "away_score": self.away_score,
            "last_event": self.last_event,
            "demo_mode": self.demo_mode,
            "timestamp": time.time(),
            "iso_time": datetime.now().isoformat()
        }
    
    def write_output(self):
        """Écrit le contexte dans output/match_context.json"""
        output_path = os.path.join(self.output_dir, "match_context.json")
        data = self.get_context_dict()
        
        try:
            with open(output_path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            return True
        except Exception as e:
            print(f"❌ Failed to write context: {e}")
            return False
    
    def run(self, interval=1.0):
        """Boucle principale — écriture JSON toutes les `interval` secondes"""
        print(f"🔄 Writing context every {interval}s to {self.output_dir}/match_context.json")
        print("Press any bound key to change state, or [D] for demo cycle.\n")
        
        while self.running:
            # Mises à jour internes
            self._update_demo_mode()
            self._update_auto_return()
            
            # Écriture JSON
            self.write_output()
            
            # Incrémentation minute match (simulé)
            if self.current_state == "normal" and not self.demo_mode:
                self.match_minute = (self.match_minute + 1) % 120
            
            time.sleep(interval)
        
        # Nettoyage final
        print("✅ Simulator stopped.")


# ─────────────────────────────────────────────────────────────
# POINT D'ENTRÉE
# ─────────────────────────────────────────────────────────────
if __name__ == "__main__":
    # Parse args optionnels
    output_dir = "output"
    interval = 1.0
    
    for i, arg in enumerate(sys.argv):
        if arg == "--output" and i+1 < len(sys.argv):
            output_dir = sys.argv[i+1]
        elif arg == "--interval" and i+1 < len(sys.argv):
            interval = float(sys.argv[i+1])
    
    # Lancement
    simulator = MatchContextSimulator(output_dir=output_dir)
    
    try:
        simulator.run(interval=interval)
    except KeyboardInterrupt:
        print("\n⚠️ Interrupted by user.")
    finally:
        simulator.running = False