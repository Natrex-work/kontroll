# Endringer 1.8.29 — Mobilnummer-innlogging med engangskode (OTP/2FA)

## Oversikt

Denne versjonen innfører sikker innlogging via mobilnummer og SMS-engangskode
som alternativ til e-post og passord. Begge metoder er tilgjengelige parallelt
og kan brukes om hverandre avhengig av hva den enkelte bruker foretrekker.

---

## 1. Ny innloggingsflyt: mobilnummer + SMS-kode

### Brukerflyt (to steg)

**Steg 1 — Mobilnummer**
1. Bruker åpner `/login` og velger fanen «Mobilnummer», *eller* går direkte
   til `/login/telefon`.
2. Bruker skriver inn norsk mobilnummer (8 siffer, starter med 4 eller 9).
3. Systemet normaliserer nummeret til E.164-format (+47XXXXXXXX) og slår opp
   en aktiv bruker med dette nummeret i databasen.
4. Hvis nummeret finnes: genererer og sender en 6-sifret engangskode via SMS.
5. Bruker videresendes til `/login/kode`.

**Steg 2 — Engangskode**
1. Bruker skriver inn 6-sifret kode fra SMS.
2. Skjemaet sendes automatisk når 6 siffer er fylt inn (JavaScript-assistert).
3. Koden verifiseres mot lagret hash; ved suksess opprettes en autentisert
   sesjon og bruker videresendes til sin landingsside.

### Sikkerhetsegenskaper

| Egenskap | Verdi |
|---|---|
| Kodelengde | 6 siffer |
| Kodeformat | Kryptografisk tilfeldig (secrets.randbelow) |
| Kodens levetid | 5 minutter |
| Maks feilforsøk | 5 per OTP-sesjon |
| Rate limiting | Maks 3 kodeforespørsler per nummer per 15 min |
| Lagringsformat | HMAC-SHA256 hash (ikke klartekst) |
| Timing-sikkerhet | Ukjente numre behandles identisk (ingen lekking) |
| CSRF | Alle POST-endepunkter krever gyldig CSRF-token |
| Sesjonstoken | Opaque UUID i server-session (ikke URL-parameter) |
| Audit | Alle innlogginger logges med metode og maskert nummer |

### Nye filer

- `app/services/sms_service.py` — OTP-generering, hashing, rate limiting og
  SMS-utsending via Twilio eller dev-modus (stdout-logging).
- `app/templates/login_phone.html` — Steg 1: mobilnummerside.
- `app/templates/login_otp.html` — Steg 2: kodebekreftelsesside.

### Endrede filer

- `app/routers/auth.py` — Lagt til fire nye endepunkter:
  - `GET /login/telefon`
  - `POST /login/telefon`
  - `GET /login/kode`
  - `POST /login/kode`
- `app/db.py` — Ny tabell `otp_sessions` med indekser, og funksjonene:
  - `create_otp_session()`
  - `get_otp_session()`
  - `increment_otp_attempts()`
  - `mark_otp_used()`
  - `purge_expired_otp_sessions()`
  - `get_user_by_phone()`
- `app/templates/login.html` — Redesignet med faner (Mobilnummer / E-post),
  slik at begge innloggingsmetoder er tilgjengelige fra én side.
- `app/static/styles.css` — Nye CSS-klasser for faner, telefoninput med
  landekode, steg-indikator og stor OTP-input.
- `.env.example` — Lagt til SMS-konfigurasjon (`KV_SMS_PROVIDER`,
  `KV_TWILIO_ACCOUNT_SID`, `KV_TWILIO_AUTH_TOKEN`, `KV_TWILIO_FROM_NUMBER`).
- `requirements.txt` — Kommentert inn `twilio`-pakken (valgfri avhengighet).

---

## 2. SMS-provider og konfigurasjon

### Dev-modus (standard)

Uten `KV_SMS_PROVIDER`-variabel skrives engangskoden til stdout:

```
============================================================
OTP DEV MODE — kode til +4799887766: 482951
============================================================
```

### Produksjon med Twilio

Sett følgende i `.env` eller Render-miljøvariabler:

```
KV_SMS_PROVIDER=twilio
KV_TWILIO_ACCOUNT_SID=ACxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
KV_TWILIO_AUTH_TOKEN=xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
KV_TWILIO_FROM_NUMBER=+4712345678
```

Installer Twilio-pakken:

```
pip install twilio==9.4.0
```

### Andre providere (fremtidig)

`sms_service.py` er bygget for enkel utvidelse. Legg til en ny `_send_X()`
funksjon og håndter `KV_SMS_PROVIDER=X` i `send_otp_sms()`.

---

## 3. Forutsetninger for mobilnummer-innlogging

For at en bruker skal kunne logge inn med mobilnummer, må:

1. Et norsk mobilnummer (8 siffer, starter med 4 eller 9) være lagret i
   brukerens profil i admin-panelet (`/admin/brukere`).
2. Nummeret kan lagres med eller uten landskode (+47), med eller uten
   mellomrom. Systemet normaliserer og matcher fleksibelt.

---

## 4. Database-migrasjon

`otp_sessions`-tabellen opprettes automatisk ved oppstart via `init_db()`.
Ingen manuell migrasjon kreves. Eksisterende databaser oppgraderes
automatisk.

---

## 5. Versjonsheving

- `app/config.py`: `1.8.28` → `1.8.29`
- `app/static/sw.js`: cache-navn og statiske filer oppdatert
- `app/templates/base.html`: `?v=`-parametere oppdatert
- `app/templates/login.html`, `login_phone.html`, `login_otp.html`: `?v=1.8.29`

---

## 6. Manuelle tilpasninger som kan ønskes

- **PWA «Husk enhet»**: Dersom man ønsker at innloggede enheter huskes i
  lengre tid, kan `session_max_age_seconds` økes (allerede mulig via
  `KV_SESSION_MAX_AGE_SECONDS`).
- **Twilio Verify**: For høyere volum eller internasjonal SMS kan Twilio
  Verify-tjenesten brukes i stedet for vanlig SMS. Krever utvidelse av
  `sms_service.py`.
- **MessageBird / Telenor**: Legg til provider-spesifikk funksjon i
  `sms_service.py` og sett `KV_SMS_PROVIDER=messagebird` eller lignende.
