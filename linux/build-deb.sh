#!/usr/bin/env bash
# PKG Viewer — build system .deb from repo files. No sudo (dpkg-deb only).
# Usage: bash linux/build-deb.sh [version]   (default: from pkgviewer.py APP_VERSION)
set -euo pipefail
SRC="$(cd "$(dirname "$0")/.." && pwd)"
VER="${1:-$(grep -oP 'APP_VERSION = "v\K[0-9.]+' "$SRC/pkgviewer.py")}"
STAGE="$(mktemp -d)"
trap 'rm -rf "$STAGE"' EXIT
PKG="$STAGE/pkgviewer"

mkdir -p "$PKG/DEBIAN" "$PKG/usr/bin" "$PKG/usr/share/pkgviewer" \
         "$PKG/usr/share/applications" "$PKG/usr/share/mime/packages"
cp "$SRC/pkgviewer.py" "$SRC/updater.py" "$SRC/assets_about.png" "$PKG/usr/share/pkgviewer/"
cp -r "$SRC/assets" "$PKG/usr/share/pkgviewer/"
cp -r "$SRC/linux/icons" "$PKG/usr/share/icons" 2>/dev/null || \
  cp -r "$SRC/linux/icons/hicolor" "$PKG/usr/share/icons/hicolor"
sed 's|^Exec=.*|Exec=/usr/bin/pkgviewer %F|' "$SRC/linux/pkgviewer.desktop" \
  > "$PKG/usr/share/applications/pkgviewer.desktop"
cp "$SRC/linux/pkgviewer-mime.xml" "$PKG/usr/share/mime/packages/pkgviewer.xml"
cat > "$PKG/usr/bin/pkgviewer" <<'EOF'
#!/bin/sh
exec python3 /usr/share/pkgviewer/pkgviewer.py "$@"
EOF
chmod +x "$PKG/usr/bin/pkgviewer"
cat > "$PKG/DEBIAN/control" <<EOF
Package: pkgviewer
Version: $VER
Section: utils
Priority: optional
Architecture: all
Maintainer: Loopayeh
Depends: python3, python3-tk, python3-pil, xdg-utils, shared-mime-info, hicolor-icon-theme
Recommends: python3-cryptography
Description: View PS3/PS4/PS5 package contents
 Shows cover art, Title ID, region, version and firmware
 for .pkg / .exfat / .ffpfsc / .ffpkg with per-format icons.
EOF
cat > "$PKG/DEBIAN/postinst" <<'EOF'
#!/bin/sh
set -e
update-mime-database /usr/share/mime >/dev/null 2>&1 || true
update-desktop-database /usr/share/applications >/dev/null 2>&1 || true
gtk-update-icon-cache -f -t /usr/share/icons/hicolor >/dev/null 2>&1 || true
(pip3 install --quiet tkinterdnd2 2>/dev/null || pip3 install --quiet --break-system-packages tkinterdnd2 2>/dev/null) || true
exit 0
EOF
cat > "$PKG/DEBIAN/postrm" <<'EOF'
#!/bin/sh
set -e
update-mime-database /usr/share/mime >/dev/null 2>&1 || true
update-desktop-database /usr/share/applications >/dev/null 2>&1 || true
gtk-update-icon-cache -f -t /usr/share/icons/hicolor >/dev/null 2>&1 || true
exit 0
EOF
chmod 755 "$PKG/DEBIAN/postinst" "$PKG/DEBIAN/postrm"
dpkg-deb --build "$PKG" "$SRC/PKGViewer-$VER.deb"
echo "built: $SRC/PKGViewer-$VER.deb"
