#!/usr/bin/env python3
"""Configure the native iOS wrapper for internal distribution.

Updates:
- AppConfig.plist
- AppConfig.example.plist
- project.yml
- Xcode project.pbxproj
- export option plists
"""

from __future__ import annotations

import argparse
import plistlib
import re
import sys
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[1]
APP_DIR = ROOT / "KontrollOgOppsynNative"
PROJECT_YML = ROOT / "project.yml"
PBXPROJ = ROOT / "KontrollOgOppsynNative.xcodeproj" / "project.pbxproj"
EXPORT_DIR = ROOT / "export"
PLISTS = [APP_DIR / "AppConfig.plist", APP_DIR / "AppConfig.example.plist"]
EXPORT_PLISTS = [
    EXPORT_DIR / "ExportOptions-AdHoc.plist",
    EXPORT_DIR / "ExportOptions-Enterprise.plist",
    EXPORT_DIR / "ExportOptions-AppStoreConnect.plist",
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Configure the iOS native wrapper for internal distribution.")
    parser.add_argument("--server-url", required=True, help="HTTPS URL to the secure backend, for example https://kontroll.example.no")
    parser.add_argument("--bundle-id", required=True, help="Bundle identifier, for example no.company.kontrollogoppsyn")
    parser.add_argument("--allowed-host", action="append", default=[], help="Additional allowed host. Repeat the flag for multiple hosts.")
    parser.add_argument("--team-id", default=None, help="Apple Developer Team ID")
    parser.add_argument("--support-email", default="it@example.no", help="Support e-mail visible in the app")
    parser.add_argument("--display-name", default="Fiskerikontroll", help="Displayed app name")
    parser.add_argument("--relock-seconds", type=int, default=30, help="Seconds before biometric relock")
    parser.add_argument("--build-number", default="44", help="Build number / CURRENT_PROJECT_VERSION")
    parser.add_argument("--marketing-version", default="1.4.0", help="MARKETING_VERSION")
    parser.add_argument("--pin", action="append", default=[], help="Optional pinned certificate SHA-256 value in hex or base64. Repeat the flag for multiple pins.")
    parser.add_argument("--print-only", action="store_true", help="Print the planned values without writing files")
    return parser.parse_args()


def ensure_https(url: str) -> str:
    parsed = urlparse(url)
    if parsed.scheme.lower() != "https":
        raise SystemExit("Server URL must use https.")
    if not parsed.netloc:
        raise SystemExit("Server URL must include a hostname.")
    return url


def normalized_hosts(server_url: str, extra_hosts: list[str]) -> list[str]:
    parsed = urlparse(server_url)
    hosts = [parsed.hostname.lower()] if parsed.hostname else []
    for host in extra_hosts:
        clean = host.strip().lower()
        if clean and clean not in hosts:
            hosts.append(clean)
    return hosts


def normalize_pins(values: list[str]) -> list[str]:
    pins: list[str] = []
    for value in values:
        clean = value.strip()
        if clean and clean.lower() not in {item.lower() for item in pins}:
            pins.append(clean)
    return pins


def update_plists(*, server_url: str, hosts: list[str], display_name: str, support_email: str, relock_seconds: int, pins: list[str]) -> None:
    for path in PLISTS:
        with path.open("rb") as f:
            data = plistlib.load(f)
        data["ServerURL"] = server_url
        data["AllowedHosts"] = hosts
        data["DisplayName"] = display_name
        data["SupportEmail"] = support_email
        data["BiometricRelockEnabled"] = True
        data["RelockAfterSeconds"] = max(0, relock_seconds)
        data["PinnedCertificateSHA256"] = pins
        with path.open("wb") as f:
            plistlib.dump(data, f, sort_keys=False)


def replace_regex(text: str, pattern: str, replacement: str) -> str:
    updated, count = re.subn(pattern, replacement, text, flags=re.MULTILINE)
    if count == 0:
        raise RuntimeError(f"Pattern not found: {pattern}")
    return updated


def update_project_files(*, bundle_id: str, team_id: str | None, build_number: str, marketing_version: str) -> None:
    yml = PROJECT_YML.read_text(encoding="utf-8")
    yml = replace_regex(yml, r"(^\s*CURRENT_PROJECT_VERSION:\s*)'[^']*'", rf"\g<1>'{build_number}'")
    yml = replace_regex(yml, r"(^\s*MARKETING_VERSION:\s*)[^\n]+", rf"\g<1>{marketing_version}")
    yml = replace_regex(yml, r"(^\s*PRODUCT_BUNDLE_IDENTIFIER:\s*)[^\n]+", rf"\g<1>{bundle_id}")
    PROJECT_YML.write_text(yml, encoding="utf-8")

    pbxproj = PBXPROJ.read_text(encoding="utf-8")
    pbxproj = replace_regex(pbxproj, r"CURRENT_PROJECT_VERSION = [^;]+;", f"CURRENT_PROJECT_VERSION = {build_number};")
    pbxproj = replace_regex(pbxproj, r"MARKETING_VERSION = [^;]+;", f"MARKETING_VERSION = {marketing_version};")
    pbxproj = replace_regex(pbxproj, r"PRODUCT_BUNDLE_IDENTIFIER = [^;]+;", f"PRODUCT_BUNDLE_IDENTIFIER = {bundle_id};")
    if team_id is not None:
        pbxproj = replace_regex(pbxproj, r'DEVELOPMENT_TEAM = "[^"]*";', f'DEVELOPMENT_TEAM = "{team_id}";')
    PBXPROJ.write_text(pbxproj, encoding="utf-8")


def update_export_plists(team_id: str | None) -> None:
    if team_id is None:
        return
    for path in EXPORT_PLISTS:
        with path.open("rb") as f:
            data = plistlib.load(f)
        data["teamID"] = team_id
        with path.open("wb") as f:
            plistlib.dump(data, f, sort_keys=False)


def main() -> int:
    args = parse_args()
    server_url = ensure_https(args.server_url)
    hosts = normalized_hosts(server_url, args.allowed_host)
    pins = normalize_pins(args.pin)

    print("Konfigurasjon som brukes:")
    print(f"  Server URL:      {server_url}")
    print(f"  Allowed hosts:   {', '.join(hosts)}")
    print(f"  Bundle ID:       {args.bundle_id}")
    print(f"  Team ID:         {args.team_id or '(behold eksisterende)'}")
    print(f"  Display name:    {args.display_name}")
    print(f"  Support e-mail:  {args.support_email}")
    print(f"  Relock seconds:  {args.relock_seconds}")
    print(f"  Build number:    {args.build_number}")
    print(f"  Version:         {args.marketing_version}")
    print(f"  Pins:            {len(pins)} configured")

    if args.print_only:
        return 0

    update_plists(
        server_url=server_url,
        hosts=hosts,
        display_name=args.display_name,
        support_email=args.support_email,
        relock_seconds=args.relock_seconds,
        pins=pins,
    )
    update_project_files(
        bundle_id=args.bundle_id,
        team_id=args.team_id,
        build_number=args.build_number,
        marketing_version=args.marketing_version,
    )
    update_export_plists(args.team_id)

    print("\nFiler oppdatert:")
    for path in PLISTS + [PROJECT_YML, PBXPROJ] + EXPORT_PLISTS:
        print(f"  - {path.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
