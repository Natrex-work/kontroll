# Fiskerikontroll – Codemagic-klargjort iOS-bygg fra PC

Denne pakken gjør det mulig å bygge den native iOS-appen fra en PC ved å bruke Codemagic som macOS-bygger i skyen. Det som er lagt inn i pakken er:

- `codemagic.yaml` med to workflows
  - `ios-testflight-internal` for TestFlight intern testing
  - `ios-adhoc-artifact` for å bygge en signert ad hoc-IPA
- delt Xcode-scheme slik at prosjektet kan bygges stabilt i CI
- `ios_native/scripts/prepare_codemagic.sh` som fyller inn server-URL, bundle ID, team ID, tillatte domener, relock-tid og eventuelle sertifikat-pins før bygging
- `CODEMAGIC_ENV.example` med variablene som skal legges inn i Codemagic

## Rask bruk

1. Pakk ut prosjektet og legg hele mappen i GitHub, GitLab eller Bitbucket.
2. Importer repoet i Codemagic.
3. Legg inn Apple Developer Portal-integrasjonen i Codemagic med navnet `KOO_ASC`.
4. Opprett eller hent signeringsfiler i Codemagic:
   - sertifikat med referanse `KOO_DIST_CERT`
   - App Store-profil med referanse `KOO_APPSTORE_PROFILE`
   - eventuelt ad hoc-profil med referanse `KOO_ADHOC_PROFILE`
5. Legg inn miljøvariablene fra `CODEMAGIC_ENV.example` i Codemagic.
6. Start workflowen `ios-testflight-internal` for intern TestFlight-distribusjon.

## Viktig avgrensing

Jeg har gjort prosjektet klart for bygging fra PC, men jeg kan ikke koble meg inn i deres Apple- eller Codemagic-kontoer herfra. Derfor må de siste stegene som krever deres legitimasjon gjøres av dere: App Store Connect API-nøkkel, sertifikat/profiler og opprettelse av app record i App Store Connect.
