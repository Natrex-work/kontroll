# Endringer v94 - stabilisering, tekst, kartlag og signatur

Denne versjonen fortsetter stabiliseringsarbeidet fra v93.

## Standardtekst / patruljeformål
- Standardtekst er omskrevet slik at den tydeligere beskriver når, hvor, type kontroll/patrulje, valgt fiskeri/redskap og kontrollformål.
- Synlige tips-/oppfolgingsvalg er fjernet fra standardtekstmenyen for å holde teksten mer nøytral og etterprovbar.
- Uonskede formuleringer om anmeldelsesegnet form og tidligere registrerte opplysninger fjernes ogsa i tekstforbedrings-API.

## Roller og synlige felt
- Synlig statusindikator i roller/grunnlag er fjernet.
- Kilde/tipsgiver og status fjernes fra PDF-metarader/fallback.
- Tjenestested bruker ikke lenger skjult kildefelt som fallback.

## Kartlagpanel
- Kartlagpanel i ekstern/mobil visning klippes ikke lenger med fast maksimalhoyde.
- Gruppevalg, utvid/legg sammen og vis/skjul skal ha bedre plass pa mobil.
- Cache-/lagvalgversjon er oppdatert til v94 slik at gammel v93-tilstand ikke skal forstyrre test.

## PDF/signatur
- Touch-signaturbilder tegnes na inn i PDF der signaturen finnes, blant annet i avhor og beslagsrapport.
- Signaturfelt viser fortsatt navn og tidspunkt, men beholder ogsa håndskrevet signaturbilde der dette er lagret.
- PDF-fallback-branding er ryddet til Minfiskerikontroll.

## Verifisering
- Python compileall: OK
- JavaScript node --check: OK
- smoke_test.py: OK
- render_smoke_test.py: OK
- Test-PDF med signaturbilder generert og rendret til PNG for visuell kontroll.
