#!/usr/bin/env bash
set -euo pipefail

VERSION="${1:-1.0.0}"
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DIST_DIR="$ROOT_DIR/dist"
PKG_ROOT="$DIST_DIR/pkgroot"

rm -rf "$PKG_ROOT"
mkdir -p \
  "$PKG_ROOT/DEBIAN" \
  "$PKG_ROOT/usr/bin" \
  "$PKG_ROOT/usr/share/tate-note/assets" \
  "$PKG_ROOT/usr/share/applications" \
  "$PKG_ROOT/usr/share/icons/hicolor/scalable/apps"

install -m 755 "$ROOT_DIR/src/tate-note" "$PKG_ROOT/usr/bin/tate-note"
install -m 644 "$ROOT_DIR/src/assets/"* "$PKG_ROOT/usr/share/tate-note/assets/"
install -m 644 "$ROOT_DIR/src/tate-note.svg" "$PKG_ROOT/usr/share/icons/hicolor/scalable/apps/tate-note.svg"
install -m 644 "$ROOT_DIR/packaging/tate-note.desktop" "$PKG_ROOT/usr/share/applications/tate-note.desktop"

SIZE_KB="$(du -sk "$PKG_ROOT/usr" | cut -f1)"
sed -e "s/__VERSION__/$VERSION/" -e "s/__SIZE__/$SIZE_KB/" \
  "$ROOT_DIR/packaging/control" > "$PKG_ROOT/DEBIAN/control"

DEB_FILE="$DIST_DIR/tate-note_${VERSION}_all.deb"
dpkg-deb --build --root-owner-group "$PKG_ROOT" "$DEB_FILE"

echo "Built: $DEB_FILE"
echo "Install with: sudo apt install $DEB_FILE"
