# Endringer 1.8.44 — Opprydning + sikkerhetsherding

To parallelle arbeidssett: rydding av prosjektmappen og styrking av
sikkerheten mot vanlige angrepsvektorer. **Ingen funksjonelle endringer**
for sluttbruker.

---

## Del 1 — Filopprydning

### Slettet (ubrukt kode)
```
app/services/hummerfisker_register.py    — ikke importert noe sted
app/services/tableau_lookup_service.py   — ikke importert noe sted
app/templates/audit_log.html             — kun strengetreff, aldri rendret
app/document_templates/*.dot             — ikke brukt runtime (4 filer, ~700 KB)
app/document_templates/Anmeldelse_Mal.xlsx — ikke brukt runtime (~300 KB)
smoke_test.py + render_smoke_test.py     — dev-utility, ikke i prod-deploy
PYTHON311_FIX_NOTAT.md                   — obsolet fix-notat
ENDRINGER_RENDER_HOTFIX.md               — obsolet
```

### Arkivert (~75 endringslogg-filer)
Alle tidligere endringslogger er flyttet fra rotmappen til
`docs/changelog_archive/`. Rotmappen har nå kun de siste 8 endringslogger
(v1.8.36 → v1.8.44) for oversikt, og full historikk i arkiv.

### Bevart (faktisk i bruk runtime)
```
app/pdf_templates/page-01.png … page-10.png + logo_box.png
  → Bakgrunns-overlay for ReportLab-PDF-generering. Brukes fra
    pdf_export.py for å generere politiskjema-stil PDF-er.

data/*.json                  → Brukt av live_sources, registry, rules
data/cache/portal_layers_v86 → Aktiv catalog-cache
generated/                   → Runtime-genererte PDF-er
```

### PDF-mal-spørsmålet
Brukeren spurte om det var nødvendig å bruke ferdig utfylte PDF-templates.
Svar etter analyse:

- **PNG-bakgrunnene i `app/pdf_templates/`** brukes ja — `pdf_export.py`
  importerer dem og overlayer tekst med ReportLab. Disse må beholdes.
- **`.dot`-filene og `.xlsx`-malene i `app/document_templates/`** ble
  IKKE brukt runtime — de var kun referanse-kildemateriale. Slettet.

`TEMPLATE_MAPPING_V88.md` flyttet til `docs/` for fremtidig referanse.

### Resultat
| Mål | Før | Etter |
|---|---|---|
| Endringslogg-filer i rot | ~80 | 8 (resten arkivert) |
| `app/document_templates/` | ~1 MB (.dot + .xlsx) | 8 KB (kun mapping.md) |
| Ubrukte Python-tjenester | 2 | 0 |
| Ubrukte templates | 1 | 0 |
| Total prosjektstørrelse | ~12 MB | ~7.3 MB |

---

## Del 2 — Sikkerhetsherding

21/21 sikkerhetssjekker passerer.

### 2.1 Fail-fast på svake hemmeligheter i produksjon

```python
# app/main.py — create_app()
if settings.production_mode and settings.session_secret == 'dev-session-secret-change-me':
    raise RuntimeError('KRITISK: SESSION_SECRET er satt til standard dev-verdi i produksjon...')
if settings.production_mode and len(settings.session_secret) < 32:
    raise RuntimeError('KRITISK: SESSION_SECRET er for kort i produksjon...')
```

**Effekt:** Appen vil **nekte å starte** hvis SESSION_SECRET er den
hardkodede dev-verdien eller kortere enn 32 tegn i produksjon. Hindrer
en av de mest vanlige reelle angrepsvektorene på Python web-apper:
fork/cloning av kildekode + bruk av default secret = forfalskede
session-cookies.

Generer sikker secret:
```bash
python -c "import secrets; print(secrets.token_hex(48))"
```

### 2.2 Strammere security headers

`SecurityHeadersMiddleware` har fått tre nye + ett oppdatert:

| Header | Verdi |
|---|---|
| **X-Permitted-Cross-Domain-Policies** | `none` (NY — blokker Flash/PDF cross-domain) |
| **Permissions-Policy** | Utvidet med `payment=(), usb=(), magnetometer=(), gyroscope=(), accelerometer=(), interest-cohort=()` |
| **Server** | `kv` (skjul versjon hvis upstream setter det) |
| **X-Content-Type-Options** | `nosniff` også på /static/-paths |

Eksisterende: CSP, X-Frame-Options:DENY, HSTS, Referrer-Policy,
COOP/CORP — alle fortsatt på plass.

### 2.3 Path-traversal defense-in-depth

```python
# app/routers/cases.py — evidence_file & generated_file
path = settings.upload_dir / filename
try:
    resolved = path.resolve()
    upload_root = settings.upload_dir.resolve()
    if not str(resolved).startswith(str(upload_root) + '/') and resolved != upload_root:
        raise HTTPException(status_code=404, detail='Fant ikke filen.')
except (OSError, ValueError):
    raise HTTPException(status_code=404, detail='Fant ikke filen.')
if not path.exists() or not path.is_file():
    raise HTTPException(status_code=404, detail='Fant ikke filen.')
```

Selv om `Path(filename).name` allerede stripper `../`-segmenter, sjekker
vi nå at **resolved path er innenfor opplastings-/generated-roten**.
Beskytter mot symlink-attacker (om noen lå inne).

### 2.4 Rate limit på dyre API-endepunkter

Ny `enforce_rate_limit()`-helper i `app/security.py`:

```python
enforce_rate_limit(request, 'vision', max_attempts=10, window_seconds=60, user_id=user.get('id'))
```

Aktivert på:
| Endepunkt | Limit |
|---|---|
| `POST /api/ocr/extract` | 20/min per bruker |
| `POST /api/person-fartoy/analyze-image` | 10/min per bruker |

Beskytter mot:
- DDoS via OCR (Tesseract bruker mye CPU)
- OpenAI-quote-tømming via Vision API
- Misbruk av eksterne tredjepartstjenester (Tableau)

Logger 429-hendelser via `audit_security_event` for senere analyse.

### 2.5 SQLite-herding

```python
# app/db.py — get_conn()
conn.execute('PRAGMA journal_mode = WAL')      # bedre concurrency
conn.execute('PRAGMA synchronous = NORMAL')    # ytelse + sikkerhet
conn.execute('PRAGMA secure_delete = ON')      # overskrive slettede data
conn.execute('PRAGMA trusted_schema = OFF')    # blokk function-injection
```

| PRAGMA | Sikkerhetseffekt |
|---|---|
| `journal_mode = WAL` | Skrive-låsen blokkerer ikke lesere → mindre DoS-risiko |
| `secure_delete = ON` | Slettede rader overskrives → nedfelt data kan ikke gjenopprettes |
| `trusted_schema = OFF` | SQLite tillater ikke at user-defined functions/triggers/views med tilfeldige funksjoner kjører automatisk → blokkerer schema-baserte angrep |
| `synchronous = NORMAL` | Balanse mellom ytelse og crash-safety i WAL-modus |

### 2.6 CSRF-dekning verifisert

Automatisk script som finner alle `@router.post|put|delete|patch`-decorators
og sjekker at funksjonsbody inneholder `enforce_csrf(request)`:

**Resultat: 32/32 endepunkter har CSRF-sjekk** — ingen huller.

### 2.7 SQL-injection — verifisert

Tre f-strings i `app/db.py` ble undersøkt:
- `PRAGMA table_info({table_name})` — `table_name` er hardkodet konstant ✓
- `ALTER TABLE {table_name} ADD COLUMN {ddl}` — kun migrasjon, hardkodet ✓
- `UPDATE cases SET {", ".join(assignments)} WHERE id = ?` — `assignments`
  bygges fra **kolonnewhitelist** i Python, ikke brukerinput ✓

Alle bruker-leverte verdier er parametriserte (`?`-placeholders).

---

## Del 3 — Filer endret

```
MOD:
  app/main.py               — fail-fast på dev session secret
  app/middleware.py         — utvidede security headers
  app/security.py           — ny enforce_rate_limit() helper
  app/routers/api.py        — rate limit på OCR + vision
  app/routers/cases.py      — path-traversal defense-in-depth
  app/db.py                 — SQLite WAL + secure_delete + trusted_schema OFF
  app/static/sw.js          — cache-bump
  app/config.py             — versjon 1.8.44

DEL:
  app/services/hummerfisker_register.py    (ubrukt)
  app/services/tableau_lookup_service.py   (ubrukt)
  app/templates/audit_log.html             (ubrukt)
  app/document_templates/*.dot             (ikke brukt runtime)
  app/document_templates/Anmeldelse_Mal.xlsx
  smoke_test.py
  render_smoke_test.py
  PYTHON311_FIX_NOTAT.md
  ENDRINGER_RENDER_HOTFIX.md

FLYTTET:
  ~75 ENDRINGER_*.md       → docs/changelog_archive/
```

## Del 4 — Filer bevisst IKKE endret

- DB-skjema og migrations
- Sync-orkestrator
- Frontend (case-app.js, common.js, map-overview.js)
- Templates (case_form.html etc.)
- Bilde-/lyd-validering (allerede solid fra v1.8.41)
- Login-flyt (eksisterende rate limit + bcrypt fortsatt aktiv)

---

## Del 5 — Sikkerhetsanbefalinger til drift

Disse miljøvariablene **bør** settes i Render/produksjon:

```bash
KV_PRODUCTION_MODE=true
SESSION_SECRET=$(python -c "import secrets; print(secrets.token_hex(48))")
KV_ALLOWED_HOSTS=minfiskerikontroll.no,www.minfiskerikontroll.no
KV_SESSION_HTTPS_ONLY=true
KV_SESSION_SAMESITE=lax           # eller 'strict' for ekstra beskyttelse
KV_SESSION_MAX_AGE_SECONDS=43200  # 12 timer (default)
KV_SESSION_IDLE_MINUTES=30        # auto-utlogg etter 30 min inaktivitet
KV_LOGIN_RATE_LIMIT_ATTEMPTS=10
KV_LOGIN_RATE_LIMIT_WINDOW_SECONDS=900
KV_MIN_PASSWORD_LENGTH=12
```

For e-post (hvis brukt):
```bash
KV_SMTP_HOST=smtp.mailprovider.com
KV_SMTP_USERNAME=...
KV_SMTP_PASSWORD=...   # APP-PASSORD, ikke hovedkonto
KV_SMTP_FROM=noreply@minfiskerikontroll.no
```

For SMS-OTP:
```bash
KV_SMS_PROVIDER=twilio
KV_TWILIO_ACCOUNT_SID=...
KV_TWILIO_AUTH_TOKEN=...
KV_TWILIO_FROM=+47...
```

---

## Del 6 — Versjon

`1.8.43` → `1.8.44`. Alle `?v=1.8.44`. SW-cache `kv-kontroll-1-8-44-static`.

**Verifisert:**
- 21/21 sikkerhetssjekker passert
- Python, Jinja, JS validert syntaktisk
- Fail-fast guard funksjonell test passert
- Ingen brute referanser til slettede tjenester
