# PKG Viewer by Loopayeh — PS4 / PS5

View PS4 (CNT) and PS5 (finalized FIH) package info: cover art, title, Title ID, Content ID, version, and file list — without extracting the whole PKG.

## Features

- Cover art preview (icon0.png, pic0.png, …) with Save PNG / Copy to clipboard
- Spec card: Title ID, Content ID, version, size, SDK / required FW (PS5)
- Files tab: named entries with id + size
- Details tab: curated param.sfo / param.json, Show all for the full dump
- Copy/paste works in every text field, on any keyboard layout (FA/EN)
- CLI mode: `pkgviewer.py --info file.pkg`

## Run

Download `PKGViewer.exe` from [Releases](../../releases) — no Python needed.
Or run from source (needs Python 3 + Pillow):

```bat
PKGViewer.bat
```

Drag & drop a `.pkg` onto the exe/bat, or use Open PKG.

## Build exe

```bat
pip install pyinstaller pillow
python -m PyInstaller --noconfirm --clean --onefile --windowed --name PKGViewer --collect-submodules PIL pkgviewer.py
```
