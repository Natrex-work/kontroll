# Fiskerikontroll – produksjonsklar appversjon

Denne pakken er gjort om fra intern demo til en brukbar appversjon for ordinær drift og videre testing.

## Det som er gjort
- fjernet standard demooppsett som automatisk oppretter brukere og saker
- lagt inn tryggere sesjonshåndtering, vertskontroll, sikkerhetsheadere og CSRF-beskyttelse
- lagt inn kryptering av sensitive personopplysninger i databasen
- fjernet offentlig direkteeksponering av opplastede bevisfiler; tilgang går nå via autentiserte ruter
- eksporterte PDF- og ZIP-filer slettes automatisk etter nedlasting
- lagt inn førsteadmin-opprettelse via miljøvariabler eller `manage.py create-admin`
- styrket passordkrav
- tilpasset skjermbilder, knapper og skjemaer bedre for iPhone og iPad
- gjort appen installérbar som web-app på iPhone og iPad via Hjem-skjerm
- service worker er strammet opp slik at den ikke cacher private sider og saksdata

## Sikkerhet i denne versjonen
- krypterer valgte sensitive felter i databasen
- bruker sikrere cookie-oppsett i produksjon
- blokkerer en del vanlige nettleserbaserte angrep med sikkerhetsheadere
- beskytter tilstandsendrende forespørsler med CSRF-token
- begrenser direkte tilgang til vedlegg og bevis
- logger sikkerhetsrelevante handlinger i revisjonsspor

## Før oppstart
1. Opprett og fyll ut `.env` basert på `.env.example`
2. Sett en sterk `SESSION_SECRET`
3. Sett en egen `KV_DATA_ENCRYPTION_KEY`
4. Sett `KV_PRODUCTION_MODE=1`
5. Sett riktige `KV_ALLOWED_HOSTS`
6. Opprett første adminbruker med enten:
   - `python manage.py create-admin --email ... --name ... --password ...`
   - eller `KV_BOOTSTRAP_ADMIN_*` i miljøet

## Viktig driftsråd
For faktisk drift bør appen kjøres bak HTTPS, med sikker backup, tilgangsstyring og jevnlige oppdateringer.

## Plattform
Denne pakken er laget som en installérbar web-app/PWA og fungerer på iPhone og iPad i nettleser og fra Hjem-skjerm.
