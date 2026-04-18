#!/usr/bin/env bash
set -euo pipefail

if [[ $# -lt 4 ]]; then
  echo "Bruk: $0 <server-url> <bundle-id> <team-id> <support-email> [allowed-host ...]" >&2
  echo "Eksempel: $0 https://api.firma.no no.firma.fiskerikontroll ABC123XYZ9 it@firma.no api.firma.no" >&2
  exit 1
fi

SERVER_URL="$1"
BUNDLE_ID="$2"
TEAM_ID="$3"
SUPPORT_EMAIL="$4"
shift 4

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT_DIR"

ARGS=(
  python3 scripts/configure_ios_internal.py
  --server-url "$SERVER_URL"
  --bundle-id "$BUNDLE_ID"
  --team-id "$TEAM_ID"
  --support-email "$SUPPORT_EMAIL"
  --display-name "Fiskerikontroll"
  --marketing-version "1.4.0"
  --build-number "44"
)

for host in "$@"; do
  ARGS+=(--allowed-host "$host")
done

echo "Kjører konfigurasjon ..."
printf '  %q' "${ARGS[@]}"
printf '\n'
"${ARGS[@]}"
python3 scripts/check_app_store_readiness.py

echo
printf 'Åpne nå prosjektet i Xcode:\n  open "%s/KontrollOgOppsynNative.xcodeproj"\n' "$ROOT_DIR"
