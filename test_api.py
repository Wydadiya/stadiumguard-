#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
test_api.py — Script de test pour l'API StadiumGuard
====================================================
Teste tous les endpoints de l'API et affiche les résultats.

Usage: python test_api.py
"""

import requests
import json
import sys
from datetime import datetime

API_BASE_URL = "http://localhost:5000"
TIMEOUT = 5  # secondes

def print_header(text):
    """Affiche un en-tête formaté."""
    print("\n" + "=" * 60)
    print(f"  {text}")
    print("=" * 60)

def print_success(text):
    """Affiche un message de succès."""
    print(f"✅ {text}")

def print_error(text):
    """Affiche un message d'erreur."""
    print(f"❌ {text}")

def print_warning(text):
    """Affiche un avertissement."""
    print(f"⚠️  {text}")

def test_endpoint(endpoint, description):
    """
    Teste un endpoint de l'API.
    
    Args:
        endpoint: Chemin de l'endpoint (ex: "/api/health")
        description: Description du test
    
    Returns:
        bool: True si le test réussit, False sinon
    """
    url = f"{API_BASE_URL}{endpoint}"
    
    print(f"\n🔍 Test: {description}")
    print(f"   URL: {url}")
    
    try:
        response = requests.get(url, timeout=TIMEOUT)
        
        if response.status_code == 200:
            data = response.json()
            print_success(f"Status: {response.status_code} OK")
            
            # Afficher quelques infos clés
            if "timestamp" in data:
                ts = data["timestamp"]
                age = datetime.now().timestamp() - ts
                print(f"   📅 Timestamp: {datetime.fromtimestamp(ts).strftime('%H:%M:%S')}")
                print(f"   ⏱️  Age: {age:.2f}s")
            
            if "is_stale" in data:
                if data["is_stale"]:
                    print_warning("Données périmées (backend peut-être arrêté)")
                else:
                    print_success("Données fraîches")
            
            if "final_score" in data:
                print(f"   🎯 Score final: {data['final_score']:.1f}/100")
                print(f"   📊 Niveau: {data.get('level', 'N/A')}")
            
            if "score" in data:
                print(f"   📊 Score: {data['score']:.1f}")
                print(f"   🎯 Confiance: {data.get('confidence', 0):.2f}")
            
            if "status" in data:
                print(f"   💚 Status: {data['status']}")
            
            # Afficher le JSON complet (tronqué)
            json_str = json.dumps(data, indent=2, ensure_ascii=False)
            if len(json_str) > 500:
                json_str = json_str[:500] + "\n   ... (tronqué)"
            print(f"\n   Réponse JSON:\n   {json_str.replace(chr(10), chr(10) + '   ')}")
            
            return True
        
        elif response.status_code == 503:
            print_warning(f"Status: {response.status_code} Service Unavailable")
            data = response.json()
            print(f"   Message: {data.get('error', 'N/A')}")
            return False
        
        else:
            print_error(f"Status: {response.status_code}")
            return False
    
    except requests.exceptions.ConnectionError:
        print_error("Impossible de se connecter à l'API")
        print("   Vérifiez que api_server.py tourne sur le port 5000")
        return False
    
    except requests.exceptions.Timeout:
        print_error(f"Timeout après {TIMEOUT}s")
        return False
    
    except Exception as e:
        print_error(f"Erreur: {str(e)}")
        return False

def main():
    """Fonction principale."""
    print_header("Test de l'API StadiumGuard")
    print(f"URL de base: {API_BASE_URL}")
    print(f"Timeout: {TIMEOUT}s")
    
    # Liste des tests à effectuer
    tests = [
        ("/api/health", "Santé du serveur"),
        ("/api/alert", "Score d'alerte fusionné"),
        ("/api/person", "Détection de personnes"),
        ("/api/fall", "Détection de chutes"),
        ("/api/motion", "Classification de mouvement"),
        ("/api/context", "Contexte du match"),
    ]
    
    results = []
    
    for endpoint, description in tests:
        success = test_endpoint(endpoint, description)
        results.append((description, success))
    
    # Résumé
    print_header("Résumé des Tests")
    
    passed = sum(1 for _, success in results if success)
    total = len(results)
    
    for description, success in results:
        status = "✅ PASS" if success else "❌ FAIL"
        print(f"{status} - {description}")
    
    print(f"\n📊 Résultat: {passed}/{total} tests réussis")
    
    if passed == total:
        print_success("Tous les tests sont passés !")
        return 0
    elif passed == 0:
        print_error("Aucun test n'est passé. Vérifiez que l'API tourne.")
        return 1
    else:
        print_warning("Certains tests ont échoué. Vérifiez les logs ci-dessus.")
        return 1

if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print("\n\n⏹️  Tests interrompus par l'utilisateur.")
        sys.exit(130)
