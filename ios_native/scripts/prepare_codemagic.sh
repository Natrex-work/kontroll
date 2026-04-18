#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

trim() {
  local value="$1"
  value="${value#${value%%[![:space:]]*}}"
  value="${value%${value##*[![:space:]]}}"
  printf '%s' "$value"
}

require_var() {
  local name="$1"
  if [[ -z "${!name:-}" ]]; then
    echo "[ERROR] Required environment variable is missing: $name" >&2
    exit 1
  fi
}

require_var SERVER_URL
require_var BUNDLE_ID

DISPLAY_NAME="${DISPLAY_NAME:-Fiskerikontroll}"
SUPPORT_EMAIL="${SUPPORT_EMAIL:-it@example.no}"
RELOCK_SECONDS="${RELOCK_SECONDS:-30}"
APPLE_TEAM_ID="${APPLE_TEAM_ID:-}"
MARKETING_VERSION="${MARKETING_VERSION:-1.2.0}"
BUILD_NUMBER_OVERRIDE="${BUILD_NUMBER_OVERRIDE:-}"
ALLOWED_HOSTS="${ALLOWED_HOSTS:-}"
PINNED_CERT_SHA256="${PINNED_CERT_SHA256:-}"

args=(
  python3 scripts/configure_ios_internal.py
  --server-url "$SERVER_URL"
  --bundle-id "$BUNDLE_ID"
  --support-email "$SUPPORT_EMAIL"
  --display-name "$DISPLAY_NAME"
  --relock-seconds "$RELOCK_SECONDS"
  --marketing-version "$MARKETING_VERSION"
)

if [[ -n "$APPLE_TEAM_ID" ]]; then
  args+=(--team-id "$APPLE_TEAM_ID")
fi

if [[ -n "$BUILD_NUMBER_OVERRIDE" ]]; then
  args+=(--build-number "$BUILD_NUMBER_OVERRIDE")
fi

if [[ -n "$ALLOWED_HOSTS" ]]; then
  IFS=',' read -r -a hosts <<< "$ALLOWED_HOSTS"
  for raw_host in "${hosts[@]}"; do
    host="$(trim "$raw_host")"
    if [[ -n "$host" ]]; then
      args+=(--allowed-host "$host")
    fi
  done
fi

if [[ -n "$PINNED_CERT_SHA256" ]]; then
  IFS=',' read -r -a pins <<< "$PINNED_CERT_SHA256"
  for raw_pin in "${pins[@]}"; do
    pin="$(trim "$raw_pin")"
    if [[ -n "$pin" ]]; then
      args+=(--pin "$pin")
    fi
  done
fi

echo "[INFO] Running iOS wrapper configuration"
printf '  %q' "${args[@]}"
printf '\n'
"${args[@]}"
