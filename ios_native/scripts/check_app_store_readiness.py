#!/usr/bin/env python3
from __future__ import annotations

import plistlib
import re
import sys
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "KontrollOgOppsynNative"
errors: list[str] = []

with (APP / "AppConfig.plist").open("rb") as f:
    cfg = plistlib.load(f)
server = cfg.get("ServerURL", "")
display = cfg.get("DisplayName", "")
hosts = cfg.get("AllowedHosts", [])
parsed = urlparse(server)
if parsed.scheme != "https" or not parsed.netloc or parsed.hostname == "example.invalid":
    errors.append("AppConfig.plist mangler gyldig HTTPS ServerURL.")
if display != "Fiskerikontroll":
    errors.append("DisplayName er ikke satt til Fiskerikontroll.")
if not hosts:
    errors.append("AllowedHosts er tom.")

project_yml = (ROOT / "project.yml").read_text(encoding="utf-8")
m = re.search(r"PRODUCT_BUNDLE_IDENTIFIER:\s*([^\n]+)", project_yml)
if not m or "no.example" in m.group(1):
    errors.append("Bundle ID er fortsatt eksempelverdi i project.yml.")
if "MARKETING_VERSION: 1.4.0" not in project_yml:
    errors.append("MARKETING_VERSION er ikke 1.4.0 i project.yml.")
if "CURRENT_PROJECT_VERSION: '44'" not in project_yml:
    errors.append("CURRENT_PROJECT_VERSION er ikke 44 i project.yml.")

with (ROOT / "export" / "ExportOptions-AppStoreConnect.plist").open("rb") as f:
    export_cfg = plistlib.load(f)
if export_cfg.get("teamID") in {None, "", "SETT_TEAM_ID"}:
    errors.append("ExportOptions-AppStoreConnect.plist mangler Team ID.")

with (APP / "PrivacyInfo.xcprivacy").open("rb") as f:
    privacy = plistlib.load(f)
found = False
for item in privacy.get("NSPrivacyAccessedAPITypes", []):
    if item.get("NSPrivacyAccessedAPIType") == "NSPrivacyAccessedAPICategoryUserDefaults" and "AC6B.1" in item.get("NSPrivacyAccessedAPITypeReasons", []):
        found = True
if not found:
    errors.append("PrivacyInfo.xcprivacy mangler UserDefaults-grunnlaget AC6B.1.")

for rel in [
    ROOT / "app_store" / "APP_STORE_METADATA_NO.md",
    ROOT / "app_store" / "APP_REVIEW_NOTES_TEMPLATE_NO.md",
    ROOT / "app_store" / "PRIVACY_POLICY_TEMPLATE_NO.md",
]:
    if not rel.exists():
        errors.append(f"Mangler hjelpefil: {rel.relative_to(ROOT)}")

if errors:
    print("IKKE KLAR FOR APP STORE")
    for err in errors:
        print(f" - {err}")
    sys.exit(1)

print("KLAR FOR NESTE STEG")
print(" - Konfigurasjonen ser grei ut for lokal archive/upload i Xcode.")
print(" - Husk fortsatt App Store Connect-metadata, skjermbilder, demo-konto og personvernsider.")
