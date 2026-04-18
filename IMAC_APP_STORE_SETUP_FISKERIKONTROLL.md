# Fiskerikontroll – full oppskrift på iMac for rask App Store-klargjøring

Denne pakken er gjort klar for iMac/Xcode. Målet er at du skal kunne konfigurere, validere, archive og laste opp til App Store Connect raskt.

## Det du fyller inn før du begynner
- HTTPS-adresse til backend, f.eks. `https://kontroll.dittdomene.no`
- Bundle ID, f.eks. `no.virksomhet.fiskerikontroll`
- Apple Team ID
- support-e-post
- demo-konto til App Review

## Raskeste vei
Åpne Terminal og kjør:

```bash
cd /path/til/Fiskerikontroll/ios_native
./scripts/quick_setup_fiskerikontroll.sh   https://kontroll.dittdomene.no   no.virksomhet.fiskerikontroll   TEAMID1234   support@virksomhet.no   kontroll.dittdomene.no
```

Deretter åpner du prosjektet:

```bash
open "/path/til/Fiskerikontroll/ios_native/KontrollOgOppsynNative.xcodeproj"
```

## I Xcode
1. Logg inn i Xcode med Apple-ID.
2. Velg prosjektet og target `KontrollOgOppsynNative`.
3. Gå til **Signing & Capabilities**.
4. Bekreft at Team er riktig og at Bundle Identifier er `no.virksomhet.fiskerikontroll`.
5. Velg en iPhone/iPad-enhet eller `Any iOS Device (arm64)`.
6. Kjør **Product > Archive**.
7. I Organizer: velg **Validate App** først.
8. Deretter **Distribute App > App Store Connect > Upload**.

## Filer du bruker under innsending
- `ios_native/app_store/APP_STORE_METADATA_NO.md`
- `ios_native/app_store/APP_REVIEW_NOTES_TEMPLATE_NO.md`
- `ios_native/app_store/PRIVACY_POLICY_TEMPLATE_NO.md`
- `ios_native/app_store/SUBMISSION_CHECKLIST_NO.md`

## Viktig
Hvis du skal sende til offentlig App Store, må du ha en offentlig privacy policy-URL og en fungerende demo-konto til reviewer.
