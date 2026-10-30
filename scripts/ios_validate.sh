#!/bin/bash
# Run on a Mac. This gate requires the target SDK; it never substitutes a static parse for a build.
set -euo pipefail
PROJECT_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$PROJECT_ROOT/frontend"
for tool in xcodebuild xcrun xcodegen python3; do
  command -v "$tool" >/dev/null || { echo "Missing $tool. Run this script on a Mac with Xcode and XcodeGen." >&2; exit 2; }
done
xcodebuild -version
SDK_VERSION="$(xcrun --sdk iphoneos --show-sdk-version)"
python3 - "$SDK_VERSION" <<'PY'
import sys
parts=tuple(int(p) for p in sys.argv[1].split('.')[:2])
if parts < (27,2):
    raise SystemExit('Target acceptance requires iOS SDK 27.2 or later. Select the matching Xcode first.')
PY
xcodegen generate
mkdir -p build
xcodebuild build -scheme LUMI -configuration Release -destination 'generic/platform=iOS' \
  -derivedDataPath build/DerivedData CODE_SIGNING_ALLOWED=NO
if [ -z "${ERII_TEST_DESTINATION:-}" ]; then
  echo 'Release device build completed. Set ERII_TEST_DESTINATION to an installed iPhone simulator (platform=iOS Simulator,id=...) and rerun for XCTest.'
  exit 3
fi
RESULT_PATH="build/Tests-$(date +%Y%m%d-%H%M%S).xcresult"
xcodebuild test -scheme LUMI -destination "$ERII_TEST_DESTINATION" \
  -derivedDataPath build/DerivedData -resultBundlePath "$RESULT_PATH" CODE_SIGNING_ALLOWED=NO
echo 'Build/XCTest completed. Physical-device frame pacing still requires the performance checklist.'
