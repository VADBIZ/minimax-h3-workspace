#!/bin/sh
# Packs the built .app into a disk image with an Applications shortcut: open, drag, done.
# Usage: sh app/build/make-dmg.sh   (after the PyInstaller build)
set -e
cd "$(dirname "$0")"
APP="dist/Minimax H3 Workspace.app"
OUT="output/Minimax.H3.Workspace-mac-$(uname -m).dmg"
STAGE=$(mktemp -d)
cp -R "$APP" "$STAGE/"
ln -s /Applications "$STAGE/Applications"
cp "Как открыть.txt" "$STAGE/"
mkdir -p output
rm -f "$OUT"
hdiutil create -volname "Minimax H3 Workspace" -srcfolder "$STAGE" -fs HFS+ -format UDZO -ov "$OUT" >/dev/null
rm -rf "$STAGE"
echo "$OUT"
