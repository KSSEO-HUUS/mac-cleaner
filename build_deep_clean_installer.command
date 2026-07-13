#!/bin/zsh
set -euo pipefail

cd "$(dirname "$0")"

SCRIPT_NAME="deep_clean.sh"
INSTALL_NAME="mac-deep-clean"
APP_DISPLAY_NAME="맥딥클린"
APP_BUNDLE_DIR="build-deepclean-app"
APP_ID="com.huus.macdeepclean"
VERSION="1.0.0"
PKG_DIR="build-installer"
PKG_PATH="$PKG_DIR/맥딥클린.pkg"
ROOT_DIR="build-deepclean-root"

if [ ! -f "$SCRIPT_NAME" ]; then
  echo "$SCRIPT_NAME 를 찾을 수 없습니다."
  exit 1
fi

if ! command -v pkgbuild >/dev/null 2>&1; then
  echo "pkgbuild를 찾을 수 없습니다."
  exit 1
fi

if [ ! -x "./build_deep_clean_app.command" ]; then
  echo "build_deep_clean_app.command를 찾을 수 없습니다."
  exit 1
fi

./build_deep_clean_app.command

APP_BUNDLE="$APP_BUNDLE_DIR/${APP_DISPLAY_NAME}.app"
if [ ! -d "$APP_BUNDLE" ]; then
  echo "앱 빌드 결과를 찾을 수 없습니다: $APP_BUNDLE"
  exit 1
fi

rm -rf "$ROOT_DIR"
mkdir -p "$ROOT_DIR/usr/local/bin"
cp "$SCRIPT_NAME" "$ROOT_DIR/usr/local/bin/$INSTALL_NAME"
chmod 755 "$ROOT_DIR/usr/local/bin/$INSTALL_NAME"

mkdir -p "$PKG_DIR"
rm -f "$PKG_PATH"

CLI_PKG="$PKG_DIR/cli-component.pkg"
APP_PKG="$PKG_DIR/app-component.pkg"
rm -f "$CLI_PKG" "$APP_PKG"

pkgbuild \
  --root "$ROOT_DIR" \
  --install-location "/" \
  --identifier "${APP_ID}.cli" \
  --version "$VERSION" \
  "$CLI_PKG"

pkgbuild \
  --component "$APP_BUNDLE" \
  --install-location "/Applications" \
  --identifier "${APP_ID}.app" \
  --version "$VERSION" \
  "$APP_PKG"

productbuild \
  --package "$CLI_PKG" \
  --package "$APP_PKG" \
  "$PKG_PATH"

rm -rf "$ROOT_DIR" "$APP_BUNDLE_DIR" "$CLI_PKG" "$APP_PKG"

echo "설치파일 생성 완료: $PKG_PATH"
echo "설치 후 응용 프로그램 폴더의 '${APP_DISPLAY_NAME}' 아이콘을 더블클릭하거나,"
echo "터미널에서 'mac-deep-clean' 명령으로 실행할 수 있습니다."
