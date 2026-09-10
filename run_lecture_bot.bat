@echo off
setlocal
cd /d "%~dp0"

echo Starting Lecture Bot...
echo Project folder: %CD%

if exist ".venv\Scripts\python.exe" (
    set "PYTHON=.venv\Scripts\python.exe"
) else (
    set "PYTHON=python"
)

start "Lecture Bot Browser" cmd /c "timeout /t 3 /nobreak >nul & start http://127.0.0.1:5000"

%PYTHON% app.py

if errorlevel 1 (
    echo.
    echo Lecture Bot stopped with an error.
    pause
)
endlocal
