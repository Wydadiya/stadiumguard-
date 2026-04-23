#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
debug_info.py — Collecte d'informations de débogage
===================================================
Affiche l'état complet du système StadiumGuard pour le débogage.

Usage: python debug_info.py
"""

import os
import sys
import json
import time
from datetime import datetime
import platform

def print_header(text):
    """Affiche un en-tête."""
    print("\n" + "=" * 60)
    print(f"  {text}")
    print("=" * 60)

def print_section(text):
    """Affiche une section."""
    print(f"\n{text}")
    print("-" * 60)

def check_python_version():
    """Vérifie la version de Python."""
    print_section("🐍 Python")
    print(f"Version: {sys.version}")
    print(f"Executable: {sys.executable}")
    
    major, minor = sys.version_info[:2]
    if major >= 3 and minor >= 8:
        print("✅ Version compatible (>= 3.8)")
    else:
        print("❌ Version trop ancienne (< 3.8)")

def check_dependencies():
    """Vérifie les dépendances Python."""
    print_section("📦 Dépendances Python")
    
    deps = [
        ("flask", "Flask"),
        ("flask_cors", "Flask-CORS"),
        ("cv2", "OpenCV"),
        ("ultralytics", "Ultralytics"),
        ("numpy", "NumPy"),
    ]
    
    for module_name, display_name in deps:
        try:
            module = __import__(module_name)
            version = getattr(module, "__version__", "unknown")
            print(f"✅ {display_name:<15} {version}")
        except ImportError:
            print(f"❌ {display_name:<15} NOT INSTALLED")

def check_output_dir():
    """Vérifie le dossier output et les fichiers JSON."""
    print_section("📁 Dossier Output")
    
    output_dir = "output"
    
    if not os.path.exists(output_dir):
        print(f"❌ Dossier '{output_dir}' n'existe pas")
        return
    
    print(f"✅ Dossier: {os.path.abspath(output_dir)}")
    
    json_files = [
        "person_score.json",
        "fall_score.json",
        "motion_score.json",
        "match_context.json",
        "final_alert.json"
    ]
    
    print("\nFichiers JSON:")
    for filename in json_files:
        path = os.path.join(output_dir, filename)
        
        if not os.path.exists(path):
            print(f"  ⏳ {filename:<25} N'existe pas encore")
            continue
        
        # Lire le fichier
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            
            # Vérifier le timestamp
            timestamp = data.get("timestamp", 0)
            age = time.time() - timestamp
            
            size = os.path.getsize(path)
            
            if age < 5.0:
                status = "✅ FRAIS"
            elif age < 30.0:
                status = "⚠️  VIEUX"
            else:
                status = "❌ PÉRIMÉ"
            
            print(f"  {status} {filename:<25} {size:>6} bytes  "
                  f"Age: {age:.1f}s")
            
            # Afficher quelques infos clés
            if "score" in data:
                print(f"       → Score: {data['score']:.1f}")
            if "final_score" in data:
                print(f"       → Final Score: {data['final_score']:.1f}")
                print(f"       → Level: {data.get('level', 'N/A')}")
        
        except json.JSONDecodeError:
            print(f"  ❌ {filename:<25} JSON invalide")
        except Exception as e:
            print(f"  ❌ {filename:<25} Erreur: {str(e)}")

def check_ports():
    """Vérifie si les ports sont utilisés."""
    print_section("🔌 Ports")
    
    import socket
    
    ports = [
        (5000, "API Server"),
        (3101, "Frontend Vite"),
        (5001, "Video Stream (optionnel)")
    ]
    
    for port, name in ports:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        result = sock.connect_ex(('localhost', port))
        sock.close()
        
        if result == 0:
            print(f"✅ Port {port:<5} ({name:<25}) EN COURS D'UTILISATION")
        else:
            print(f"⏳ Port {port:<5} ({name:<25}) Libre")

def check_api_health():
    """Vérifie la santé de l'API."""
    print_section("🏥 Santé de l'API")
    
    try:
        import requests
        
        url = "http://localhost:5000/api/health"
        response = requests.get(url, timeout=2)
        
        if response.status_code == 200:
            data = response.json()
            print(f"✅ API accessible sur {url}")
            print(f"   Service: {data.get('service', 'N/A')}")
            print(f"   Version: {data.get('version', 'N/A')}")
            print(f"   Cache TTL: {data.get('cache_ttl_ms', 'N/A')}ms")
        else:
            print(f"❌ API retourne HTTP {response.status_code}")
    
    except ImportError:
        print("⚠️  Module 'requests' non installé (pip install requests)")
    except Exception as e:
        print(f"❌ API inaccessible: {str(e)}")

def check_system_info():
    """Affiche les informations système."""
    print_section("💻 Système")
    
    print(f"OS: {platform.system()} {platform.release()}")
    print(f"Architecture: {platform.machine()}")
    print(f"Processeur: {platform.processor()}")
    print(f"Hostname: {platform.node()}")

def main():
    """Fonction principale."""
    print_header("StadiumGuard - Informations de Débogage")
    print(f"Date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    check_system_info()
    check_python_version()
    check_dependencies()
    check_output_dir()
    check_ports()
    check_api_health()
    
    print_header("Fin du Diagnostic")
    print("\n💡 Conseils:")
    print("  • Si des dépendances manquent: pip install -r backend/requirements.txt")
    print("  • Si les fichiers JSON sont périmés: relancer orchestrator.py")
    print("  • Si l'API est inaccessible: relancer api_server.py")
    print("  • Si les ports sont occupés: tuer les processus ou changer les ports")
    print()

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n⏹️  Diagnostic interrompu.")
        sys.exit(130)
