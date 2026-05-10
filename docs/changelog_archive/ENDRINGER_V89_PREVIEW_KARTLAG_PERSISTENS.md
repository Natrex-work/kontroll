# Endringer v89 - preview, dokumentpakke, kartlag og persistens

## Rettet: Forhåndsvisning/dokumentpakke ga «Fant ikke saken»

- Forhåndsvisning og eksport forsøker nå å synke saken til server før handlingen kjøres.
- Autosave kontrollerer HTTP-status riktig. En 404 fra `/api/cases/{id}/autosave` blir ikke lenger tolket som vellykket lagring.
- Hvis serveren ikke finner saken, forsøker appen å opprette en ny serverkopi fra utfylt lokal kladd før forhåndsvisning/PDF/ZIP.
- Preview- og eksportlenker oppdateres til nytt saksnummer/saks-ID etter slik gjenoppretting.
- Hvis en gammel direktelenke likevel åpnes, vises en forklarende HTML-side i stedet for rå JSON.

## Rettet: Kartlagpanelet kunne ikke legges sammen/utvides

Rotårsak: CSS-reglene for `.kv-temalag-card` og `.kv-temalag-group-body` overstyrte HTML-attributtet `hidden`. Derfor ble kort og grupper ikke faktisk skjult selv om JavaScript satte `hidden`.

- Lagt inn eksplisitt `display: none !important` for skjulte kartlagkort og gruppeinnhold.
- Oppdatert kartlag-prefiks til v89 slik at gammel lagret v88-tilstand ikke forstyrrer testen.
- På mobil starter kartlaglisten med første gruppe åpen og øvrige grupper lukket.
- Gruppeknapper har nå tydelig pil og større treffflate.
- `Vis alle i gruppen` og `Skjul alle i gruppen` stopper klikkbobling og skal fungere mer stabilt på iPhone/Safari.
- Kartlagkortet har bedre scrolling på mobil.

## Rettet: Datatap etter deploy / Render

- `render.yaml` er oppdatert med persistent disk på `/var/data`.
- Standard anbefalte runtime-stier settes nå i Render blueprint:
  - `KV_DB_PATH=/var/data/fiskerikontroll/kv_kontroll.db`
  - `KV_UPLOAD_DIR=/var/data/fiskerikontroll/uploads`
  - `KV_GENERATED_DIR=/var/data/fiskerikontroll/generated`

Dette er viktig fordi SQLite-databasen ellers ligger i appmappen og kan forsvinne ved ny deploy/restart i Render-miljø.

## Dokumentpakke

- Malbasert PDF-flyt er beholdt som hovedløp.
- Dokumentrekkefølgen og utfylling skjer fortsatt via PDF-template/layout i `app/pdf_export.py` og `app/pdf_templates/`.
- Vedlagte maler ligger fortsatt i `app/document_templates/` som referansemaler.

## Verifisering utført

- Python `py_compile` på sentrale filer.
- `node --check` på JavaScript-filer.
- FastAPI-testflyt:
  - login
  - ny kontroll
  - edit-side
  - preview
  - PDF-generering
  - manglende sak viser forklarende HTML-side
- Test-PDF ble rendret til 7 sider med `render_pdf.py`.
