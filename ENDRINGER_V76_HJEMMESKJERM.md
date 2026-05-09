# Endringer v76 – hjemme-/innloggingsskjerm

Denne oppdateringen gjør startsiden og innloggingen mer lik oppsettet i den vedlagte referansen.

## Gjort

- byttet synlig tekstbranding fra `KV Kontroll` til `Kontroll`
- beholdt `MK` som merke/logo i toppfelt og på innlogging
- lagt inn toppfelt på mobil med merke til venstre og rund menyknapp til høyre
- laget ny mobil bunnnavigasjon med hurtigvalg for Hjem, Ny, Kart, Regler og Saker
- bygget om dashboard/hjemmeskjerm til store, mørkeblå kort i 2x2-oppsett
- lagt inn bred kart-knapp/hero-blokk i samme visuelle stil som referansen
- lagt inn lange rad-kort under hurtigvalgene for snarveier videre i appen
- oppdatert innloggingsskjermen til samme visuelle uttrykk
- endret standard appnavn i konfigurasjon fra `KV Kontroll` til `Kontroll`
- lagt inn sikker visning som fortsatt skjuler `KV` selv om gammel miljøverdi skulle være satt
- oppdatert brukerrettighetslabel fra `KV Kontroll` til `Kontroll`

## Filer som er endret

- `app/config.py`
- `app/db.py`
- `app/ui.py`
- `app/templates/base.html`
- `app/templates/dashboard.html`
- `app/templates/login.html`
- `app/static/styles.css`

## Verifisert

- Python-koden kompilerer
- eksisterende `smoke_test.py` går grønt
- innloggingssiden viser ikke `KV Kontroll`
- dashboardsiden viser ikke `KV Kontroll`
