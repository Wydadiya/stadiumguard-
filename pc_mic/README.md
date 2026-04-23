# Mic Classifier PC — Temps réel

Même algorithme que l'ESP32, mais via le microphone de ta machine.

## Installation

```bash
pip install -r requirements.txt
```

Sur Linux si erreur PortAudio :
```bash
sudo apt install libportaudio2
pip install -r requirements.txt
```

Sur Mac si erreur PortAudio :
```bash
brew install portaudio
pip install -r requirements.txt
```

## Utilisation

### Lister les micros disponibles
```bash
python3 mic_classifier.py --list
```

### Lancer avec le micro par défaut
```bash
python3 mic_classifier.py
```

### Lancer avec un micro spécifique
```bash
python3 mic_classifier.py --device 2
```

## Procédure de test

1. Lancer le script
2. Jouer un des 4 fichiers audio (haut-parleur ou écouteurs) devant le micro
3. Observer la détection en temps réel dans le terminal
4. Ctrl+C pour arrêter

## Sortie attendue

```
[14:32:01]  🔇  SILENCE                    rms=0.002 cent=312Hz
[14:32:05]  💣  BOMBES                     (votes: sil=0 chant=0 bag=1 bom=7)  centroid≈2582Hz
[14:32:12]  ⚠️   BAGARRE                    (votes: sil=0 chant=1 bag=7 bom=0)  centroid≈1849Hz
```

## Résultats attendus par fichier

| Fichier audio   | Détection             |
|-----------------|-----------------------|
| normal.mp3      | 🔇 silence            |
| support.mp3     | 🎵 chants supportaires|
| bagarre.mp3     | ⚠️  bagarre           |
| fumigenes.mp3   | 💣 bombes             |
