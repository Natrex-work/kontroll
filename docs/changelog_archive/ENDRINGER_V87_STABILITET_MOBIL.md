# Endringer v87 - stabilitet, mobil-OCR og kart

Denne pakken er laget som en stabiliseringsrunde for mobil bruk i felt.

## Hovedendringer

- Oppdatert versjon/cache fra v86 til v87.
- Synlige brukerfeil med gammelt navn `KV Kontroll` er endret til `Minfiskerikontroll`.
- Maks opplasting og maks request-storrelse er samordnet via config, slik at store mobilbilder stoppes tidligere og mer forutsigbart.
- API-kall som stopper pa request-storrelse returnerer JSON-feil for `/api/*` i stedet for ren tekst.

## OCR/autofyll

- Server-OCR kjores i threadpool i stedet for a blokkere async requesten.
- OCR har egen maksgrense for bilde (`KV_OCR_MAX_IMAGE_MB`, standard 12 MB).
- Server-OCR har kortere, mer deterministisk tidsramme og hardere veggklokke-grense.
- Tesseract-varianter er redusert og avbrytes tidligere nar gode felt/hints er funnet.
- iPhone/Safari/mobil prioriterer optimalisert bilde til server og laster ikke lenger opp originalbildet som tung fallback.
- Frontend stopper tydelig med feilmelding i stedet for a bli staende i uendelig OCR-arbeid.

## Kart/overlay

- Kartpakker og offline-varming begrenses til et mindre antall relevante lag.
- `/api/map/bundle` markerer om laglisten er avkortet og returnerer `ok:false` ved feil i stedet for stille tomt resultat.
- Case-kartet henter bare feature-detaljer for prioriterte synlige lag og trefflag.
- Rasterchunking er redusert for mindre belastning pa mobil.

## Ny kontroll og eksport

- Ny kontroll-flyt er beholdt som POST, med redirect til `step=1` etter at sak er opprettet.
- PDF-/intervju-/ZIP-eksport kjores i threadpool fra async routes for a redusere blokkering av serveren.

## Oppsummeringstekster

- Omradetekster i PDF/preview er strammet inn slik at de blir mer rapportvennlige.
- Lokal fallback-oppsummering i frontend bruker tydeligere formulering:
  - observert/kontrollert redskap
  - kontrollposisjon innenfor omrade
  - forbud/begrensninger i omradet

## Testet i denne runden

- Python-syntaks: `py_compile` pa sentrale moduler.
- JavaScript-syntaks: `node --check` pa sentrale JS-filer.

Ikke fullverifisert her:

- Full smoke test med FastAPI/TestClient i runtime-miljo.
- Reell iPhone/Safari-test.
- Live karttjenester under mobilnett.
