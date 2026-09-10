@echo off
setlocal
cd /d "%~dp0"

echo Starting Lecture Bot...
echo Project folder: %CD%

where python >nul 2>nul
if errorlevel 1 (
    echo Python was not found in PATH.
    echo Install Python or add it to PATH, then try again.
    pause
    exit /b 1
)

start "Lecture Bot Browser" cmd /c "timeout /t 3 /nobreak >nul & start http://127.0.0.1:5000"

python app.py

if errorlevel 1 (
    echo.
    echo Lecture Bot stopped with an error.
    pause
)
endlocal
