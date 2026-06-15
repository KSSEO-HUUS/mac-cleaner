#!/bin/zsh
set -euo pipefail

cd "$(dirname "$0")"

if [ ! -x "./build_app.command" ]; then
  echo "build_app.command를 찾을 수 없습니다."
  exit 1
fi

APP_NAME="앱클리너"
APP_BUNDLE_NAME="HuusCleaner"
SOURCE_APP="build-onefile-dist/${APP_BUNDLE_NAME}.app"
PKG_DIR="build-installer"
PKG_PATH="$PKG_DIR/${APP_NAME}.pkg"
APP_ID="com.huus.maccleaner"
VERSION="1.0.1"

if [ ! -d "$SOURCE_APP" ] || [ ! -f "$SOURCE_APP/Contents/Info.plist" ]; then
  echo "빌드 산출물이 없어서 먼저 앱을 빌드합니다."
  ./build_app.command
fi

if ! command -v pkgbuild >/dev/null 2>&1; then
  echo "pkgbuild를 찾을 수 없습니다."
  exit 1
fi

mkdir -p "$PKG_DIR"
rm -f "$PKG_PATH"

pkgbuild \
  --component "$SOURCE_APP" \
  --install-location "/Applications" \
  --identifier "$APP_ID" \
  --scripts "build-installer-scripts" \
  --version "$VERSION" \
  "$PKG_PATH"

echo "설치파일 생성 완료: $PKG_PATH"
