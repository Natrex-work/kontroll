# Minfiskerikontroll – Render-hotfix og videreutviklet pakke

Herdet PWA / webapp for feltutprøving av kontrollsaker, kart, regelverk, registeroppslag og dokumenteksport.

## Hva som er rettet i denne pakken
- rettet `uvicorn`-pin i `requirements.txt` slik at Docker-bygg i Render ikke stopper på en ugyldig versjon
- appen godtar nå automatisk Render sitt `onrender.com`-vertsnavn når den kjører i produksjon på Render
- appen oppretter nå også foreldremappen til `KV_DB_PATH` automatisk ved oppstart
- `KV_ALLOWED_HOSTS` tåler nå også at du ved en feil legger inn full URL i stedet for bare vertsnavn
- lagt ved egen Render-guide med sjekkliste og forklaring på vanlige feil

## Sikkerhetsoppsett som fortsatt gjelder
- åpne FastAPI-dokumentasjonssider er slått av i produksjon
- CSRF-beskyttelse på innlogging, lagring, eksport, adminhandlinger og API-kall
- Trusted Host-kontroll og strammere sesjonsinnstillinger
- sikkerhetsheadere som CSP, `X-Frame-Options`, `Referrer-Policy`, `X-Content-Type-Options` og HSTS på HTTPS
- offentlig tilgang til `/uploads` og `/generated` er fjernet
- filsignaturkontroll og strengere filtrering av filtyper ved opplasting
- innloggingsbegrensning mot brute force og tidsavgrenset sesjonskontroll
- service worker cacher bare statiske filer

## Første oppstart
Kopier `.env.example` til `.env` og sett minst:

```env
KV_PRODUCTION_MODE=1
SESSION_SECRET=sett-en-lang-og-unik-hemmelig-verdi
KV_DATA_ENCRYPTION_KEY=sett-en-lang-og-unik-krypteringsnoekkel
KV_SESSION_HTTPS_ONLY=1
KV_BOOTSTRAP_ADMIN_EMAIL=navn@domene.no
KV_BOOTSTRAP_ADMIN_NAME=Fullt Navn
KV_BOOTSTRAP_ADMIN_PASSWORD=VelgEtSterktPassord123!Ekstra
KV_BOOTSTRAP_ADMIN_PREFIX=LBHN
```

Hvis du bruker eget domene, sett også minst ett av disse:

```env
KV_ALLOWED_HOSTS=www.dittdomene.no,dittdomene.onrender.com
SERVER_URL=https://www.dittdomene.no
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

### Anbefalte Render-variabler
- `KV_PRODUCTION_MODE=1`
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

### Viktig om vertsnavn i Render
- Hvis du **bare** bruker `*.onrender.com`, vil appen nå automatisk plukke opp Render sitt vertsnavn.
- Hvis du bruker **eget domene**, sett `KV_ALLOWED_HOSTS` og/eller `SERVER_URL` eksplisitt til domenet ditt.
- Hvis `KV_ALLOWED_HOSTS` er feil, vil `/healthz` kunne svare `400 Invalid host header`, og Render vil markere deployen som mislykket.

### Viktig om lagring i Render
- Uten persistent disk er filsystemet midlertidig.
- Appen oppretter nå nødvendige mapper automatisk, men data vil fortsatt forsvinne ved restart uten disk.
- For varig lagring anbefales Render-disk montert på `/var/data`.

## Teststatus
- Python-syntakssjekk
- JavaScript-syntakssjekk
- eksisterende smoke test for innlogging, sak, kart og PDF
- ekstra Render-smoke test for auto-host og oppretting av DB-mappe

## Merknad
Live kartlag, hummerregister, fartøyregister og andre eksterne oppslag krever internett. Når en ekstern kilde ikke svarer, brukes lokale fallback-data der det finnes trygge geografiske reserveflater og grunnleggende oppslagsdata.
