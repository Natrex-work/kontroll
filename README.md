# KV Kontroll v49 – portal-lag, toppnavigasjon og mindre GIS-belastning

Herdet PWA / webapp for fullskala feltutprøving av kontrollsaker, kart, regelverk, registeroppslag og dokumenteksport.

## Sikkerhetsforbedringer i denne pakken
- fjernet demooppsett, demoordlyd, eksempeldatabaser og unødvendige hjelpefiler
- slått av åpne FastAPI-dokumentasjonssider i produksjon
- lagt inn **CSRF-beskyttelse** på innlogging, lagring, eksport, adminhandlinger og API-kall
- lagt inn **Trusted Host**-kontroll og strammere sesjonsinnstillinger
- lagt inn **sikkerhetsheadere** som CSP, `X-Frame-Options`, `Referrer-Policy`, `X-Content-Type-Options` og HSTS på HTTPS
- fjernet offentlig tilgang til `/uploads` og `/generated`; filer åpnes nå bare via autentiserte, saksbundne ruter
- lagt inn **filsignaturkontroll** og strengere filtrering av filtyper ved opplasting
- lagt inn **innloggingsbegrensning** mot brute force og tidsavgrenset sesjonskontroll
- oppdatert service worker til å cache kun statiske filer
- beholdt kartforbedringer med **blå GPS-prikk + nøyaktighetssirkel** og **rød kontrollnål**
- oversiktskartet viser nå **synlige soner i kartutsnittet** i egen liste
- kontrollkartet viser nå **bare soner og kartlag som matcher valgt kontrolltype, fiskeri og redskap**
- områdesjekk filtrerer nå treff etter valgt fiskeri/kontrolltype slik at varslene blir mer presise
- beholdt redigering av de tre siste sifrene i saksnummeret
- beholdt `/healthz` for Render

## Første oppstart
Kopier `.env.example` til `.env` og sett minst:

```env
KV_PRODUCTION_MODE=1
SESSION_SECRET=sett-en-lang-og-unik-hemmelig-verdi
KV_DATA_ENCRYPTION_KEY=sett-en-lang-og-unik-krypteringsnoekkel
KV_ALLOWED_HOSTS=www.dittdomene.no,dittdomene.onrender.com
KV_SESSION_HTTPS_ONLY=1
KV_BOOTSTRAP_ADMIN_EMAIL=navn@domene.no
KV_BOOTSTRAP_ADMIN_NAME=Fullt Navn
KV_BOOTSTRAP_ADMIN_PASSWORD=VelgEtSterktPassord123!Ekstra
KV_BOOTSTRAP_ADMIN_PREFIX=LBHN
```

Du kan også opprette første administrator lokalt med:

```bash
python manage.py create-admin --email navn@domene.no --name "Fullt Navn" --password "VelgEtSterktPassord123!Ekstra" --prefix LBHN
```

## Kjør lokalt
```bash
python -m pip install -r requirements.txt
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

## Kjør i Docker / Render
Denne pakken inneholder `Dockerfile` og kan brukes direkte i Render som Docker service.

Health check path:

```text
/healthz
```

Anbefalte Render-variabler:
- `KV_PRODUCTION_MODE=1`
- `KV_ALLOWED_HOSTS=www.minfiskerikontroll.no,minfiskerikontroll.onrender.com`
- `KV_SESSION_HTTPS_ONLY=1`
- `SESSION_SECRET=...`
- `KV_DATA_ENCRYPTION_KEY=...`
- `KV_BOOTSTRAP_ADMIN_EMAIL=...`
- `KV_BOOTSTRAP_ADMIN_NAME=...`
- `KV_BOOTSTRAP_ADMIN_PASSWORD=...`
- `KV_BOOTSTRAP_ADMIN_PREFIX=LBHN`
- `KV_DB_PATH=/var/data/fiskerikontroll/kv_kontroll.db`
- `KV_UPLOAD_DIR=/var/data/fiskerikontroll/uploads`
- `KV_GENERATED_DIR=/var/data/fiskerikontroll/generated`

## Nyttige miljøvariabler
- `KV_PRODUCTION_MODE`
- `SESSION_SECRET`
- `KV_DATA_ENCRYPTION_KEY`
- `KV_ALLOWED_HOSTS`
- `KV_SESSION_HTTPS_ONLY`
- `KV_SESSION_MAX_AGE_SECONDS`
- `KV_SESSION_IDLE_MINUTES`
- `KV_SESSION_ABSOLUTE_MINUTES`
- `KV_DB_PATH`
- `KV_UPLOAD_DIR`
- `KV_GENERATED_DIR`
- `KV_LOG_LEVEL`
- `KV_MAX_REQUEST_MB`
- `KV_MIN_PASSWORD_LENGTH`
- `KV_LOGIN_RATE_LIMIT_ATTEMPTS`
- `KV_LOGIN_RATE_LIMIT_WINDOW_SECONDS`
- `KV_LIVE_SOURCES`
- `KV_BOOTSTRAP_ADMIN_EMAIL`
- `KV_BOOTSTRAP_ADMIN_NAME`
- `KV_BOOTSTRAP_ADMIN_PASSWORD`
- `KV_BOOTSTRAP_ADMIN_PREFIX`

## Teststatus
- Python-syntakssjekk
- JavaScript-syntakssjekk
- smoke test med bootstrap-admin og CSRF
- health check `/healthz`
- oppretting, lagring, forhåndsvisning og PDF-eksport av sak
- saksnummerendring av tresifret løpenummer

## Merknad
Live kartlag, hummerregister, fartøyregister og andre eksterne oppslag krever internett. Når en ekstern kilde ikke svarer, brukes lokale fallback-data der det finnes trygge geografiske reserveflater og grunnleggende oppslagsdata.
