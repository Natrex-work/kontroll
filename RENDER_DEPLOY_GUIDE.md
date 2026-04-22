# Render deploy-guide for KV Kontroll

Denne pakken er justert for de vanligste Render-problemene i v72-pakken.

## 1. Hvis deployen feiler under build
Se etter feil i stil med:

```text
ERROR: Could not find a version that satisfies the requirement uvicorn==0.45.0
```

I denne hotfix-pakken er `uvicorn` rettet til en tilgjengelig versjon.

## 2. Hvis deployen feiler etter at containeren starter
Se etter én av disse typiske årsakene:

### A. Manglende eller feil `KV_ALLOWED_HOSTS`
Symptom i logg:

```text
RuntimeError: KV_ALLOWED_HOSTS må settes eksplisitt i produksjon.
```

eller

```text
400 Invalid host header
```

Tiltak:
- bruker du bare `*.onrender.com`, vil appen i denne pakken prøve å plukke opp Render-host automatisk
- bruker du eget domene, sett `KV_ALLOWED_HOSTS` og/eller `SERVER_URL`

Eksempel:

```env
KV_ALLOWED_HOSTS=minapp.no,www.minapp.no,minapp.onrender.com
SERVER_URL=https://www.minapp.no
```

### B. DB-sti peker til en mappe som ikke finnes
Symptom i logg:

```text
sqlite3.OperationalError: unable to open database file
```

Tiltak:
- bruk denne hotfix-pakken, som oppretter foreldremappen automatisk
- anbefalt sti i Render:

```env
KV_DB_PATH=/var/data/fiskerikontroll/kv_kontroll.db
KV_UPLOAD_DIR=/var/data/fiskerikontroll/uploads
KV_GENERATED_DIR=/var/data/fiskerikontroll/generated
```

### C. Manglende produksjonshemmelighet
Symptom i logg:

```text
RuntimeError: SESSION_SECRET må settes til en unik verdi i produksjon.
```

Tiltak:
- sett `SESSION_SECRET`
- sett også `KV_DATA_ENCRYPTION_KEY`

## 3. Minste anbefalte miljøvariabler
```env
KV_PRODUCTION_MODE=1
KV_SESSION_HTTPS_ONLY=1
SESSION_SECRET=sett-en-lang-og-unik-hemmelig-verdi
KV_DATA_ENCRYPTION_KEY=sett-en-lang-og-unik-krypteringsnoekkel
KV_BOOTSTRAP_ADMIN_EMAIL=navn@domene.no
KV_BOOTSTRAP_ADMIN_NAME=Fullt Navn
KV_BOOTSTRAP_ADMIN_PASSWORD=VelgEtSterktPassord123!Ekstra
KV_BOOTSTRAP_ADMIN_PREFIX=LBHN
KV_DB_PATH=/var/data/fiskerikontroll/kv_kontroll.db
KV_UPLOAD_DIR=/var/data/fiskerikontroll/uploads
KV_GENERATED_DIR=/var/data/fiskerikontroll/generated
```

## 4. Hvis du bruker eget domene
Husk at Render kan sende health check med custom domain som `Host`-header. Derfor må domenet være tillatt i appen.

Bruk minst ett av disse:

```env
KV_ALLOWED_HOSTS=minapp.no,www.minapp.no,minapp.onrender.com
```

eller

```env
SERVER_URL=https://www.minapp.no
```

## 5. Slik skiller du build-feil og runtime-feil
- **build-feil** skjer under `pip install` eller Docker build
- **runtime-feil** skjer etter at containeren er startet
- **health-check-feil** vises ofte som at deployen aldri blir frisk selv om appen nesten starter

## 6. Anbefalt videreutvikling etter at deploy er oppe
- flytt fra SQLite til managed Postgres hvis flere brukere skal jobbe samtidig
- legg smoke test i GitHub Actions før auto deploy
- lag eksport av revisjonslogg for saksgjennomgang
- lag enkel konfliktvarsling når lokal sakskladd synkes til server
