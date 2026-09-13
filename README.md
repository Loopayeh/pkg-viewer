# PKG Viewer — PS4 / PS5

![screenshot](screenshot.png)

View PS4 (CNT) and PS5 (finalized FIH) package info, plus PS5 exFAT / ffpfsc images and app folders: cover art, title, Title ID, Content ID, version, region, and required firmware — without extracting anything.

## Download

Get `PKGViewer.exe` from [Releases](../../releases) — no Python needed, just run it.

## Features

- Cover art preview (icon0.png, pic0.png, …) with Save PNG / Copy to clipboard
- Spec card: Title ID, Content ID, version, region, Min. System, SDK, DRM
- Files tab: named entries with id + size
- Details tab: curated param.sfo / param.json, Show all for the full dump
- Drag & drop: PKG files, exFAT / ffpfsc images, and app folders onto the window
- Copy/paste works in every text field, on any keyboard layout
- CLI mode: `pkgviewer.py --info file.pkg`

## Usage

Drag & drop a `.pkg` / `.exfat` / `.ffpfsc` file or an app folder onto the exe or the open window, or use Open. To run from source (needs Python 3 + Pillow + tkinterdnd2 + mkpfs):

```bat
PKGViewer.bat
```

## Supported formats

- **PS4** packages (`7F CNT`): reads the entry table and `param.sfo`
- **PS5** finalized packages (FIH): reads the file table, `param.json`, and the icon
- **PS5 exFAT images** (`.exfat`): reads `sce_sys/param.json` + icon straight from the image via FAT walk
- **PS5 compressed images** (`.ffpfsc`): opens the inner exFAT via mkpfs, then reads `sce_sys` the same way (needs `pip install mkpfs` when running from source)
- **PS5 app folders**: reads `sce_sys/param.json` + icon directly — no container needed

## Build from source

```bat
pip install pyinstaller pillow
python -m PyInstaller --noconfirm --clean --onefile --windowed --name PKGViewer --collect-submodules PIL pkgviewer.py
```

## License

MIT — see [LICENSE](LICENSE).

## Contact

Telegram: [@loopayeh](https://t.me/loopayeh)
