# PKG Viewer — PS4 / PS5

View PS4 (CNT) and PS5 (finalized FIH) package info: cover art, title, Title ID, Content ID, version, and file list — without extracting the whole PKG.

## Download

Get `PKGViewer.exe` from [Releases](../../releases) — no Python needed, just run it.

## Features

- Cover art preview (icon0.png, pic0.png, …) with Save PNG / Copy to clipboard
- Spec card: Title ID, Content ID, version, size, SDK / required firmware (PS5)
- Files tab: named entries with id + size
- Details tab: curated param.sfo / param.json, Show all for the full dump
- Copy/paste works in every text field, on any keyboard layout
- CLI mode: `pkgviewer.py --info file.pkg`

## Usage

Drag & drop a `.pkg` file onto the exe, or open it from inside the app. To run from source (needs Python 3 + Pillow):

```bat
PKGViewer.bat
```

## Supported formats

- **PS4** packages (`7F CNT`): reads the entry table and `param.sfo`
- **PS5** finalized packages (FIH): reads the file table, `param.json`, and the icon

## Build from source

```bat
pip install pyinstaller pillow
python -m PyInstaller --noconfirm --clean --onefile --windowed --name PKGViewer --collect-submodules PIL pkgviewer.py
```

## License

MIT — see [LICENSE](LICENSE).

## Contact

Telegram: [@loopayeh](https://t.me/loopayeh)
