# Fiskerikontroll – native iOS-app for intern distribusjon

Denne mappen inneholder en native iOS-shell for iPhone og iPad. Appen er laget for å koble seg til den sikre FastAPI-instansen av Fiskerikontroll over HTTPS, men presenteres som en vanlig iOS-app med:

- Face ID eller kodebasert gjenlåsing ved gjenåpning
- støtte for kamera, foto, mikrofon og posisjon gjennom WKWebView
- håndtering av dokumentnedlasting til deling og lagring på enheten
- enkel iPhone- og iPad-tilpasning uten nettlesergrensesnitt
- sperre for navigasjon til andre domener enn de som er angitt i konfigurasjonen
- valgfri sertifikat-pinning mot serverens TLS-sertifikat
- støtte for MDM-styrt managed app configuration

## Viktig avgrensing

Selve sakslogikken, PDF-generering, database, kryptering og tilgangsstyring ligger fortsatt på serveren. iOS-prosjektet er derfor en native app rundt den sikre web-løsningen, ikke en full omskriving av hele backend til Swift.

## Innhold

- `KontrollOgOppsynNative.xcodeproj` – Xcode-prosjekt
- `KontrollOgOppsynNative/` – SwiftUI-kildekode og ressurser
- `scripts/configure_ios_internal.py` – setter URL, bundle ID, Team ID og eksportplister
- `scripts/archive_and_export.sh` – bygger arkiv og eksporterer med `xcodebuild`
- `scripts/fetch_cert_sha256.py` – henter SHA-256 for leaf-sertifikat ved valgfri pinning
- `export/ExportOptions-AdHoc.plist` – eksempel for ad hoc-eksport
- `export/ExportOptions-Enterprise.plist` – eksempel for enterprise-eksport
- `export/ExportOptions-AppStoreConnect.plist` – eksempel for eksport som skal lastes opp til App Store Connect og senere distribueres som Custom App
- `mdm/ManagedAppConfig.example.plist` – mal for MDM-styrt appkonfigurasjon

## Rask klargjøring på Mac

Eksempel:

```bash
cd ios_native
python3 scripts/configure_ios_internal.py \
  --server-url https://kontroll.example.no \
  --bundle-id no.virksomhet.kontrollogoppsyn \
  --team-id A1B2C3D4E5 \
  --support-email it@virksomhet.no \
  --allowed-host kontroll.example.no \
  --allowed-host api.kontroll.example.no
```

Deretter kan dere bygge med:

```bash
EXPORT_OPTIONS_PLIST="$PWD/export/ExportOptions-AdHoc.plist" \
./scripts/archive_and_export.sh
```

## Managed app configuration via MDM

Appen leser administrert konfigurasjon fra `com.apple.configuration.managed` når den er distribuert som en managed app. Verdier fra MDM overstyrer lokale verdier i `AppConfig.plist`.

Nyttige felter:

- `ServerURL`
- `AllowedHosts`
- `DisplayName`
- `SupportEmail`
- `BiometricRelockEnabled`
- `RelockAfterSeconds`
- `PinnedCertificateSHA256`

Dette gjør det enklere å ha ulike miljøer uten å bygge appen på nytt for hver liten endring.

## Valgfri sertifikat-pinning

Hvis dere vil låse appen enda sterkere til egen server, kan dere legge inn `PinnedCertificateSHA256` som en liste med SHA-256-hash av leaf-sertifikatet.

Hent hash med:

```bash
python3 scripts/fetch_cert_sha256.py kontroll.example.no
```

Lim inn verdien i `AppConfig.plist` eller i MDM-konfigurasjonen. Appen godtar både hex og base64. Ved planlagt sertifikatbytte bør dere legge inn både gammel og ny hash i en overgangsperiode.

## Byggeflyt i Xcode

### Ad hoc og registrerte enheter

Brukes når dere vil installere `.ipa` på et begrenset antall registrerte iPhone- eller iPad-enheter.

1. Velg en iOS-enhet eller `Any iOS Device` som destination.
2. Velg **Product → Archive**.
3. I Organizer, velg **Distribute App**.
4. Velg eksport for registrerte enheter eller ad hoc.
5. Installer `.ipa` via Apple Configurator 2, Xcode Devices eller MDM.

### Custom App i Apple Business Manager

Brukes når appen skal distribueres internt i virksomheten via Apple Business Manager.

1. Archive appen i Xcode.
2. Last opp builden til App Store Connect.
3. Velg privat eller custom distribusjon i App Store Connect.
4. Tildel appen til virksomheten i Apple Business Manager og installer via MDM eller Apps and Books.

### Enterprise-distribusjon

Brukes bare hvis virksomheten allerede har Apple Developer Enterprise Program og er kvalifisert for direkte intern distribusjon.

## Tips for drift

- bruk alltid HTTPS
- behold serverens sikre cookies og krypteringsnøkler
- slå på `KV_PRODUCTION_MODE=1` på backend
- begrens backend til kjente verter og IP-områder
- bruk MDM hvis appen skal ut til mange enheter
- oppdater sertifikat-pins før sertifikatrotasjon


## Codemagic-bygg fra PC

Denne pakken inneholder også `codemagic.yaml` i prosjektroten og skriptet `ios_native/scripts/prepare_codemagic.sh`.

Bruk referansenavnene under i Codemagic for minst mulig manuell endring:

- Developer Portal key: `KOO_ASC`
- Distribution certificate: `KOO_DIST_CERT`
- App Store profile: `KOO_APPSTORE_PROFILE`
- Ad hoc profile: `KOO_ADHOC_PROFILE`

Se `IOS_NATIVE_V43_PC_CODEMAGIC.md` for den konkrete arbeidsflyten.
