#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
PROJECT_PATH="$ROOT_DIR/KontrollOgOppsynNative.xcodeproj"
SCHEME="${SCHEME:-KontrollOgOppsynNative}"
CONFIGURATION="${CONFIGURATION:-Release}"
ARCHIVE_PATH="${ARCHIVE_PATH:-$ROOT_DIR/build/KontrollOgOppsynNative.xcarchive}"
EXPORT_PATH="${EXPORT_PATH:-$ROOT_DIR/build/export}"
EXPORT_OPTIONS_PLIST="${EXPORT_OPTIONS_PLIST:-$ROOT_DIR/export/ExportOptions-AdHoc.plist}"
ALLOW_PROVISIONING_UPDATES="${ALLOW_PROVISIONING_UPDATES:-1}"

mkdir -p "$(dirname "$ARCHIVE_PATH")" "$EXPORT_PATH"

echo "==> Archiving $SCHEME"
ARCHIVE_CMD=(
  xcodebuild
  -project "$PROJECT_PATH"
  -scheme "$SCHEME"
  -configuration "$CONFIGURATION"
  -archivePath "$ARCHIVE_PATH"
  archive
)

if [[ "$ALLOW_PROVISIONING_UPDATES" == "1" ]]; then
  ARCHIVE_CMD+=( -allowProvisioningUpdates )
fi

"${ARCHIVE_CMD[@]}"

echo "==> Exporting archive"
EXPORT_CMD=(
  xcodebuild
  -exportArchive
  -archivePath "$ARCHIVE_PATH"
  -exportPath "$EXPORT_PATH"
  -exportOptionsPlist "$EXPORT_OPTIONS_PLIST"
)

if [[ "$ALLOW_PROVISIONING_UPDATES" == "1" ]]; then
  EXPORT_CMD+=( -allowProvisioningUpdates )
fi

"${EXPORT_CMD[@]}"

echo "\nDone. Output folder: $EXPORT_PATH"
find "$EXPORT_PATH" -maxdepth 2 -type f | sed 's#^#  - #' 
