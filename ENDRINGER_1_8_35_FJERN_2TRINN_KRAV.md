# Endringer 1.8.35 — 2-trinns innloggings­krav fjernet

## Hva er endret

Etter ønske er kravet om 2-trinnsinnlogging via SMS fjernet for alle brukere.
Innlogging er nå **e-post + passord — ett steg, alle roller**.

Endringen er **reversibel**: 2FA-infrastruktur (database, ruter, templates,
SMS-tjeneste) er beholdt. Det kan slås på igjen ved å sette miljøvariabelen
`KV_OTP_ENABLED=true` i Render eller `.env`.

---

## 1. Konfigurasjon

`app/config.py`:

```python
# Før:
otp_enabled=_env_flag('KV_OTP_ENABLED', True),

# Nå:
otp_enabled=_env_flag('KV_OTP_ENABLED', False),
```

Når `otp_enabled` er `False`, returnerer `_otp_required_for_user()` alltid
`False`, og innloggings­flyten hopper helt over OTP-steget.

---

## 2. Login-flyt

### Før
1. POST `/login` med e-post + passord
2. Hvis bruker ikke er admin → opprett OTP-challenge → redirect til `/login/2fa`
3. POST `/login/2fa` med 6-sifret kode fra SMS
4. Logg inn

### Nå
1. POST `/login` med e-post + passord
2. Logg inn

---

## 3. Sikkerhets-redirects

Alle tre `/login/2fa`-endepunkter sjekker nå `settings.otp_enabled` først og
redirecter til `/login` hvis det er av:

```python
@router.get('/login/2fa')
def login_2fa_page(request: Request):
    if not settings.otp_enabled:
        return RedirectResponse('/login', ...)
    ...
```

Dette betyr at en gammel cachet `/login/2fa`-URL eller bokmerke alltid
sender brukeren tilbake til riktig sted.

---

## 4. Bruker­opprettelse

| Felt | Før | Nå |
|---|---|---|
| Mobilnummer | Påkrevd for ikke-admin | **Valgfritt for alle** |
| Hint under telefon | «SMS-kode sendes hit ved innlogging.» | «Brukes hvis du sender invitasjon på SMS.» |
| Pille på brukerkort | «2-trinn: SMS» / «2-trinn: unntatt» | Fjernet |
| Rolle-hint | «Etterforsker logger inn med passord + SMS-kode.» | «Etterforsker har tilgang til kontroll, kart og regelverk.» |
| `validate_login_mobile(...)` | `required=(role != 'admin')` | `required=False` |
| `two_factor_required` | `(role != 'admin')` | `False` |
| SMS-invitasjon ved opprettelse | Bare ikke-admin | **Tilgjengelig for alle** |

`KV_TWILIO_*`-variabler trenger ikke lenger å være satt for at brukere
skal kunne logge inn. Twilio-integrasjonen brukes fortsatt for *valgfri*
SMS-invitasjon ved bruker­opprettelse, men siden den er valgfri kan den
være helt utelatt.

---

## 5. Login-side

Fjernet finprint:
> «Ikke-adminbrukere får tilsendt engangskode på SMS som steg 2.»

Login-skjemaet har nå bare e-post + passord + «Logg inn»-knapp.

---

## 6. Filer endret

```
app/config.py                       — otp_enabled default → False
app/routers/auth.py                 — sikkerhets-redirects på alle 3
                                       /login/2fa-endepunkter
app/routers/admin.py                — phone valgfritt, two_factor_required=False,
                                       SMS-invitasjon for alle roller
app/templates/admin_users.html      — fjernet 2-trinn-piller, oppdatert
                                       hint-tekster, telefon merket valgfritt
app/templates/login.html            — fjernet SMS-finprint
app/static/js/admin-users.js        — telefon alltid valgfritt, oppdatert
                                       rolle-hint
app/static/sw.js                    — versjons-bump
```

## 7. Filer bevisst IKKE rørt (reversibelt)

- `app/templates/login_2fa.html` — beholdes for fremtidig bruk
- `app/services/sms_service.py` — beholdes (brukes til invitasjon)
- `app/db.py` — `two_factor_required`-kolonnen beholdes; ingen migrasjon
  trengs. Eksisterende verdier blir bare ignorert av ny login-flyt.
- `app/security.py` — OTP-rate-limiting beholdes for hvis 2FA gjenaktiveres
- DB-tabellen `login_otp_challenges` — beholdes (ubrukt nå, men trygt å ha)

## 8. Slik skrur du på 2FA igjen senere

Sett i Render eller `.env`:
```
KV_OTP_ENABLED=true
KV_SMS_PROVIDER=twilio
KV_TWILIO_ACCOUNT_SID=...
KV_TWILIO_AUTH_TOKEN=...
KV_TWILIO_FROM_NUMBER=+47...
```

Restart applikasjonen. Ikke-adminbrukere får da igjen SMS-kode ved login.

---

## 9. Versjon

`1.8.34` → `1.8.35`. Alle `?v=1.8.35`. SW-cache `kv-kontroll-1-8-35-static`.
