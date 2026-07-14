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

# 앱만 담은 깨끗한 스테이징 폴더를 만든다 (dist 폴더의 다른 파일 제외).
WORK_DIR="$(mktemp -d)"
trap 'rm -rf "$WORK_DIR"' EXIT
STAGE_DIR="$WORK_DIR/root"
mkdir -p "$STAGE_DIR"
ditto "$SOURCE_APP" "$STAGE_DIR/${APP_BUNDLE_NAME}.app"

# 번들 재배치를 끈다. 이걸 켜두면 macOS Installer가 Launch Services에서
# 같은 CFBundleIdentifier를 가진 기존 앱(예: 개발 폴더의 원본)을 찾아
# /Applications 대신 그쪽에 덮어써서, 응용프로그램에 앱이 안 보이게 된다.
# 플리스트는 --root 밖에 둔다(안에 두면 페이로드에 딸려 들어감).
COMPONENT_PLIST="$WORK_DIR/component.plist"
cat > "$COMPONENT_PLIST" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<array>
  <dict>
    <key>BundleHasStrictIdentifier</key><true/>
    <key>BundleIsRelocatable</key><false/>
    <key>BundleIsVersionChecked</key><true/>
    <key>BundleOverwriteAction</key><string>upgrade</string>
    <key>RootRelativeBundlePath</key><string>${APP_BUNDLE_NAME}.app</string>
  </dict>
</array>
</plist>
PLIST

pkgbuild \
  --root "$STAGE_DIR" \
  --component-plist "$COMPONENT_PLIST" \
  --install-location "/Applications" \
  --identifier "$APP_ID" \
  --scripts "build-installer-scripts" \
  --version "$VERSION" \
  "$PKG_PATH"

echo "설치파일 생성 완료: $PKG_PATH"
