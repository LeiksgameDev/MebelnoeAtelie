@echo off
chcp 65001 >nul
cd /d "%~dp0"

echo Installing dependencies...
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
python -m pip install pyinstaller

echo Building DEBUG EXE...
python -m PyInstaller --noconfirm --clean --onefile --collect-all customtkinter --collect-all PIL --add-data "assets;assets" --add-data "data;data" --name "MebelnoeAtelie_debug" app.py

echo Done. EXE file: dist\MebelnoeAtelie_debug.exe
pause
