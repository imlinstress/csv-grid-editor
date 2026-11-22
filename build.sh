#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
NAME="csv-grid-editor"
VERSION="1.4.1"
DIST="$ROOT/dist"
BUILD="$DIST/build-root"
PACKAGE="$DIST/${NAME}_${VERSION}_all.deb"

python3 - "$ROOT/src" <<'PY'
import ast
import pathlib
import sys
for source in pathlib.Path(sys.argv[1]).rglob("*.py"):
    ast.parse(source.read_text(encoding="utf-8"), filename=str(source))
PY

rm -rf "$BUILD"
mkdir -p "$BUILD/DEBIAN" \
         "$BUILD/usr/bin" \
         "$BUILD/usr/lib/$NAME" \
         "$BUILD/usr/share/applications" \
         "$BUILD/usr/share/icons/hicolor/scalable/apps"

sed "s/@VERSION@/$VERSION/g" "$ROOT/packaging/control.in" > "$BUILD/DEBIAN/control"

cp -R "$ROOT/src/csv_grid_editor" "$BUILD/usr/lib/$NAME/"
find "$BUILD/usr/lib/$NAME" -type d -name __pycache__ -prune -exec rm -rf {} +

cat > "$BUILD/usr/bin/$NAME" <<EOF
#!/usr/bin/python3
import sys
sys.path.insert(0, "/usr/lib/$NAME")
from csv_grid_editor.app import main
raise SystemExit(main())
EOF
chmod 0755 "$BUILD/usr/bin/$NAME"

cat > "$BUILD/usr/share/applications/$NAME.desktop" <<EOF
[Desktop Entry]
Type=Application
Name=CSV Grid Editor
Comment=Edit CSV files with aligned, adjustable columns and line numbers
Exec=$NAME %f
Icon=$NAME
MimeType=text/csv;
Terminal=false
Categories=Office;
EOF

cp "$ROOT/packaging/$NAME.svg" "$BUILD/usr/share/icons/hicolor/scalable/apps/$NAME.svg"

find "$BUILD/usr" -type d -exec chmod 0755 {} +
find "$BUILD/usr/lib" -type f -exec chmod 0644 {} +
find "$BUILD/usr/share" -type f -exec chmod 0644 {} +

dpkg-deb --build --root-owner-group "$BUILD" "$PACKAGE"
dpkg-deb --info "$PACKAGE"
dpkg-deb --contents "$PACKAGE"
