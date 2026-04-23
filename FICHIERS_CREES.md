# 📋 Fichiers Créés - Intégration Frontend-Backend

## 🆕 Nouveaux Fichiers

### Backend

| Fichier | Description | Rôle |
|---------|-------------|------|
| `backend/api_server.py` | Serveur REST Flask | Expose les JSON via API HTTP avec CORS |
| `backend/requirements.txt` | Dépendances Python | Liste des packages à installer |

### Frontend

| Fichier | Description | Rôle |
|---------|-------------|------|
| `frontend/notika/green-horizotal/src/js/modules/backend.js` | Module de connexion | Gère le polling et les callbacks |

### Scripts de Lancement

| Fichier | Description | Rôle |
|---------|-------------|------|
| `start_backend.bat` | Lanceur backend (Windows) | Démarre API + Orchestrator |
| `start_frontend.bat` | Lanceur frontend (Windows) | Démarre Vite dev server |

### Scripts de Test

| Fichier | Description | Rôle |
|---------|-------------|------|
| `test_api.py` | Test automatique de l'API | Vérifie tous les endpoints |
| `test_endpoints.bat` | Test manuel (Windows) | Teste avec curl |
| `debug_info.py` | Diagnostic complet | Collecte infos de débogage |
| `check_setup.py` | Vérification pré-lancement | Vérifie l'installation |

### Documentation

| Fichier | Description | Contenu |
|---------|-------------|---------|
| `README.md` | Documentation principale | Vue d'ensemble complète |
| `INTEGRATION_GUIDE.md` | Guide d'intégration | Instructions détaillées |
| `DEMARRAGE_RAPIDE.md` | Guide express | Démarrage en 5 minutes |
| `FICHIERS_CREES.md` | Ce fichier | Liste des fichiers créés |

### Configuration

| Fichier | Description | Rôle |
|---------|-------------|------|
| `config.example.json` | Exemple de config | Template de configuration |
| `.gitignore` | Exclusions Git | Fichiers à ne pas commiter |

---

## 🔄 Fichiers Modifiés

### Frontend

| Fichier | Modifications | Raison |
|---------|---------------|--------|
| `frontend/notika/green-horizotal/src/js/main.js` | Ajout de BackendConnector, méthodes de mise à jour | Intégration API backend |
| `frontend/vite.config.js` | Port changé de 3100 → 3101 | Cohérence avec la doc |

---

## 📊 Résumé

### Nouveaux Fichiers
- **Backend** : 2 fichiers
- **Frontend** : 1 fichier
- **Scripts** : 6 fichiers
- **Documentation** : 4 fichiers
- **Configuration** : 2 fichiers

**Total** : 15 nouveaux fichiers

### Fichiers Modifiés
- **Frontend** : 2 fichiers

---

## 🎯 Fonctionnalités Ajoutées

### 1. API REST Backend
- ✅ Serveur Flask sur port 5000
- ✅ 6 endpoints REST (health, alert, person, fall, motion, context)
- ✅ CORS activé pour localhost:3101
- ✅ Cache en mémoire (200ms TTL)
- ✅ Gestion d'erreurs robuste

### 2. Connexion Frontend
- ✅ Module BackendConnector avec polling
- ✅ Callbacks pour data/error/connect/disconnect
- ✅ Mise à jour automatique du DOM
- ✅ Détection automatique backend online/offline
- ✅ Fallback sur simulateur si backend absent

### 3. Scripts de Lancement
- ✅ Lanceurs Windows (.bat)
- ✅ Scripts de test automatiques
- ✅ Diagnostic et vérification

### 4. Documentation
- ✅ README principal avec badges
- ✅ Guide d'intégration complet
- ✅ Guide de démarrage rapide
- ✅ Diagrammes d'architecture

---

## 🔍 Détails Techniques

### API Server (`backend/api_server.py`)

**Caractéristiques :**
- Framework : Flask 3.0+
- CORS : flask-cors
- Cache : In-memory avec TTL configurable
- Endpoints : 6 routes REST
- Port : 5000 (configurable)
- Timeout : 5s pour données périmées

**Endpoints :**
```
GET /api/health   → Status du serveur
GET /api/alert    → Score fusionné (principal)
GET /api/person   → Détection de personnes
GET /api/fall     → Détection de chutes
GET /api/motion   → Classification de mouvement
GET /api/context  → Contexte du match
```

### Backend Connector (`frontend/.../backend.js`)

**Caractéristiques :**
- Polling : 500ms par défaut (configurable)
- Mode : CORS avec fetch()
- Callbacks : onData, onError, onConnect, onDisconnect
- Reconnexion : Automatique
- Gestion d'erreurs : Robuste avec fallback

**Méthodes principales :**
```javascript
startPolling(intervalMs)    // Démarre le polling
stopPolling()               // Arrête le polling
fetchAlertData()            // Récupère les données
checkHealth()               // Vérifie la santé de l'API
```

### Main.js Modifications

**Ajouts :**
- Import de BackendConnector
- Méthode `setupBackend()` pour les callbacks
- Méthode `updateDashboardFromBackend(data)` pour MAJ DOM
- Méthode `toggleBackend()` pour connect/disconnect
- Méthodes utilitaires : `updateElement()`, `updateAlertLevel()`, etc.

**Comportement :**
- Détection automatique du backend au démarrage
- Bascule automatique simulateur ↔ backend
- Mise à jour temps réel des métriques
- Journal d'événements avec horodatage

---

## 🚀 Utilisation

### Installation
```bash
# Backend
pip install -r backend/requirements.txt

# Frontend
cd frontend && npm install
```

### Lancement (Windows)
```bash
# Double-clic sur :
start_backend.bat    # Lance API + Orchestrator
start_frontend.bat   # Lance Vite
```

### Lancement (Linux/Mac)
```bash
# Terminal 1
python backend/orchestrator.py

# Terminal 2
python backend/api_server.py

# Terminal 3
cd frontend && npm run dev
```

### Test
```bash
python test_api.py           # Test automatique
python check_setup.py        # Vérification installation
python debug_info.py         # Diagnostic complet
```

---

## 📝 Notes Importantes

### Ports Utilisés
- **5000** : API Server Flask
- **3101** : Frontend Vite
- **5001** : Video stream (optionnel, non implémenté)

### Fichiers JSON
Les fichiers dans `output/` sont lus par l'API :
- `person_score.json`
- `fall_score.json`
- `motion_score.json`
- `match_context.json`
- `final_alert.json`

### CORS
L'API autorise les requêtes depuis :
- `http://localhost:3101`
- `http://127.0.0.1:3101`

Pour ajouter d'autres origines, modifier `backend/api_server.py` :
```python
CORS(app, resources={
    r"/api/*": {
        "origins": ["http://localhost:3101", "http://autre-origine.com"],
        ...
    }
})
```

---

## 🎓 Architecture Finale

```
┌─────────────┐         ┌─────────────┐         ┌─────────────┐
│  Backend    │  JSON   │  API Flask  │  REST   │  Frontend   │
│  Python     │ ──────> │  (5000)     │ <────── │  Vite       │
│             │  files  │  + CORS     │  HTTP   │  (3101)     │
└─────────────┘         └─────────────┘         └─────────────┘
```

---

## ✅ Checklist de Validation

- [ ] `pip install -r backend/requirements.txt` exécuté
- [ ] `cd frontend && npm install` exécuté
- [ ] `python check_setup.py` retourne "TOUT EST PRÊT"
- [ ] `python test_api.py` retourne "6/6 tests réussis"
- [ ] Backend démarre sans erreur
- [ ] Frontend affiche "Backend API connected"
- [ ] Métriques se mettent à jour en temps réel
- [ ] Appuyer sur [G] dans le simulateur baisse le threat-score

---

## 🆘 Support

En cas de problème :
1. Exécuter `python debug_info.py`
2. Consulter `DEMARRAGE_RAPIDE.md`
3. Vérifier les logs des terminaux
4. Tester avec `python test_api.py`

---

**Intégration complète réalisée avec succès ! 🎉**
