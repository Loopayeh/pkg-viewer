#!/usr/bin/env bash
# PKG Viewer — per-user Linux install. No sudo.
# Registers icons + double-click open, so no "Open With" each time.
set -euo pipefail
SRC="$(cd "$(dirname "$0")" && pwd)"
ROOT="$(dirname "$SRC")"
PREFIX="${HOME}/.local/share/pkgviewer"
BIN="${HOME}/.local/bin/pkgviewer"

echo "[1/5] copy app -> ${PREFIX}"
mkdir -p "${PREFIX}" "${HOME}/.local/bin"
cp "${ROOT}/pkgviewer.py" "${ROOT}/updater.py" "${ROOT}/assets_about.png" "${PREFIX}/"
cp -r "${ROOT}/assets" "${PREFIX}/"
cat > "${BIN}" <<'EOF'
#!/usr/bin/env bash
exec python3 "$HOME/.local/share/pkgviewer/pkgviewer.py" "$@"
EOF
chmod +x "${BIN}"

echo "[2/5] python deps (pillow, tkinterdnd2, cryptography)"
if ! python3 -c "import tkinter" 2>/dev/null; then
  echo "  ! tkinter missing — Debian/Ubuntu: sudo apt install -y python3-tk"
  echo "  ! Arch/Manjaro: sudo pacman -S --needed tk"
fi
# PEP 668 (Debian 12+/Ubuntu 23.04+/Arch): plain pip --user is blocked,
# retry with --break-system-packages so install never silently skips deps.
# One package per invocation: a single unreachable package must not sink
# the rest (pillow/cover art matters most, tkinterdnd2 is drag-drop only).
# Slow/blocked PyPI mirrors time out on big wheels: generous timeout+retries.
_pip() { PIP_DEFAULT_TIMEOUT=100 PIP_RETRIES=10 pip3 install --user -q "$@" 2>&1 | tail -1 || \
        PIP_DEFAULT_TIMEOUT=100 PIP_RETRIES=10 pip3 install --user -q --break-system-packages "$@" 2>&1 | tail -1; }
# drag-and-drop needs no network: wheel vendored in linux/vendor/ (MIT).
_dnd_whl="$(ls "${SRC}/vendor"/tkinterdnd2-*.whl 2>/dev/null | head -1 || true)"
if [ -n "${_dnd_whl:-}" ]; then
  pip3 install --user -q --no-index "$_dnd_whl" 2>&1 | tail -1 || \
  pip3 install --user -q --no-index --break-system-packages "$_dnd_whl" 2>&1 | tail -1 || \
  echo "  ! failed: tkinterdnd2 (drag-and-drop disabled, app still runs)"
fi
for _p in pillow cryptography mkpfs pytsk3; do
  _pip "$_p" || echo "  ! failed: $_p (app still runs without it)"
done

echo "[3/5] mime types"
mkdir -p "${HOME}/.local/share/mime/packages"
cp "${SRC}/pkgviewer-mime.xml" "${HOME}/.local/share/mime/packages/pkgviewer.xml"
update-mime-database "${HOME}/.local/share/mime" >/dev/null 2>&1 || true

echo "[4/5] icons + desktop entry"
for sz in 16 32 48 64 128 256; do
  dst="${HOME}/.local/share/icons/hicolor/${sz}x${sz}"
  mkdir -p "${dst}/mimetypes" "${dst}/apps"
  for f in pkg exfat ffpfsc ffpkg; do
    cp "${SRC}/icons/hicolor/${sz}x${sz}/mimetypes/application-x-pkgviewer-${f}.png" \
       "${dst}/mimetypes/" 2>/dev/null || true
  done
  cp "${SRC}/icons/hicolor/${sz}x${sz}/apps/pkgviewer.png" "${dst}/apps/" 2>/dev/null || true
done
mkdir -p "${HOME}/.local/share/applications"
sed "s|^Exec=.*|Exec=${BIN//\//\\/} %F|" "${SRC}/pkgviewer.desktop" \
  > "${HOME}/.local/share/applications/pkgviewer.desktop"
update-desktop-database "${HOME}/.local/share/applications" >/dev/null 2>&1 || true
gtk-update-icon-cache -f -t "${HOME}/.local/share/icons/hicolor" >/dev/null 2>&1 || true

echo "[5/5] set as default handler"
for m in application/x-pkgviewer-pkg application/x-pkgviewer-exfat \
         application/x-pkgviewer-ffpfsc application/x-pkgviewer-ffpkg; do
  xdg-mime default pkgviewer.desktop "$m" 2>/dev/null || true
done
# KDE (Dolphin) uses its own cache, not gtk's
if command -v kbuildsycoca6 >/dev/null 2>&1; then
  kbuildsycoca6 >/dev/null 2>&1 || true
elif command -v kbuildsycoca5 >/dev/null 2>&1; then
  kbuildsycoca5 >/dev/null 2>&1 || true
fi

echo "[verify] icon/mime tools"
for t in update-mime-database update-desktop-database gtk-update-icon-cache; do
  if ! command -v "$t" >/dev/null 2>&1; then
    echo "  ! $t missing — icons may not show."
    echo "    Debian/Ubuntu: sudo apt install -y shared-mime-info desktop-file-utils gtk3"
    echo "    Arch/Manjaro: sudo pacman -S --needed shared-mime-info desktop-file-utils gtk3"
  fi
done

echo "done — double-click a .pkg/.exfat/.ffpfsc/.ffpkg to open. icons may need a file-manager refresh."
