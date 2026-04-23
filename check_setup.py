#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
check_setup.py — Vérification de l'installation
===============================================
Vérifie que tout est prêt pour lancer StadiumGuard.

Usage: python check_setup.py
"""

import sys
import os

def check(condition, success_msg, error_msg):
    """Vérifie une condition et affiche le résultat."""
    if condition:
        print(f"✅ {success_msg}")
        return True
    else:
        print(f"❌ {error_msg}")
        return False

def main():
    print("=" * 60)
    print("  StadiumGuard - Vérification de l'Installation")
    print("=" * 60)
    print()
    
    all_ok = True
    
    # 1. Version Python
    print("🐍 Python")
    major, minor = sys.version_info[:2]
    all_ok &= check(
        major >= 3 and minor >= 8,
        f"Python {major}.{minor} (compatible)",
        f"Python {major}.{minor} (requis: >= 3.8)"
    )
    print()
    
    # 2. Dépendances Python
    print("📦 Dépendances Backend")
    deps = ["flask", "flask_cors", "cv2", "ultralytics", "numpy"]
    for dep in deps:
        try:
            __import__(dep)
            all_ok &= check(True, f"{dep} installé", "")
        except ImportError:
            all_ok &= check(False, "", f"{dep} manquant (pip install {dep})")
    print()
    
    # 3. Fichiers backend
    print("📁 Fichiers Backend")
    backend_files = [
        "backend/api_server.py",
        "backend/orchestrator.py",
        "backend/camera_server.py",
        "backend/requirements.txt"
    ]
    for file in backend_files:
        all_ok &= check(
            os.path.exists(file),
            f"{file} présent",
            f"{file} manquant"
        )
    print()
    
    # 4. Dossier frontend
    print("🎨 Frontend")
    all_ok &= check(
        os.path.exists("frontend/package.json"),
        "package.json présent",
        "package.json manquant"
    )
    all_ok &= check(
        os.path.exists("frontend/node_modules"),
        "node_modules présent (npm install fait)",
        "node_modules manquant (exécuter: cd frontend && npm install)"
    )
    print()
    
    # 5. Dossier output
    print("📂 Dossier Output")
    if not os.path.exists("output"):
        os.makedirs("output")
        print("✅ Dossier output créé")
    else:
        print("✅ Dossier output existe")
    print()
    
    # 6. Scripts de lancement
    print("🚀 Scripts de Lancement")
    scripts = ["start_backend.bat", "start_frontend.bat"]
    for script in scripts:
        all_ok &= check(
            os.path.exists(script),
            f"{script} présent",
            f"{script} manquant"
        )
    print()
    
    # Résumé
    print("=" * 60)
    if all_ok:
        print("✅ TOUT EST PRÊT !")
        print()
        print("Prochaines étapes:")
        print("  1. Double-cliquez sur start_backend.bat")
        print("  2. Double-cliquez sur start_frontend.bat")
        print("  3. Ouvrez http://localhost:3101")
        print()
        print("Ou consultez DEMARRAGE_RAPIDE.md pour plus de détails.")
        return 0
    else:
        print("❌ INSTALLATION INCOMPLÈTE")
        print()
        print("Actions requises:")
        print("  • Installer les dépendances: pip install -r backend/requirements.txt")
        print("  • Installer le frontend: cd frontend && npm install")
        print("  • Vérifier les fichiers manquants ci-dessus")
        print()
        print("Consultez INTEGRATION_GUIDE.md pour l'aide complète.")
        return 1

if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print("\n\n⏹️  Vérification interrompue.")
        sys.exit(130)
