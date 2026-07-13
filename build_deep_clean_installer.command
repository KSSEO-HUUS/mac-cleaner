#!/bin/zsh
set -euo pipefail

cd "$(dirname "$0")"

SCRIPT_NAME="deep_clean.sh"
INSTALL_NAME="mac-deep-clean"
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

rm -rf "$ROOT_DIR"
mkdir -p "$ROOT_DIR/usr/local/bin"
cp "$SCRIPT_NAME" "$ROOT_DIR/usr/local/bin/$INSTALL_NAME"
chmod 755 "$ROOT_DIR/usr/local/bin/$INSTALL_NAME"

mkdir -p "$PKG_DIR"
rm -f "$PKG_PATH"

pkgbuild \
  --root "$ROOT_DIR" \
  --install-location "/" \
  --identifier "$APP_ID" \
  --version "$VERSION" \
  "$PKG_PATH"

rm -rf "$ROOT_DIR"

echo "설치파일 생성 완료: $PKG_PATH"
echo "설치 후 터미널에서 'mac-deep-clean' 명령으로 실행할 수 있습니다."
