# 🏟️ StadiumGuard - AI Stadium Monitoring System

<div align="center">

![StadiumGuard](https://img.shields.io/badge/Morocco-2030-green?style=for-the-badge)
![Python](https://img.shields.io/badge/Python-3.8+-blue?style=for-the-badge&logo=python)
![Flask](https://img.shields.io/badge/Flask-3.0+-black?style=for-the-badge&logo=flask)
![Vite](https://img.shields.io/badge/Vite-7.x-646CFF?style=for-the-badge&logo=vite)
![Bootstrap](https://img.shields.io/badge/Bootstrap-5.3-7952B3?style=for-the-badge&logo=bootstrap)

**Système de surveillance IA pour stades - Détection en temps réel de menaces et d'incidents**

[Démarrage Rapide](#-démarrage-rapide) • [Documentation](#-documentation) • [Architecture](#-architecture) • [Démo](#-démo)

</div>

---

## 🎯 Fonctionnalités

### 🔍 Détection IA Multi-Modules

- **Lab1 - Person Tracking** : Détection et suivi de personnes (YOLOv8)
- **Lab2 - Fall Detection** : Détection de chutes avec analyse de pose
- **Lab3 - Motion Classifier** : Classification de mouvements de foule (CALM, CELEBRATION, FIGHT, STAMPEDE)
- **Orchestrator** : Fusion intelligente des scores avec contexte du match

### 📊 Dashboard Temps Réel

- Métriques en direct (personnes, chutes, mouvement, menace)
- Graphiques historiques interactifs
- Journal d'événements avec horodatage
- Niveaux d'alerte dynamiques (LOW, MEDIUM, HIGH, CRITICAL)

### 🔌 API REST

- Endpoints RESTful avec CORS
- Cache en mémoire (200ms TTL)
- Gestion d'erreurs robuste
- Support multi-origine

---

## 🚀 Démarrage Rapide

### Installation (5 minutes)

```bash
# 1. Backend Python
pip install -r backend/requirements.txt

# 2. Frontend Node.js
cd frontend
npm install
cd ..
```

### Lancement (Windows)

**Double-cliquez sur :**
1. `start_backend.bat` → Lance `camera_server` + `match_context` + `orchestrator` (mode ESP32 unifie)
2. `start_frontend.bat` → Lance le dashboard

**Ouvrez :** http://localhost:3101

### Lancement (Linux/Mac)

```bash
# Terminal 1 : Camera server (API + endpoints ESP32 + audio stream)
python backend/camera_server.py

# Terminal 2 : Match context simulator
python backend/match_context_simulator.py

# Terminal 3 : Orchestrator
python backend/orchestrator.py

# Terminal 4 : Frontend
cd frontend && npm run dev
```

### Test de Validation

```bash
# Tester l'API
python test_api.py

# Tester les endpoints
curl http://localhost:5000/api/health
```

---

## 📁 Structure du Projet

```
StadiumGuard/
├── backend/
│   ├── api_server.py          # Serveur REST standalone (sans endpoints ESP32)
│   ├── orchestrator.py        # Fusion des scores
│   ├── camera_server.py       # Capture caméra + labs
│   ├── lab1.py                # Person tracking
│   ├── lab2.py                # Fall detection
│   ├── lab3.py                # Motion classifier
│   ├── match_context_simulator.py  # Simulateur de match
│   └── requirements.txt       # Dépendances Python
│
├── frontend/
│   └── notika/green-horizotal/
│       ├── index.html         # Dashboard principal
│       └── src/js/
│           ├── main.js        # 🔄 Modifié (backend integration)
│           └── modules/
│               ├── backend.js # 🆕 Connexion API
│               ├── ui.js      # Interface utilisateur
│               ├── simulator.js  # Mode démo
│               └── charts.js  # Graphiques
│
├── output/                    # Fichiers JSON générés
│   ├── person_score.json
│   ├── fall_score.json
│   ├── motion_score.json
│   └── final_alert.json
│
├── start_backend.bat          # 🆕 Lanceur backend (Windows)
├── start_frontend.bat         # 🆕 Lanceur frontend (Windows)
├── test_api.py                # 🆕 Script de test API
├── INTEGRATION_GUIDE.md       # 🆕 Guide complet
└── DEMARRAGE_RAPIDE.md        # 🆕 Guide express
```

---

## 🏗️ Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    FRONTEND (Vite)                          │
│                  http://localhost:3101                      │
│                                                             │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐  │
│  │ Persons  │  │   Fall   │  │  Motion  │  │  Threat  │  │
│  │  Chart   │  │  Status  │  │  Level   │  │  Score   │  │
│  └──────────┘  └──────────┘  └──────────┘  └──────────┘  │
│                                                             │
│              Polling toutes les 500ms (fetch)              │
└─────────────────────────┬───────────────────────────────────┘
                          │ HTTP GET
                          ↓
┌─────────────────────────────────────────────────────────────┐
│                  API SERVER (Flask)                         │
│                 http://localhost:5000                       │
│                                                             │
│  Endpoints:                    Cache (200ms TTL)           │
│  • GET /api/health             ┌──────────────┐            │
│  • GET /api/alert    ←────────→│  In-Memory   │            │
│  • GET /api/person             │    Cache     │            │
│  • GET /api/fall               └──────────────┘            │
│  • GET /api/motion                                          │
│  • GET /api/context                                         │
│                                                             │
│              Lit JSON toutes les 200ms                      │
└─────────────────────────┬───────────────────────────────────┘
                          │ File I/O
                          ↓
┌─────────────────────────────────────────────────────────────┐
│                    OUTPUT DIRECTORY                         │
│                                                             │
│  ┌──────────────────┐  ┌──────────────────┐               │
│  │ person_score.json│  │  fall_score.json │               │
│  └──────────────────┘  └──────────────────┘               │
│  ┌──────────────────┐  ┌──────────────────┐               │
│  │motion_score.json │  │final_alert.json  │               │
│  └──────────────────┘  └──────────────────┘               │
│                                                             │
│              Écrits toutes les 0.5s                         │
└─────────────────────────┬───────────────────────────────────┘
                          │
                          ↑
┌─────────────────────────────────────────────────────────────┐
│                  BACKEND PYTHON                             │
│                                                             │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐    │
│  │   Lab1       │  │    Lab2      │  │    Lab3      │    │
│  │   Person     │  │    Fall      │  │   Motion     │    │
│  │  Tracking    │  │  Detection   │  │ Classifier   │    │
│  └──────────────┘  └──────────────┘  └──────────────┘    │
│         │                 │                  │             │
│         └─────────────────┴──────────────────┘             │
│                           │                                │
│                           ↓                                │
│                  ┌──────────────────┐                      │
│                  │  Orchestrator    │                      │
│                  │  (Fusion Engine) │                      │
│                  └──────────────────┘                      │
│                           │                                │
│                           ↓                                │
│                  ┌──────────────────┐                      │
│                  │ Match Context    │                      │
│                  │   Simulator      │                      │
│                  └──────────────────┘                      │
└─────────────────────────────────────────────────────────────┘
```

---

## 🔌 Endpoints API

| Endpoint | Description | Fichier Source |
|----------|-------------|----------------|
| `GET /api/health` | Santé du serveur | - |
| `GET /api/alert` | Score fusionné (principal) | `final_alert.json` |
| `GET /api/person` | Détection de personnes | `person_score.json` |
| `GET /api/fall` | Détection de chutes | `fall_score.json` |
| `GET /api/motion` | Classification de mouvement | `motion_score.json` |
| `GET /api/context` | Contexte du match | `match_context.json` |

### Exemple de Réponse

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
  "match": {
    "state": "playing",
    "minute": 67,
    "score": "2-1",
    "multiplier": 1.2
  },
  "is_stale": false
}
```

---

## 🎮 Utilisation

### Mode Backend Réel

1. Lancez les 3 services (backend, API, frontend)
2. Ouvrez http://localhost:3101
3. Cliquez sur **"Connect Backend"**
4. Les métriques se mettent à jour en temps réel

### Mode Simulateur

Si le backend n'est pas disponible :
1. Le frontend détecte automatiquement l'absence de backend
2. Cliquez sur **"Start Demo"**
3. Le simulateur génère des données aléatoires

### Test du Contexte de Match

1. Lancez `python backend/match_context_simulator.py`
2. Appuyez sur **[G]** pour simuler un but
3. Le score de menace baisse dans le dashboard

---

## 🛠️ Technologies

### Backend
- **Python 3.8+**
- **Flask 3.0** - API REST
- **Flask-CORS** - Support CORS
- **OpenCV** - Traitement vidéo
- **Ultralytics YOLOv8** - Détection d'objets
- **NumPy** - Calculs numériques

### Frontend
- **Vite 7.x** - Build tool
- **Bootstrap 5.3** - UI framework
- **Chart.js 4.5** - Graphiques
- **Font Awesome 7.2** - Icônes
- **Day.js** - Gestion des dates

---

## 📚 Documentation

- **[DEMARRAGE_RAPIDE.md](DEMARRAGE_RAPIDE.md)** - Guide express (5 min)
- **[INTEGRATION_GUIDE.md](INTEGRATION_GUIDE.md)** - Guide complet d'intégration
- **[config.example.json](config.example.json)** - Exemple de configuration

---

## 🧪 Tests

### Test Automatique
```bash
python test_api.py
```

### Test Manuel (Windows)
```bash
test_endpoints.bat
```

### Test Manuel (Linux/Mac)
```bash
curl http://localhost:5000/api/health | python -m json.tool
curl http://localhost:5000/api/alert | python -m json.tool
```

---

## 🐛 Dépannage

### Backend Offline
```bash
# Vérifier que l'API tourne
curl http://localhost:5000/api/health

# Relancer le backend unifie (mode ESP32)
python backend/camera_server.py
```

### Port Occupé
```cmd
# Windows
netstat -ano | findstr :5000
taskkill /PID <PID> /F
```

### Erreur CORS
```bash
pip install flask-cors
```

---

## 📊 Métriques du Dashboard

| Métrique | Description | Source |
|----------|-------------|--------|
| **Persons** | Nombre de personnes détectées | Lab1 (YOLOv8) |
| **Fall** | Statut de détection de chutes | Lab2 (Pose estimation) |
| **Motion** | Niveau de mouvement de foule | Lab3 (Optical flow) |
| **Threat** | Score de menace global (0-100) | Orchestrator (fusion) |

---

## 🎯 Roadmap

- [x] Backend Python (Labs 1-3)
- [x] Orchestrator avec fusion de scores
- [x] API REST Flask avec CORS
- [x] Frontend Vite avec polling
- [x] Graphiques temps réel
- [x] Mode simulateur
- [ ] WebSocket pour réduire la latence
- [ ] Stream vidéo MJPEG intégré
- [ ] Base de données pour historique
- [ ] Authentification JWT
- [ ] Conteneurisation Docker

---

## 📄 Licence

MIT License - Voir [LICENSE](LICENSE) pour plus de détails.

---

## 👥 Contributeurs

Développé pour **Morocco 2030** 🇲🇦

---

## 🆘 Support

En cas de problème :
1. Consultez [DEMARRAGE_RAPIDE.md](DEMARRAGE_RAPIDE.md)
2. Vérifiez les logs des terminaux
3. Testez avec `python test_api.py`
4. Vérifiez les fichiers JSON dans `output/`

---

<div align="center">

**Fait avec ❤️ pour la sécurité des stades**

[⬆ Retour en haut](#-stadiumguard---ai-stadium-monitoring-system)

</div>
