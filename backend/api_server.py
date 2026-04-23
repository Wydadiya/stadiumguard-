#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
api_server.py — StadiumGuard REST API Server (standalone)
=========================================================
Micro-serveur Flask qui expose les données JSON du backend via REST API.
Lit les fichiers JSON dans output/ et les sert avec CORS activé.

NOTE: Si vous utilisez camera_server.py (qui intègre Flask + streaming MJPEG),
      ce fichier standalone n'est PAS nécessaire. Les endpoints JSON sont déjà
      disponibles via camera_server.py sur le même port.

Endpoints:
    GET /api/alert    → final_alert.json (score fusionné)
    GET /api/person   → person_score.json
    GET /api/fall     → fall_score.json
    GET /api/motion   → motion_score.json
    GET /api/audio    → audio_score.json
    GET /api/smoke    → smoke_score.json
    GET /api/context  → match_context.json
    GET /api/health   → Status du serveur

Usage:
    python backend/api_server.py
    
Le serveur tourne sur http://localhost:5000
"""

import json
import os
import time
from datetime import datetime
from flask import Flask, jsonify
from flask_cors import CORS

# ─────────────────────────────────────────────────────────────
# CONFIG
# ─────────────────────────────────────────────────────────────
OUTPUT_DIR = "output"
CACHE_TTL_MS = 200  # Rafraîchir le cache toutes les 200ms
PORT = 5000

# ─────────────────────────────────────────────────────────────
# FLASK APP
# ─────────────────────────────────────────────────────────────
app = Flask(__name__)

# Active CORS pour autoriser toutes les origines (dev)
CORS(app, resources={r"/api/*": {"origins": "*"}})

# ─────────────────────────────────────────────────────────────
# CACHE EN MÉMOIRE
# ─────────────────────────────────────────────────────────────
class DataCache:
    """Cache simple avec TTL pour éviter de lire les fichiers à chaque requête."""
    
    def __init__(self, ttl_ms=200):
        self.ttl_ms = ttl_ms
        self.cache = {}
        self.last_update = {}
    
    def get(self, key, loader_fn):
        """
        Retourne la valeur du cache si elle est fraîche,
        sinon appelle loader_fn() pour la recharger.
        """
        now = time.time() * 1000  # timestamp en ms
        
        if key in self.cache:
            age_ms = now - self.last_update.get(key, 0)
            if age_ms < self.ttl_ms:
                return self.cache[key]
        
        # Cache expiré ou absent → recharger
        try:
            data = loader_fn()
            self.cache[key] = data
            self.last_update[key] = now
            return data
        except Exception as e:
            # En cas d'erreur, retourner l'ancienne valeur si disponible
            if key in self.cache:
                return self.cache[key]
            raise e

cache = DataCache(ttl_ms=CACHE_TTL_MS)

# ─────────────────────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────────────────────
def read_json_file(filename):
    """
    Lit un fichier JSON dans OUTPUT_DIR.
    Retourne None si le fichier n'existe pas ou est invalide.
    """
    path = os.path.join(OUTPUT_DIR, filename)
    
    if not os.path.exists(path):
        return None
    
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
            return data
    except (json.JSONDecodeError, PermissionError, IOError):
        return None


def is_stale(data, timeout_s=5.0):
    """Vérifie si les données sont périmées (timestamp trop ancien)."""
    if data is None:
        return True
    
    timestamp = data.get("timestamp", 0)
    age = time.time() - timestamp
    return age > timeout_s


def create_error_response(message, status_code=500):
    """Crée une réponse d'erreur JSON."""
    return jsonify({
        "error": message,
        "timestamp": time.time(),
        "iso_time": datetime.now().isoformat()
    }), status_code


# ─────────────────────────────────────────────────────────────
# ENDPOINTS
# ─────────────────────────────────────────────────────────────
@app.route("/api/health", methods=["GET"])
def health():
    """Endpoint de santé du serveur."""
    return jsonify({
        "status": "ok",
        "service": "StadiumGuard API",
        "version": "1.0.0",
        "timestamp": time.time(),
        "iso_time": datetime.now().isoformat(),
        "output_dir": os.path.abspath(OUTPUT_DIR),
        "cache_ttl_ms": CACHE_TTL_MS
    })


@app.route("/api/alert", methods=["GET"])
def get_alert():
    """
    Retourne le score d'alerte fusionné (final_alert.json).
    C'est l'endpoint principal pour le dashboard.
    """
    try:
        data = cache.get("alert", lambda: read_json_file("final_alert.json"))
        
        if data is None:
            return create_error_response(
                "Alert data not available. Is orchestrator.py running?",
                503
            )
        
        # Ajouter un flag pour indiquer si les données sont fraîches
        data["is_stale"] = is_stale(data, timeout_s=5.0)
        
        return jsonify(data)
    
    except Exception as e:
        return create_error_response(f"Error reading alert data: {str(e)}", 500)


@app.route("/api/person", methods=["GET"])
def get_person():
    """Retourne les données de détection de personnes (person_score.json)."""
    try:
        data = cache.get("person", lambda: read_json_file("person_score.json"))
        
        if data is None:
            return create_error_response(
                "Person data not available. Is lab1 running?",
                503
            )
        
        data["is_stale"] = is_stale(data)
        return jsonify(data)
    
    except Exception as e:
        return create_error_response(f"Error reading person data: {str(e)}", 500)


@app.route("/api/fall", methods=["GET"])
def get_fall():
    """Retourne les données de détection de chutes (fall_score.json)."""
    try:
        data = cache.get("fall", lambda: read_json_file("fall_score.json"))
        
        if data is None:
            return create_error_response(
                "Fall data not available. Is lab2 running?",
                503
            )
        
        data["is_stale"] = is_stale(data)
        return jsonify(data)
    
    except Exception as e:
        return create_error_response(f"Error reading fall data: {str(e)}", 500)


@app.route("/api/motion", methods=["GET"])
def get_motion():
    """Retourne les données de classification de mouvement (motion_score.json)."""
    try:
        data = cache.get("motion", lambda: read_json_file("motion_score.json"))
        
        if data is None:
            return create_error_response(
                "Motion data not available. Is lab3 running?",
                503
            )
        
        data["is_stale"] = is_stale(data)
        return jsonify(data)
    
    except Exception as e:
        return create_error_response(f"Error reading motion data: {str(e)}", 500)


@app.route("/api/audio", methods=["GET"])
def get_audio():
    """Retourne les données de classification audio (audio_score.json)."""
    try:
        data = cache.get("audio", lambda: read_json_file("audio_score.json"))

        if data is None:
            return create_error_response(
                "Audio data not available. Is pc_mic/mic_classifier.py running?",
                503
            )

        data["is_stale"] = is_stale(data)
        return jsonify(data)

    except Exception as e:
        return create_error_response(f"Error reading audio data: {str(e)}", 500)


@app.route("/api/smoke", methods=["GET"])
def get_smoke():
    """Retourne les données de détection fumée (smoke_score.json)."""
    try:
        data = cache.get("smoke", lambda: read_json_file("smoke_score.json"))

        if data is None:
            return create_error_response(
                "Smoke data not available. Is smoke detector running?",
                503
            )

        data["is_stale"] = is_stale(data)
        return jsonify(data)

    except Exception as e:
        return create_error_response(f"Error reading smoke data: {str(e)}", 500)


@app.route("/api/context", methods=["GET"])
def get_context():
    """Retourne le contexte du match (match_context.json)."""
    try:
        data = cache.get("context", lambda: read_json_file("match_context.json"))
        
        if data is None:
            return create_error_response(
                "Context data not available. Is match_context_simulator.py running?",
                503
            )
        
        data["is_stale"] = is_stale(data, timeout_s=10.0)
        return jsonify(data)
    
    except Exception as e:
        return create_error_response(f"Error reading context data: {str(e)}", 500)


@app.errorhandler(404)
def not_found(error):
    """Handler pour les routes non trouvées."""
    return jsonify({
        "error": "Endpoint not found",
        "available_endpoints": [
            "/api/health",
            "/api/alert",
            "/api/person",
            "/api/fall",
            "/api/motion",
            "/api/audio",
            "/api/smoke",
            "/api/context"
        ]
    }), 404


# ─────────────────────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────────────────────
if __name__ == "__main__":
    # Créer le dossier output s'il n'existe pas
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    
    print("=" * 60)
    print("  StadiumGuard REST API Server")
    print("=" * 60)
    print(f"  Output directory : {os.path.abspath(OUTPUT_DIR)}")
    print(f"  Cache TTL        : {CACHE_TTL_MS}ms")
    print(f"  CORS enabled for : http://localhost:3101")
    print(f"  Server URL       : http://localhost:{PORT}")
    print("=" * 60)
    print("\nEndpoints disponibles :")
    print(f"  • GET http://localhost:{PORT}/api/health")
    print(f"  • GET http://localhost:{PORT}/api/alert")
    print(f"  • GET http://localhost:{PORT}/api/person")
    print(f"  • GET http://localhost:{PORT}/api/fall")
    print(f"  • GET http://localhost:{PORT}/api/motion")
    print(f"  • GET http://localhost:{PORT}/api/audio")
    print(f"  • GET http://localhost:{PORT}/api/smoke")
    print(f"  • GET http://localhost:{PORT}/api/context")
    print("\nCtrl+C pour arrêter.\n")
    
    # Lancer le serveur Flask
    app.run(
        host="0.0.0.0",
        port=PORT,
        debug=False,  # Mettre True pour le dev
        threaded=True
    )
