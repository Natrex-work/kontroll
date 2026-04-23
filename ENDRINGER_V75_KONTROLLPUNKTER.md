# Endringer v75 – kontrollpunkter autolast

Denne oppdateringen retter feilen der kontrollpunkter ikke kom opp automatisk etter valg av art og redskap.

## Hva som var feil
- Frontend sendte alltid `lat=` og `lng=` til `/api/rules`, også når koordinatfeltene var tomme.
- FastAPI tolket tom streng som ugyldig float og svarte med `422 Unprocessable Entity`.
- Resultatet var at kontrollpunktlisten ble tom selv om art og redskap var valgt riktig.

## Rettet i denne versjonen
- `app/static/js/case-app.js`
  - sender bare `lat`/`lng` når verdiene faktisk er gyldige tall
  - viser tydeligere melding når ingen kontrollpunkter er hentet ennå
  - laster kontrollpunkter automatisk når brukeren går til steg 4
  - oppdaterer kontrollpunkter også mens art skrives i feltet
  - håndterer API-feil tydeligere
- `app/routers/api.py`
  - `/api/rules` tåler nå blanke `lat`/`lng` og behandler dem som tomme verdier i stedet for å feile
- `smoke_test.py`
  - ny test som verifiserer at `/api/rules` fungerer selv når `lat` og `lng` er blanke

## Verifisert
- Python-kode kompilerer
- `node --check app/static/js/case-app.js` er grønn
- `python smoke_test.py` er grønn
