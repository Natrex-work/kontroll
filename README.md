# KV Kontroll Demo v25

Lokal demo/PWA for stegvis kontroll av fritidsfiske og kommersielt fiskeri.

## Hva som er gjort i v25
- delt backend opp i **routers** for auth, sider, admin, saker og API
- flyttet sakslogikk til **services** for bootstrap, saker, PDF, regelverk og registeroppslag
- lagt til **miljøstyrt konfigurasjon** i `app/config.py`
- lagt til enkel **logging** og tydelig varsel hvis `SESSION_SECRET` ikke er satt
- strammet inn **validering** av e-post, passord, saksnummer-prefix, koordinater og filopplasting
- flyttet frontend til **side-spesifikke scripts** (`common.js`, `map-overview.js`, `rules-overview.js`, `case-app.js`)
- beholdt eksisterende demo-funksjoner og eksportflyt

## Prosjektstruktur
```text
app/
  main.py
  config.py
  logging_setup.py
  dependencies.py
  ui.py
  validation.py
  schemas.py
  routers/
    auth.py
    pages.py
    admin.py
    cases.py
    api.py
  services/
    bootstrap_service.py
    case_service.py
    pdf_service.py
    rules_service.py
    registry_service.py
  static/js/
    common.js
    map-overview.js
    rules-overview.js
    case-app.js
```

## Miljøvariabler
Kopier `.env.example` til `.env` og sett minst:

```bash
SESSION_SECRET=sett-en-lang-og-unik-hemmelig-verdi
```

Andre valgfrie innstillinger:
- `KV_DB_PATH`
- `KV_UPLOAD_DIR`
- `KV_GENERATED_DIR`
- `KV_LOG_LEVEL`
- `KV_MAX_UPLOAD_MB`
- `KV_LIVE_SOURCES`

## Windows
1. Pakk ut zip-filen.
2. Åpne mappen `kv_kontroll_demo_v24`.
3. Lag eventuelt en `.env` basert på `.env.example`.
4. Dobbeltklikk `start_windows.bat`.
5. Hvis nettleseren ikke åpnes automatisk, åpne `http://127.0.0.1:8000`.

## Manuell oppstart
```bash
python -m pip install -r requirements.txt
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

## Innlogging
- Admin: `admin@kv.demo` / `Admin123!`
- Kontrollør: `kontrollor@kv.demo` / `Demo123!`

## Teststatus
- Python-syntakssjekk bestått
- JavaScript-syntakssjekk bestått
- backend smoke-test bestått
- PDF-eksport bestått
- ZIP-eksport bestått
- eksport av kun avhørsrapport bestått

## Merknad
Dette er fortsatt en lokal testversjon. Live kartlag, hummerregister, fartøyregister og eventuelle katalogoppslag krever internett. Hvis en ekstern kilde ikke svarer, brukes lokale demo-data der det finnes fallback.
