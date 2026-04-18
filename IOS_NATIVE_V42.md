# iOS native v42 – intern distribusjon videreført

Denne pakken bygger videre på v41 og gjør prosjektet mer klart for reell intern distribusjon.

## Nytt i v42

- støtte for managed app configuration via MDM, der verdier fra `com.apple.configuration.managed` kan overstyre lokal `AppConfig.plist`
- valgfri sertifikat-pinning med `PinnedCertificateSHA256`
- nytt oppsettsskript: `ios_native/scripts/configure_ios_internal.py`
- nytt byggeskript: `ios_native/scripts/archive_and_export.sh`
- nytt hjelpeskript for sertifikathash: `ios_native/scripts/fetch_cert_sha256.py`
- eksportmal for App Store Connect / Custom App: `ios_native/export/ExportOptions-AppStoreConnect.plist`
- MDM-mal: `ios_native/mdm/ManagedAppConfig.example.plist`
- oppdatert dokumentasjon i `ios_native/README_IOS_NATIVE.md`
- prosjektversjon løftet til build 42 og version 1.2.0

## Praktisk betydning

Dette er neste steg etter ren native innpakning:

1. Sett faktisk serveradresse, bundle ID og Team ID med skriptet.
2. Velg distribusjonsmåte:
   - ad hoc til registrerte enheter
   - Custom App via Apple Business Manager
   - enterprise, hvis virksomheten er kvalifisert
3. Bruk MDM til å styre miljøverdier uten å bygge appen på nytt.
4. Bruk sertifikat-pinning hvis dere vil låse appen til egen TLS-endepunkt.

## Viktig avgrensing

Pakken inneholder fremdeles ikke en ferdig signert `.ipa`, fordi signering og endelig eksport må kjøres i Xcode på Mac med riktig Apple-konto, sertifikat og provisioning.
