#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Version: an explicit argument wins, otherwise a release-x.y.z git tag, and
# 1.0.0 if there is neither. A tag on HEAD is preferred over an older one so
# that building a checked-out release always packages that release's number.
git_release_version() {
  command -v git >/dev/null 2>&1 || return 1
  git -C "$ROOT_DIR" rev-parse --git-dir >/dev/null 2>&1 || return 1

  local pattern='release-[0-9]*.[0-9]*.[0-9]*' tag
  tag="$(git -C "$ROOT_DIR" tag --points-at HEAD --list "$pattern" \
         | sort -V | tail -n 1)"
  if [ -z "$tag" ]; then
    tag="$(git -C "$ROOT_DIR" describe --tags --abbrev=0 --match "$pattern" 2>/dev/null || true)"
  fi
  [ -n "$tag" ] || return 1

  local version="${tag#release-}"
  case "$version" in
    [0-9]*.[0-9]*.[0-9]*) printf '%s\n' "$version" ;;
    *) return 1 ;;
  esac
}

if [ $# -ge 1 ]; then
  VERSION="$1"
else
  VERSION="$(git_release_version || true)"
  VERSION="${VERSION:-1.0.0}"
fi
DIST_DIR="$ROOT_DIR/dist"
PKG_ROOT="$DIST_DIR/pkgroot"

rm -rf "$PKG_ROOT"
mkdir -p \
  "$PKG_ROOT/DEBIAN" \
  "$PKG_ROOT/usr/bin" \
  "$PKG_ROOT/usr/share/tate-note" \
  "$PKG_ROOT/usr/share/applications" \
  "$PKG_ROOT/usr/share/icons/hicolor/scalable/apps"

install -m 755 "$ROOT_DIR/src/tate-note" "$PKG_ROOT/usr/bin/tate-note"
# The editor is split across modules; the launcher looks for them here.
install -m 644 "$ROOT_DIR/src/"tate*.py "$PKG_ROOT/usr/share/tate-note/"
# The desktop entry and the icon are installed under the application ID, not
# the command name. That is how a Wayland compositor ties a window back to its
# launcher: the window's app_id is the GApplication ID, and the shell looks for
# the .desktop file of that name to find out which icon to show.
APP_ID="net.tate_note.TateNote"
install -m 644 "$ROOT_DIR/src/tate-note.svg" \
  "$PKG_ROOT/usr/share/icons/hicolor/scalable/apps/$APP_ID.svg"
install -m 644 "$ROOT_DIR/packaging/$APP_ID.desktop" \
  "$PKG_ROOT/usr/share/applications/$APP_ID.desktop"

SIZE_KB="$(du -sk "$PKG_ROOT/usr" | cut -f1)"
sed -e "s/__VERSION__/$VERSION/" -e "s/__SIZE__/$SIZE_KB/" \
  "$ROOT_DIR/packaging/control" > "$PKG_ROOT/DEBIAN/control"

DEB_FILE="$DIST_DIR/tate-note_${VERSION}_all.deb"
dpkg-deb --build --root-owner-group "$PKG_ROOT" "$DEB_FILE"

echo "Version: $VERSION"
echo "Built: $DEB_FILE"
echo "Install with: sudo apt install $DEB_FILE"
