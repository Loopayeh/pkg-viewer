#!/usr/bin/env bash
# PKG Viewer — build per-user Linux tarball from repo files.
# The tarball carries install.sh (no sudo, no dpkg) for Arch/Manjaro etc.
# Usage: bash linux/build-tarball.sh [version]   (default: from pkgviewer.py APP_VERSION)
set -euo pipefail
SRC="$(cd "$(dirname "$0")/.." && pwd)"
VER="${1:-$(grep -oP 'APP_VERSION = "v\K[0-9.]+' "$SRC/pkgviewer.py")}"
OUT="$SRC/PKGViewer-linux-$VER.tar.gz"
tar czf "$OUT" -C "$SRC" pkgviewer.py updater.py assets assets_about.png linux README.md LICENSE
echo "built: $OUT"
