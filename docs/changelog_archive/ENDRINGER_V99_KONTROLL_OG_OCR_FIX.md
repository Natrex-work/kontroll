# V99 kontroll og OCR-fix

- Rettet klientfilter for OCR-navn slik at `Vis nummer`, `Vis telefon`, `1881` og `Gulesider` ikke kan bli brukt som navn i autofyll på mobil.
- Kontrollert at serverfilteret allerede hadde tilsvarende sperre.
- Kjørt statisk kontroll av sentrale Python- og JavaScript-filer.
- Kjørt røykflyt delvis/indikativt i TestClient-logg: login, ny kontroll, kartkatalog, zones-check, OCR-endepunkt, oppsummering, preview og PDF.

Ikke fullverifisert uten fysisk iPhone/Render/live GPS/live kart/ekte kamera-OCR.
