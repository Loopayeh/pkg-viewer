#!/usr/bin/env bash
# PKG Viewer — per-user uninstall.
set -euo pipefail
rm -rf "${HOME}/.local/share/pkgviewer" "${HOME}/.local/bin/pkgviewer"
rm -f "${HOME}/.local/share/mime/packages/pkgviewer.xml"
rm -f "${HOME}/.local/share/applications/pkgviewer.desktop"
for sz in 16 32 48 64 128 256; do
  rm -f "${HOME}/.local/share/icons/hicolor/${sz}x${sz}/mimetypes/application-x-pkgviewer-"*.png
  rm -f "${HOME}/.local/share/icons/hicolor/${sz}x${sz}/apps/pkgviewer.png"
done
update-mime-database "${HOME}/.local/share/mime" >/dev/null 2>&1 || true
update-desktop-database "${HOME}/.local/share/applications" >/dev/null 2>&1 || true
gtk-update-icon-cache -f -t "${HOME}/.local/share/icons/hicolor" >/dev/null 2>&1 || true
echo "uninstalled."
