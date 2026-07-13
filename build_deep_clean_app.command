#!/bin/zsh
set -euo pipefail

cd "$(dirname "$0")"

APP_DISPLAY_NAME="맥딥클린"
APP_ID="com.huus.macdeepclean.app"
BUILD_DIR="build-deepclean-app"
APP_BUNDLE="$BUILD_DIR/${APP_DISPLAY_NAME}.app"
SOURCE_ICONSET="MacCleaner.iconset"
CLI_PATH="/usr/local/bin/mac-deep-clean"

if [ ! -d "$SOURCE_ICONSET" ]; then
  echo "아이콘 소스 폴더를 찾을 수 없습니다: $SOURCE_ICONSET"
  exit 1
fi

if ! command -v iconutil >/dev/null 2>&1; then
  echo "iconutil을 찾을 수 없습니다."
  exit 1
fi

rm -rf "$APP_BUNDLE"
mkdir -p "$APP_BUNDLE/Contents/MacOS" "$APP_BUNDLE/Contents/Resources"

iconutil -c icns "$SOURCE_ICONSET" -o "$APP_BUNDLE/Contents/Resources/MacCleaner.icns"

cat > "$APP_BUNDLE/Contents/Info.plist" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
	<key>CFBundleDisplayName</key>
	<string>${APP_DISPLAY_NAME}</string>
	<key>CFBundleExecutable</key>
	<string>launcher</string>
	<key>CFBundleIconFile</key>
	<string>MacCleaner.icns</string>
	<key>CFBundleIdentifier</key>
	<string>${APP_ID}</string>
	<key>CFBundleInfoDictionaryVersion</key>
	<string>6.0</string>
	<key>CFBundleName</key>
	<string>${APP_DISPLAY_NAME}</string>
	<key>CFBundlePackageType</key>
	<string>APPL</string>
	<key>CFBundleShortVersionString</key>
	<string>1.0.0</string>
	<key>NSHighResolutionCapable</key>
	<true/>
	<key>CFBundleVersion</key>
	<string>1</string>
</dict>
</plist>
PLIST

cat > "$APP_BUNDLE/Contents/MacOS/launcher" <<LAUNCHER
#!/bin/bash
SCRIPT="${CLI_PATH}"
if [ ! -x "\$SCRIPT" ]; then
  osascript -e 'display alert "맥딥클린" message "설치가 올바르지 않습니다: '"\$SCRIPT"' 를 찾을 수 없습니다." as critical'
  exit 1
fi
osascript -e "tell application \"Terminal\" to activate" -e "tell application \"Terminal\" to do script \"'\$SCRIPT'\""
LAUNCHER
chmod +x "$APP_BUNDLE/Contents/MacOS/launcher"

printf 'APPL????' > "$APP_BUNDLE/Contents/PkgInfo"

echo "앱 생성 완료: $APP_BUNDLE"
