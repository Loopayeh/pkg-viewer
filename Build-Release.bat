@echo off
rem PKG Viewer release builder - run from this folder.
rem Build env needs: pip install pyinstaller pillow cryptography mkpfs tkinterdnd2
rem Bundles assets (window icon) + sets the exe icon. Without these
rem the window falls back to the Tk feather and a white titlebar.
cd /d "%~dp0"
python -m PyInstaller --noconfirm --clean --onefile --windowed --name PKGViewer --icon assets\logo.ico --add-data "assets;assets" --add-data "assets_about.png;." --add-data "orbis_full.py;." --collect-submodules PIL --collect-all tkinterdnd2 pkgviewer.py
echo.
echo Built: dist\PKGViewer.exe
pause
