@echo off
echo ============================================================
echo   StadiumGuard Backend Launcher
echo ============================================================
echo.

REM Vérifier si Python est installé
python --version >nul 2>&1
if errorlevel 1 (
    echo [ERREUR] Python n'est pas installe ou pas dans le PATH
    pause
    exit /b 1
)

REM Créer le dossier output
if not exist "output" mkdir output

echo [1/5] Demarrage du Camera Server + Streaming (port 5000)...
echo.
start "StadiumGuard Camera Server" cmd /k "python backend/camera_server.py"

timeout /t 2 /nobreak >nul

echo [2/5] Demarrage du Simulateur de contexte match...
echo.
start "StadiumGuard Match Context" cmd /k "python backend/match_context_simulator.py"

timeout /t 1 /nobreak >nul

echo [3/5] Demarrage de l'Orchestrator...
echo.
start "StadiumGuard Orchestrator" cmd /k "python backend/orchestrator.py"

timeout /t 1 /nobreak >nul

echo [4/5] Mode audio ESP32 active (pc_mic desactive)...
echo.
echo [INFO] Le module pc_mic/mic_classifier.py n'est pas lance.
echo [INFO] Utilisez POST /api/esp32/audio depuis l'ESP32 pour alimenter l'audio.

timeout /t 1 /nobreak >nul

echo [5/5] Mode gaz ESP32 active (smoke_simulator desactive)...
echo.
echo [INFO] Le module backend/smoke_simulator.py n'est pas lance.
echo [INFO] Utilisez POST /api/esp32/gas depuis l'ESP32 pour alimenter le gaz.
echo [IMPORTANT] Ne pas lancer backend/api_server.py en parallele (meme port 5000).

echo.
echo ============================================================
echo   Backend demarre !
echo ============================================================
echo.
echo   Camera Server : http://localhost:5000
echo   Streams       : /api/stream/lab1, /api/stream/lab2, /api/stream/lab3
echo   Context       : backend/match_context_simulator.py (terminal separe)
echo   API Audio     : /api/audio
echo   API Smoke     : /api/smoke
echo   Orchestrator  : Terminal separe
echo   Audio ESP32   : POST /api/esp32/audio
echo   Gaz ESP32     : POST /api/esp32/gas
echo.
echo   Appuyez sur une touche pour fermer cette fenetre...
echo   (Les serveurs continueront de tourner)
echo ============================================================
pause >nul
