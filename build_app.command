#!/bin/zsh
set -euo pipefail

cd "$(dirname "$0")"

if [ ! -x ".venv/bin/pyinstaller" ]; then
  echo "PyInstaller를 찾을 수 없습니다. 먼저 .venv를 준비하세요."
  exit 1
fi

SOURCE_ICONSET="MacCleaner.iconset"
BUILD_ICON="MacCleaner.icns"
BUILD_ICON_ABS="$PWD/$BUILD_ICON"
APP_ID="com.huus.maccleaner"
APP_BUNDLE_NAME="HuusCleaner"
APP_DISPLAY_NAME="앱클리너"

if [ ! -d "$SOURCE_ICONSET" ]; then
  echo "아이콘 소스 폴더를 찾을 수 없습니다: $SOURCE_ICONSET"
  exit 1
fi

if ! command -v iconutil >/dev/null 2>&1; then
  echo "iconutil을 찾을 수 없습니다."
  exit 1
fi

iconutil -c icns "$SOURCE_ICONSET" -o "$BUILD_ICON_ABS"

./.venv/bin/pyinstaller \
  --noconfirm \
  --clean \
  --windowed \
  --name "$APP_BUNDLE_NAME" \
  --icon "$BUILD_ICON_ABS" \
  --distpath build-onefile-dist \
  --workpath build-onefile-build \
  --specpath build-onefile-spec \
  mac_cleaner.py

SOURCE_APP="build-onefile-dist/${APP_BUNDLE_NAME}.app"

python3 - <<PY
from pathlib import Path
import plistlib

for bundle_root in (Path("${SOURCE_APP}"),):
    plist_path = bundle_root / "Contents/Info.plist"
    if plist_path.exists():
        data = plistlib.loads(plist_path.read_bytes())
        data["CFBundleIdentifier"] = "${APP_ID}"
        data["CFBundleDisplayName"] = "${APP_DISPLAY_NAME}"
        data["CFBundleName"] = "${APP_DISPLAY_NAME}"
        data["CFBundleShortVersionString"] = "1.0.0"
        data["CFBundleVersion"] = "1"
        plist_path.write_bytes(plistlib.dumps(data, sort_keys=False))

    pkginfo = bundle_root / "Contents/PkgInfo"
    if pkginfo.exists():
        pkginfo.write_bytes(b"APPL????")
PY

rm -f "$BUILD_ICON_ABS"
