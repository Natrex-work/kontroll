# Endringer v90 - Render-persistens, forhåndsvisning og kartlagpanel

## Hvorfor denne versjonen
Deployloggen viste at `KV_DB_PATH` fortsatt pekte til lokal appmappe. Det betyr at brukere, saker, opplastinger og genererte dokumenter kan forsvinne ved restart/deploy dersom Render ikke har persistent disk eller appen ikke skriver til `/var/data`.

Brukertest viste også at:

- Forhåndsvisning kunne ende i `{"detail":"Fant ikke saken."}`.
- Kartlagpanelet på mobil kunne ikke legges sammen/utvides pålitelig.
- Valg av grupper/områder i kartlagpanelet var vanskelig på iPhone.

## Endringer

### Persistens på Render

- Appen bruker nå `/var/data/fiskerikontroll` som standard lagringsrot når den kjører på Render, også hvis miljøvariablene ikke er satt manuelt.
- `KV_STORAGE_ROOT` er lagt inn i `render.yaml` som tydelig felles rot.
- Ved oppstart logger appen nå faktisk lagringssti for database, uploads og genererte dokumenter.
- `HEAD /` og `HEAD /healthz` returnerer 200 slik at Render-/proxy-sjekker ikke gir unødvendig 405.

Standardstier på Render:

```text
/var/data/fiskerikontroll/kv_kontroll.db
/var/data/fiskerikontroll/uploads
/var/data/fiskerikontroll/generated
```

### Forhåndsvisning og dokumentpakke

- Autosave og manuell lagring sjekker nå HTTP-status korrekt før forhåndsvisning/eksport.
- `404 Fant ikke saken` fra autosave blir ikke lenger behandlet som vellykket lagring.
- Hvis serveren ikke finner saken, forsøker appen å opprette ny serverkopi fra lokal kladd.
- Forhåndsvisning/eksport blokkeres nå hvis saken ikke er synket, i stedet for å åpne rå JSON-feil.
- Hvis en gammel `/cases/{id}/edit` åpnes og saken mangler på server, vises nå et gjenopprettingsskjema som kan laste lokal kladd fra iPhone og synke den som ny serverkopi.

### Kartlagpanel

- Kartlagpanel er versjonert til v90 slik at gammel lagret v89-tilstand ikke forstyrrer testen.
- Gruppeåpning/lukking oppdateres direkte i DOM ved trykk, før eventuelle kartoppdateringer.
- CSS bruker både `hidden` og `.is-collapsed` slik at iPhone/Safari faktisk skjuler/viser gruppeinnhold.
- Panelet har ikke lenger intern mobilklipping som skjuler knapper eller lagvalg.
- `Vis alle i gruppen` og `Skjul alle i gruppen` er lagt i to-kolonne mobilvennlig layout.

## Verifisering utført

- `python -m py_compile` på sentrale Python-filer.
- `node --check` på `common.js`, `case-app.js`, `local-cases.js`, `local-map.js`, `local-media.js`.
- FastAPI testflyt: login, ny kontroll, edit, preview, manglende sak recovery.
- PDF-generering via `/cases/{id}/pdf`.
- Render av test-PDF til PNG med PDF-verktøy.

## Viktig ved deploy

Render må ha persistent disk montert på `/var/data`. Hvis tjenesten kjører uten persistent disk, kan `/var/data` fortsatt finnes inne i containeren, men data vil ikke nødvendigvis overleve restart/deploy. Kontroller dette i Render Dashboard under Disks.
