@echo off
echo.
echo ╔══════════════════════════════════════════════════════════════╗
echo ║                                                              ║
echo ║         StadiumGuard - Verification Rapide                   ║
echo ║                                                              ║
echo ╚══════════════════════════════════════════════════════════════╝
echo.

REM Vérifier Python
echo [1/5] Verification de Python...
python --version >nul 2>&1
if errorlevel 1 (
    echo ❌ Python n'est pas installe
    goto :error
) else (
    python --version
    echo ✅ Python OK
)
echo.

REM Vérifier Node.js
echo [2/5] Verification de Node.js...
node --version >nul 2>&1
if errorlevel 1 (
    echo ❌ Node.js n'est pas installe
    goto :error
) else (
    node --version
    echo ✅ Node.js OK
)
echo.

REM Vérifier dossier output
echo [3/5] Verification du dossier output...
if not exist "output" (
    echo ⏳ Creation du dossier output...
    mkdir output
)
echo ✅ Dossier output OK
echo.

REM Vérifier les dépendances Python
echo [4/5] Verification des dependances Python...
python -c "import flask, flask_cors, cv2, ultralytics, numpy" >nul 2>&1
if errorlevel 1 (
    echo ⚠️  Certaines dependances Python manquent
    echo    Executez: pip install -r backend/requirements.txt
) else (
    echo ✅ Dependances Python OK
)
echo.

REM Vérifier node_modules
echo [5/5] Verification du frontend...
if not exist "frontend\node_modules" (
    echo ⚠️  node_modules manquant
    echo    Executez: cd frontend ^&^& npm install
) else (
    echo ✅ Frontend OK
)
echo.

echo ╔══════════════════════════════════════════════════════════════╗
echo ║                                                              ║
echo ║                    VERIFICATION TERMINEE                     ║
echo ║                                                              ║
echo ╚══════════════════════════════════════════════════════════════╝
echo.
echo Prochaines etapes:
echo   1. Double-clic sur start_backend.bat
echo   2. Double-clic sur start_frontend.bat
echo   3. Ouvrir http://localhost:3101
echo.
echo Pour plus d'infos: DEMARRAGE_RAPIDE.md
echo.
pause
exit /b 0

:error
echo.
echo ╔══════════════════════════════════════════════════════════════╗
echo ║                                                              ║
echo ║                    ERREUR DETECTEE                           ║
echo ║                                                              ║
echo ╚══════════════════════════════════════════════════════════════╝
echo.
echo Consultez INTEGRATION_GUIDE.md pour l'installation.
echo.
pause
exit /b 1
