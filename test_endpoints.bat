@echo off
echo ============================================================
echo   Test des Endpoints API StadiumGuard
echo ============================================================
echo.

set API_URL=http://localhost:5000

echo [1/6] Test de sante du serveur...
curl -s %API_URL%/api/health | python -m json.tool
echo.
echo.

echo [2/6] Test du score d'alerte fusionne...
curl -s %API_URL%/api/alert | python -m json.tool
echo.
echo.

echo [3/6] Test de detection de personnes...
curl -s %API_URL%/api/person | python -m json.tool
echo.
echo.

echo [4/6] Test de detection de chutes...
curl -s %API_URL%/api/fall | python -m json.tool
echo.
echo.

echo [5/6] Test de classification de mouvement...
curl -s %API_URL%/api/motion | python -m json.tool
echo.
echo.

echo [6/6] Test du contexte du match...
curl -s %API_URL%/api/context | python -m json.tool
echo.
echo.

echo ============================================================
echo   Tests termines !
echo ============================================================
pause
