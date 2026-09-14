# PKG Viewer — PS4 / PS5

![screenshot](screenshot.png)

**PKG Viewer** shows what's inside a PS4 / PS5 game file without extracting it: cover art, title, Title ID, region, version, and required firmware.

Works with `.pkg` packages, `.exfat` / `.ffpfsc` / `.ffpkg` images, and app folders.

## Download

Get `PKGViewer.exe` from [Releases](../../releases) — no Python needed, just run it.

## Features

- Cover art preview (icon0.png, pic0.png, …) with Save PNG / Copy to clipboard
- Spec card: Title ID, Content ID, version, region, Min. System, SDK, DRM
- Files tab: named entries with id + size
- Details tab: curated param.sfo / param.json, Show all for the full dump
- Drag & drop: PKG files, exFAT / ffpfsc / ffpkg images, and app folders onto the window
- AMPR / LZ4 asset containers (LIZARD dumps): listed with size in the spec card + Files tab
- Copy/paste works in every text field, on any keyboard layout
- CLI mode: `pkgviewer.py --info file.pkg`

## Usage

Drag & drop a `.pkg` / `.exfat` / `.ffpfsc` / `.ffpkg` file or an app folder onto the exe or the open window, or use Open. To run from source (needs Python 3 + Pillow + tkinterdnd2 + mkpfs + pytsk3):

```bat
PKGViewer.bat
```

## Supported formats

- **PS4 / PS5 packages** (`.pkg`) — game, DLC, update
- **PS5 disk images** (`.exfat`) — game dumps
- **PS5 compressed images** (`.ffpfsc`) — game dumps
- **PS5 UFS2 images** (`.ffpkg`) — game dumps (needs pytsk3 from source)
- **PS5 app folders** — extracted game folder (incl. LIZARD AMPR/LZ4 dumps)

## Build from source

```bat
pip install pyinstaller pillow
python -m PyInstaller --noconfirm --clean --onefile --windowed --name PKGViewer --collect-submodules PIL pkgviewer.py
```

## License

MIT — see [LICENSE](LICENSE).

## Contact

Telegram: [@loopayeh](https://t.me/loopayeh)
