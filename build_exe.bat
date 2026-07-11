@echo off
setlocal
cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
    echo ERROR: Project virtual environment was not found.
    exit /b 1
)

echo Generating application icon...
".venv\Scripts\python.exe" packaging\generate_icon.py || exit /b 1

echo Building ECUMapStudio.exe...
rem Keep PyInstaller's cache: OneDrive can briefly lock clean-up files between builds.
".venv\Scripts\python.exe" -m PyInstaller --noconfirm ECUMapStudio.spec || exit /b 1

echo.
echo Build complete: dist\ECUMapStudio.exe
endlocal
