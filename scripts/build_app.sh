#!/bin/bash
# 회의록.app 생성 — 이 Mac의 파이썬 환경을 그대로 실행하는 얇은 앱 래퍼.
# 사용법: bash scripts/build_app.sh [설치할 폴더]   (기본: /Applications)
# 프로젝트 폴더나 파이썬을 옮기면 이 스크립트만 다시 실행하면 된다.
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
PYTHON_BIN="$(command -v python3)"
FFMPEG_BIN="$(command -v ffmpeg || true)"
FFMPEG_DIR="${FFMPEG_BIN:+$(dirname "$FFMPEG_BIN")}"

DEST="${1:-/Applications}"
if [ ! -w "$DEST" ]; then
  DEST="$HOME/Applications"
  mkdir -p "$DEST"
  echo "/Applications에 쓰기 권한이 없어 $DEST 에 설치합니다."
fi
APP="$DEST/회의록.app"

rm -rf "$APP"
mkdir -p "$APP/Contents/MacOS" "$APP/Contents/Resources"

cat > "$APP/Contents/Info.plist" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>CFBundleName</key><string>회의록</string>
  <key>CFBundleDisplayName</key><string>회의록</string>
  <key>CFBundleIdentifier</key><string>com.postcoitum.meetinglog</string>
  <key>CFBundleVersion</key><string>1.0</string>
  <key>CFBundleShortVersionString</key><string>1.0</string>
  <key>CFBundlePackageType</key><string>APPL</string>
  <key>CFBundleExecutable</key><string>MeetingLog</string>
  <key>CFBundleIconFile</key><string>icon</string>
  <key>NSHighResolutionCapable</key><true/>
  <key>NSMicrophoneUsageDescription</key><string>회의 녹음을 위해 마이크를 사용합니다.</string>
  <key>LSArchitecturePriority</key><array><string>arm64</string></array>
  <key>LSRequiresNativeExecution</key><true/>
</dict>
</plist>
PLIST

cat > "$APP/Contents/MacOS/MeetingLog" <<LAUNCH
#!/bin/zsh
# 더블클릭 실행은 셸 초기화 파일을 읽지 않으므로 필요한 PATH를 직접 구성한다.
export PATH="${FFMPEG_DIR:-/opt/homebrew/bin}:/usr/local/bin:\$PATH"
cd "$PROJECT_DIR"
# LaunchServices가 스크립트 번들을 Rosetta(x86_64)로 띄우는 경우가 있어
# 아키텍처를 arm64로 명시 고정한다 (numpy 등 네이티브 확장이 arm64 전용).
exec arch -arm64 "$PYTHON_BIN" -m app.main
LAUNCH
chmod +x "$APP/Contents/MacOS/MeetingLog"

# 아이콘 (PIL 없으면 건너뜀 — 앱은 기본 아이콘으로 동작)
if "$PYTHON_BIN" -c "import PIL" 2>/dev/null; then
  "$PYTHON_BIN" "$PROJECT_DIR/scripts/make_icon.py" "$APP/Contents/Resources/icon.icns"
else
  echo "PIL이 없어 아이콘을 건너뜁니다 (pip3 install pillow 후 재실행하면 추가됨)"
fi

# Finder/Dock이 새 번들을 인식하도록 등록
touch "$APP"

echo ""
echo "완성: $APP"
echo "  - Launchpad/Spotlight에서 '회의록'으로 실행"
echo "  - 첫 녹음 시 마이크 권한을 한 번 물어봅니다"
