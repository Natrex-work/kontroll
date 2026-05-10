# Endringer v97 - stabilitet, retry og kortere mobilflyt

Fokus i v97 er bugfix og stabilisering etter v96: færre duplikater, bedre autosave under dårlig nett, tryggere sletting av vedlegg og kortere statustekster.

## Autosave og konflikt

- Autosave har nå intern kø dersom bruker endrer felter mens en lagring allerede pågår.
- Endringer gjort under pågående autosave lagres i neste runde i stedet for å bli liggende bare lokalt.
- Konfliktmelding er kortere: `Konflikt. Last inn eller behold lokal kopi.`

## Bilder og lyd

- Lokale medier har `updated_at` og DB-schema v4.
- Medier som ble stående som `uploading` etter lukking/restart forsøkes synket på nytt når de er gamle nok.
- Serveropplasting er idempotent på `local_media_id`: retry fra mobil lager ikke dublettfil eller dublettvedlegg.
- Originalfilen beholdes lokalt etter synk og serveren fungerer som backup.

## CSRF og sletting

- Dynamisk genererte sletteknapper for bilde/lyd får CSRF-token.
- Serverrenderte sletteknapper i skjemaet får også CSRF-token.
- Testet opplasting, idempotent retry og sletting av evidence via API/TestClient.

## Kortere UI-status

- Flere lange hjelpetekster i lokal lagring/synk er gjort kortere.
- Eksempler: `Lagret lokalt`, `Synk venter`, `Konflikt`, `Bilde lokalt`, `Lyd lokalt`.

## Cache/versjon

- Statisk cache, service worker og script/css-parametre er løftet til v97.

## Verifisering

- `python -m compileall -q app`: OK
- `node --check` på alle JS-filer: OK
- `smoke_test.py`: OK
- `render_smoke_test.py`: OK
- Egen test for opplasting/retry/sletting av evidence: OK
- ZIP-integritet må kontrolleres etter pakking.
