# 🚀 Démarrage Rapide - StadiumGuard

## ⚡ Installation Express (5 minutes)

### 1️⃣ Installer les dépendances

**Backend Python :**
```bash
pip install -r backend/requirements.txt
```

**Frontend Node.js :**
```bash
cd frontend
npm install
cd ..
```

---

## 🎬 Lancement Automatique (Windows)

### Option A : Scripts Batch (Recommandé)

**Double-cliquez sur :**
1. `start_backend.bat` → Lance API + Orchestrator
2. `start_frontend.bat` → Lance le dashboard Vite

**Ouvrez votre navigateur sur :** http://localhost:3101

---

## 🎮 Lancement Manuel (3 terminaux)

### Terminal 1 : Backend Python
```bash
python backend/orchestrator.py
```

### Terminal 2 : API Server
```bash
python backend/api_server.py
```

### Terminal 3 : Frontend
```bash
cd frontend
npm run dev
```

**Ouvrez :** http://localhost:3101

---

## ✅ Vérification Rapide

### Test 1 : API fonctionne ?
```bash
python test_api.py
```

Vous devriez voir :
```
✅ PASS - Santé du serveur
✅ PASS - Score d'alerte fusionné
...
📊 Résultat: 6/6 tests réussis
```

### Test 2 : Dashboard connecté ?

1. Ouvrez http://localhost:3101
2. Vérifiez que le point vert est allumé (en haut à droite)
3. Cliquez sur **"Connect Backend"**
4. Les métriques doivent se mettre à jour en temps réel

---

## 🎯 Test du Simulateur de Contexte

1. Lancez le simulateur de match :
```bash
python backend/match_context_simulator.py
```

2. Dans le terminal du simulateur, appuyez sur **[G]** (Goal)

3. Dans le dashboard, le **Threat Score** devrait **baisser** immédiatement

---

## 🐛 Problèmes Courants

### ❌ "Backend offline"

**Cause :** L'API server ne tourne pas

**Solution :**
```bash
python backend/api_server.py
```

### ❌ "Port 5000 already in use"

**Solution Windows :**
```cmd
netstat -ano | findstr :5000
taskkill /PID <PID> /F
```

### ❌ "CORS error"

**Cause :** flask-cors pas installé

**Solution :**
```bash
pip install flask-cors
```

### ❌ "Module not found: ultralytics"

**Solution :**
```bash
pip install ultralytics opencv-python numpy
```

---

## 📊 URLs Importantes

| Service | URL | Description |
|---------|-----|-------------|
| Frontend | http://localhost:3101 | Dashboard principal |
| API Health | http://localhost:5000/api/health | Santé de l'API |
| API Alert | http://localhost:5000/api/alert | Données fusionnées |

---

## 🎨 Fonctionnalités du Dashboard

### Métriques en Temps Réel
- **Persons** : Nombre de personnes détectées
- **Fall** : Statut de détection de chutes
- **Motion** : Niveau de mouvement de la foule
- **Threat** : Score de menace global (0-100)

### Graphiques
- Historique du nombre de personnes (30 derniers points)
- Historique du score de menace (30 derniers points)

### Journal d'Événements
- Changements de niveau d'alerte
- Détections de chutes
- Événements système

---

## 🔧 Configuration Avancée

### Changer le port de l'API

**Fichier :** `backend/api_server.py`
```python
PORT = 5000  # Modifier ici
```

**Fichier :** `frontend/notika/green-horizotal/src/js/main.js`
```javascript
this.backend = new BackendConnector('http://localhost:5000')  // Modifier ici
```

### Changer l'intervalle de polling

**Fichier :** `frontend/notika/green-horizotal/src/js/main.js`
```javascript
this.backend.startPolling(500)  // 500ms = 2 fois par seconde
```

### Changer le cache du backend

**Fichier :** `backend/api_server.py`
```python
CACHE_TTL_MS = 200  # Rafraîchir toutes les 200ms
```

---

## 📚 Documentation Complète

Pour plus de détails, consultez :
- **INTEGRATION_GUIDE.md** : Guide complet d'intégration
- **config.example.json** : Exemple de configuration

---

## 🎓 Architecture Simplifiée

```
Backend Python          API Flask           Frontend Vite
(orchestrator.py)   →   (port 5000)    →    (port 3101)
     ↓                       ↓                    ↓
  output/              Lit JSON           Affiche données
  *.json              toutes les 200ms    toutes les 500ms
```

---

## 💡 Astuces

1. **Mode Démo** : Si le backend n'est pas disponible, le frontend bascule automatiquement en mode simulateur

2. **Logs** : Surveillez les terminaux pour voir les requêtes en temps réel

3. **Performance** : Ajustez `CACHE_TTL_MS` et `polling_interval_ms` selon vos besoins

4. **Debug** : Ouvrez la console du navigateur (F12) pour voir les requêtes fetch()

---

## 🆘 Besoin d'Aide ?

1. Vérifiez que tous les services tournent (3 terminaux)
2. Testez l'API avec `python test_api.py`
3. Consultez les logs dans les terminaux
4. Vérifiez les fichiers JSON dans `output/`

---

**Prêt à surveiller votre stade ! 🏟️🇲🇦**
