#!/bin/sh
# Wrap dist/Gunshot.app in a drag-to-Applications disk image.
# Usage: packaging/make_dmg.sh <version> <arch>
set -eu
version="$1"; arch="$2"
staging="$(mktemp -d)"
cp -R dist/Gunshot.app "$staging/"
ln -s /Applications "$staging/Applications"
hdiutil create -volname "Gunshot" -srcfolder "$staging" -ov -format UDZO \
  "dist/Gunshot-$version-macos-$arch.dmg"
rm -rf "$staging"
