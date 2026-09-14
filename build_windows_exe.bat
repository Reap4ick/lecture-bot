@echo off
setlocal
cd /d "%~dp0"

echo Installing/updating PyInstaller...
python -m pip install --upgrade pyinstaller
if errorlevel 1 (
    echo Failed to install PyInstaller.
    pause
    exit /b 1
)

echo Building LectureBot.exe...
if exist build rmdir /s /q build
if exist dist rmdir /s /q dist
python -m PyInstaller --noconfirm --clean --onedir --windowed --name LectureBot --add-data "templates;templates" launcher.py
if errorlevel 1 (
    echo Build failed.
    pause
    exit /b 1
)

copy /Y deepl_keys.txt.example dist\LectureBot\deepl_keys.txt.example >nul

echo.
echo Build complete.
echo EXE folder: %CD%\dist\LectureBot
start "" "%CD%\dist\LectureBot"
pause
endlocal
