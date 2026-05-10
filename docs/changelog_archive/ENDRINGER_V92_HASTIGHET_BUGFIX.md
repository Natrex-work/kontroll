# Endringer v92 - hastighet, stabilitet og bugfix

Denne versjonen viderefører v91 og prioriterer ytelse/stabilitet i feltbruk fremfor nye visuelle endringer.

## Hastighet og stabilitet

- Flyttet tunge OCR-importer til lazy loading:
  - `pytesseract` importeres først når OCR faktisk kjøres.
  - `opencv/numpy` importeres bare dersom deskew er slått på.
- Deskew er av som standard (`KV_OCR_ENABLE_DESKEW=0`) fordi OpenCV gjør små containere tregere og kan påvirke test/helse-sjekk.
- OCR kjører med lavere standard bilde- og variantbelastning:
  - `KV_OCR_MAX_SIDE=1500`
  - `KV_OCR_MIN_SIDE=850`
  - `KV_OCR_VARIANT_LIMIT=5`
  - `KV_OCR_ATTEMPT_TIMEOUT=5`
- OCR API har kortere serverramme (`timeout_seconds=16`).
- Mobilklienten stopper nå OCR-retry riktig ved timeout/for store bilder, i stedet for å fortsette med flere tunge forsøk.

## Kart og områder

- Kartbundle med bbox laster ikke lenger ned hele live-laget dersom bbox-spørringen ikke gir treff. Dette skal redusere ventetid kraftig på mobil.
- Maks automatisk kartbundle er redusert fra 10 til 8 lag.
- Case-kartet viser færre tunge detaljlag automatisk:
  - maks 6 relevante lag i visning
  - maks 4 detaljlag for features
  - større raster-chunking for færre tile-/export-lag
- Områdesjekk cache er økt og kan styres med `KV_ZONE_STATUS_CACHE_SECONDS`, standard 90 sekunder.
- Live punktkontroll mot kartportal er begrenset med `KV_ZONE_CHECK_MAX_LIVE_LAYERS`, standard 14 lag.
- Reverse geocoding kjøres ikke lenger hver gang dersom lokal stedsinformasjon finnes.
- Reverse geocoding har egen hurtigbuffer.
- Frontend avbryter gamle områdesjekker når ny posisjon/nytt valg kommer, og bruker kort klientcache for identisk posisjon/fiskeri/redskap.

## Temakartpanel

- Kartlagpreferanser er versjonert til v92 slik at gammel lagringsstatus ikke forstyrrer testen.
- `Utvid alle`, `Legg sammen`, gruppevis åpne/lukke og `Vis/Skjul alle i gruppen` beholdes, men med raskere kartoppdatering i bakgrunnen.

## Dokument/PDF/e-post

- PDF-templatebilder caches i minne slik at dokumentgenerering blir raskere.
- E-postutsending markerer ikke lenger saken som “Anmeldt og sendt” før SMTP-sending faktisk er fullført.
- ZIP-eksport via vanlig eksport beholder tidligere statuslogikk.

## Database

- SQLite får `busy_timeout` for færre skrivekonflikter.
- Init setter WAL/synchronous normal der miljøet støtter det.
- Lagt til indekser for saker, vedlegg og auditlogg.

## Versjon/cache

- Appversjon og statiske cache-nøkler er oppdatert til v92.
- `smoke_test.py` og `render_smoke_test.py` terminerer nå eksplisitt etter ferdige tester for å unngå at native OCR/PDF-håndtak holder prosessen åpen.

## Verifisering

- Python compileall OK.
- JavaScript `node --check` OK for alle filer i `app/static/js`.
- Importtest av `app.main` OK uten heng etter lazy OCR-import.
- Lett FastAPI-flow verifisert i logg:
  - HEAD `/` og `/healthz`
  - login
  - ny kontroll
  - lagring
  - forhåndsvisning
  - PDF-generering
  - områdesjekk
  - kartbundle
  - e-postfeil uten SMTP gir kontrollert 400, ikke krasj
- Full `smoke_test.py`-flyt ble kjørt gjennom hovedpunktene og logget `SMOKE_MAIN_RETURNED 0` med wrapper, men testmiljøet har vist ustabil shell-retur rundt OCR/Tesseract. Derfor bør reell iPhone/Render-test fortsatt kjøres.
