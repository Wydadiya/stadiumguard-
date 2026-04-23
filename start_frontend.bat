@echo off
echo ============================================================
echo   StadiumGuard Frontend Launcher
echo ============================================================
echo.

REM Vérifier si Node.js est installé
node --version >nul 2>&1
if errorlevel 1 (
    echo [ERREUR] Node.js n'est pas installe ou pas dans le PATH
    pause
    exit /b 1
)

cd frontend

REM Vérifier si node_modules existe
if not exist "node_modules" (
    echo [INFO] Installation des dependances npm...
    call npm install
    echo.
)

echo [INFO] Demarrage du serveur Vite...
echo.
echo ============================================================
echo   Frontend disponible sur : http://localhost:3101
echo ============================================================
echo.

call npm run dev

pause
