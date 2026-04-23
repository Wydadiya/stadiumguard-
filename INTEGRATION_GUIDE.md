# 🎯 Guide d'Intégration Frontend-Backend StadiumGuard

## 📦 Architecture

```
┌─────────────────┐         ┌──────────────────┐         ┌─────────────────┐
│   Backend       │         │   API Server     │         │   Frontend      │
│   Python        │  JSON   │   Flask          │  REST   │   Vite          │
│                 │ ──────> │   (port 5000)    │ <────── │   (port 3101)   │
│ • camera_server │  files  │   + CORS         │  HTTP   │   + Polling     │
│ • orchestrator  │         │   + Cache        │         │   + Charts      │
│ • lab1/2/3      │         │                  │         │                 │
└─────────────────┘         └──────────────────┘         └─────────────────┘
       ↓                              ↓                           ↓
   output/                      Lit JSON                   Affiche données
   ├─ person_score.json         toutes les 200ms           en temps réel
   ├─ fall_score.json
   ├─ motion_score.json
   └─ final_alert.json
```

## 🚀 Installation

### Prérequis

**Backend (Python):**
```bash
pip install flask flask-cors ultralytics opencv-python numpy
```

**Frontend (Node.js):**
```bash
cd frontend
npm install
```

## 📋 Instructions de Lancement

### Option 1 : Mode Complet Unifie (recommande pour ESP32)

Ouvrez **4 terminaux** :

#### Terminal 1 : Camera server (API + endpoints ESP32 + streaming)
```bash
python backend/camera_server.py
```

#### Terminal 2 : Match context
```bash
python backend/match_context_simulator.py
```

#### Terminal 3 : Orchestrator
```bash
python backend/orchestrator.py
```

Vous devriez voir :
```
============================================================
  StadiumGuard REST API Server
============================================================
  Output directory : C:\...\output
  Cache TTL        : 200ms
  CORS enabled for : http://localhost:3101
  Server URL       : http://localhost:5000
============================================================

Endpoints disponibles :
  • GET http://localhost:5000/api/health
  • GET http://localhost:5000/api/alert
  • GET http://localhost:5000/api/person
  • GET http://localhost:5000/api/fall
  • GET http://localhost:5000/api/motion
  • GET http://localhost:5000/api/context
```

#### Terminal 4 : Frontend Vite
```bash
cd frontend
npm run dev
```

> Important: ne lancez pas `backend/api_server.py` en parallele de `backend/camera_server.py` (meme port 5000).

Ouvrez votre navigateur sur **http://localhost:3101**

Cliquez sur **"Connect Backend"** pour démarrer le polling.

---

### Option 2 : Mode Démo (Simulateur)

Si le backend n'est pas disponible, le frontend bascule automatiquement en mode simulateur.

```bash
cd frontend
npm run dev
```

Cliquez sur **"Start Demo"** pour lancer la simulation.

---

## 🔧 Configuration

### Modifier le port de l'API

**Backend (`backend/camera_server.py`):**
```python
flask_app.run(host='0.0.0.0', port=5000, debug=False, threaded=True)  # Changer ici
```

**Frontend (`frontend/notika/green-horizotal/src/js/main.js`):**
```javascript
this.backend = new BackendConnector('http://localhost:5000')  // Changer ici
```

### Modifier l'intervalle de polling

Dans `main.js` :
```javascript
this.backend.startPolling(500)  // 500ms par défaut
```

### Modifier le TTL du cache

Le mode unifie `camera_server.py` lit les JSON en direct (pas de cache TTL dedie).

---

## 🧪 Test de Validation

### 1. Vérifier que l'API fonctionne

```bash
curl http://localhost:5000/api/health
```

Réponse attendue :
```json
{
  "status": "ok",
  "service": "StadiumGuard API",
  "version": "1.0.0",
  "timestamp": 1234567890.123,
  "output_dir": "C:\\...\\output",
  "cache_ttl_ms": 200
}
```

### 2. Vérifier les données d'alerte

```bash
curl http://localhost:5000/api/alert
```

Réponse attendue :
```json
{
  "timestamp": 1234567890.123,
  "final_score": 45.2,
  "level": "MEDIUM",
  "scores": {
    "person": 30.0,
    "fall": 50.0,
    "motion": 40.0
  },
  "is_stale": false,
  ...
}
```

### 3. Test du simulateur de contexte

Dans le terminal du simulateur (`match_context_simulator.py`), appuyez sur **[G]** (Goal).

Le `threat_score` dans le dashboard devrait **baisser** (multiplicateur de contexte réduit).

---

## 📊 Endpoints API Disponibles

| Endpoint | Description | Fichier source |
|----------|-------------|----------------|
| `GET /api/health` | Santé du serveur | - |
| `GET /api/alert` | Score fusionné (principal) | `final_alert.json` |
| `GET /api/person` | Détection de personnes | `person_score.json` |
| `GET /api/fall` | Détection de chutes | `fall_score.json` |
| `GET /api/motion` | Classification de mouvement | `motion_score.json` |
| `GET /api/context` | Contexte du match | `match_context.json` |

---

## 🎨 Éléments DOM Mis à Jour

Le frontend met à jour automatiquement ces éléments :

| ID DOM | Donnée affichée | Source |
|--------|-----------------|--------|
| `#person-count` | Nombre de personnes | `data.scores.person` |
| `#threat-score` | Score de menace (0-100) | `data.final_score` |
| `#fall-status` | Statut de chute | `data.scores.fall` |
| `#motion-level` | Niveau de mouvement | `data.scores.motion` |
| `#alert-level` | Niveau d'alerte | `data.level` |
| `#system-status` | État du système | Connexion API |
| `#event-log` | Journal d'événements | Changements d'état |

---

## 🐛 Dépannage

### Erreur CORS

Si vous voyez dans la console :
```
Access to fetch at 'http://localhost:5000/api/alert' from origin 'http://localhost:3101' 
has been blocked by CORS policy
```

**Solution :** Vérifiez que `flask-cors` est installé :
```bash
pip install flask-cors
```

### Backend "Offline"

Si le frontend affiche "Backend offline" :

1. Vérifiez que `camera_server.py` tourne sur le port 5000
2. Testez manuellement : `curl http://localhost:5000/api/health`
3. Vérifiez les logs du serveur Flask

### Données périmées (is_stale: true)

Si `is_stale: true` dans la réponse API :

1. Vérifiez que `orchestrator.py` ou `camera_server.py` tourne
2. Vérifiez que les fichiers JSON sont créés dans `output/`
3. Les timestamps doivent être récents (< 5 secondes)

### Port déjà utilisé

Si le port 5000 est occupé :

**Windows :**
```cmd
netstat -ano | findstr :5000
taskkill /PID <PID> /F
```

**Linux/Mac :**
```bash
lsof -ti:5000 | xargs kill -9
```

---

## 📝 Structure des Fichiers Créés

```
backend/
├── camera_server.py       ← Serveur unifie (REST + endpoints ESP32 + streaming)
├── orchestrator.py        ← Existant (fusion)
└── lab1.py, lab2.py, lab3.py

frontend/
└── notika/green-horizotal/src/js/
    ├── main.js            ← Modifié (ajout backend)
    └── modules/
        ├── backend.js     ← Nouveau module de connexion
        ├── ui.js          ← Existant
        ├── simulator.js   ← Existant (fallback)
        └── charts.js      ← Existant

output/                    ← Créé automatiquement
├── person_score.json
├── fall_score.json
├── motion_score.json
└── final_alert.json
```

---

## ✅ Checklist de Validation

- [ ] `pip install flask flask-cors` installé
- [ ] `npm install` exécuté dans `frontend/`
- [ ] Terminal 1 : `python backend/camera_server.py` tourne (port 5000)
- [ ] Terminal 2 : `python backend/match_context_simulator.py` tourne
- [ ] Terminal 3 : `python backend/orchestrator.py` tourne
- [ ] Terminal 4 : `npm run dev` tourne (port 3101)
- [ ] `curl http://localhost:5000/api/health` retourne `{"status": "ok"}`
- [ ] Dashboard affiche "Backend API connected"
- [ ] Bouton "Connect Backend" démarre le polling
- [ ] Les métriques se mettent à jour en temps réel
- [ ] Appuyer sur [G] dans le simulateur baisse le threat-score

---

## 🎯 Prochaines Étapes (Optionnel)

1. **WebSocket** : Remplacer le polling par une connexion WebSocket pour réduire la latence
2. **Stream vidéo** : Intégrer le flux MJPEG sur `http://localhost:5001/stream`
3. **Historique** : Stocker les données dans une base (SQLite/PostgreSQL)
4. **Authentification** : Ajouter JWT pour sécuriser l'API
5. **Docker** : Conteneuriser backend + frontend

---

## 📞 Support

En cas de problème, vérifiez :
1. Les logs du serveur Flask (Terminal 2)
2. La console du navigateur (F12)
3. Les fichiers JSON dans `output/`
4. Les timestamps des données (`is_stale` flag)

---

**Fait avec ❤️ pour Morocco 2030 🇲🇦**
