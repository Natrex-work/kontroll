# Endringer 1.8.36 — Nytt kart-design og profesjonelle login-feil

## Hva er endret

To områder er omarbeidet:

1. **Kart-siden** (`/kart`) — full-bleed Apple Maps-stil med levende
   posisjons­markør, flytende kontroll-knapper, og bunn-panel som glir
   opp med treff og innstillinger. Optimalisert for iPhone og iPad.

2. **Login-feilmeldinger** — distinkte titler + beskrivelse + ikon i
   profesjonelt format som tydelig forteller hva som er galt.

---

## 1. Nytt kart-design

### Layout-prinsipp
Kart-siden har nå en **full-bleed-arkitektur** der kartet eier hele den
synlige skjermen. Ingen iframe, ingen tett pakkede paneler — kartet er
hovedinnholdet og alt annet legger seg over som overlays.

```
┌─────────────────────────────────┐
│ Kart og områder    [Portal ↗]   │ ← Slank header (12-16px padding)
├─────────────────────────────────┤
│                            [📍] │
│                            [🗺] │ ← Flytende FAB-knapper
│      [Kart med blå dot]    [⬇] │
│                                 │
│                                 │
│  ─── handle ───                 │
│  3 områder i nærheten      ▲    │ ← Bunn-panel (glir opp)
└─────────────────────────────────┘
```

### Nøkkelfunksjoner

**Live posisjons­markør (Apple Maps-stil)**
- Blå punkt (16 × 16 px) med 3 px hvit ring og myk skygge
- Pulserende ring rundt (2.4s loop) som visuelt indikerer "live"
- Respekterer `prefers-reduced-motion` (pulse skrus av)

**Flytende kontroll-knapper (FABs)**
- Tre runde knapper øverst til høyre, 48 × 48 px (44 × 44 på iPhone)
- 📍 **Bruk min posisjon** — sentrerer på enheten og kjører punktsjekk
- 🗺 **Kartlag** — åpner bunn-panelet og scroller til kartlag-seksjonen
- ⬇ **Lagre offline** — laster ned reguleringer for offline bruk
- Hver knapp har semi-transparent hvit bakgrunn med skygge,
  tap-animasjon (`scale(0.94)`)
- Respekterer `safe-area-inset-top/right` på iPhone

**Bunn-panel som glir opp**
- I kollaps-tilstand: viser kun en kompakt "summary"-linje med antall
  treff og en grip-indikator
- Klikk for å ekspandere: paneler glir opp og avdekker:
  - Status-melding (auto-oppdatert fra map-overview.js)
  - Aktuelle reguleringsområder (treff)
  - Kartlag-velger
  - Lagrede offline-pakker
- Ekspandert kan dekke 70 % av skjermen på iPhone, 60 % på iPad
- Animert med `cubic-bezier(0.32, 0.72, 0, 1)` (Apple-stil ease)
- Når summary-teksten endres, oppdaterer den seg automatisk via
  `MutationObserver`

**iPhone/iPad-tilpasning**
- Body får `overflow: hidden` på kart-siden så hele skjermen er kart
- Toppbar-padding støtter `env(safe-area-inset-top)`
- Bunn-panel har `padding-bottom: env(safe-area-inset-bottom)` så det
  ikke er under hjem-indikatoren på nyere iPhones
- Touch-targets er minst 44 × 44 px
- Landskaps-modus får mer plass til bunn-panel (90 %)

**Iframe fjernet**
Den gamle iframe-baserte kartportalen var awkward på mobil (kunne ikke
zoomes pålitelig, hadde sin egen UI). Erstattet med en lenke til portal
i ny fane (Portal-knapp i header).

### Filendringer
- **OMSKREVET:** `app/templates/map_overview.html` — ny full-bleed layout
- **MOD:** `app/static/styles.css` — +260 linjer for ny map-CSS
- **UENDRET:** `app/static/js/map-overview.js` — fungerer med samme
  element-IDs, ingen JS-endringer trengs

---

## 2. Profesjonelle login-feilmeldinger

### Visuell oppgradering
Feilboks går fra:
```
[i] Innloggingen mislyktes. Kontroller at...
```
til:
```
┌──────────────────────────────────────────┐
│ [⚠]  Feil e-postadresse eller passord    │
│      Kontroller at du har skrevet riktig │
│      e-postadresse og passord, og prøv   │
│      igjen.                              │
└──────────────────────────────────────────┘
```

- Rødt rundt ikon i sirkel (28 × 28 px)
- Tittel i bold, mørk rødtone
- Beskrivelse i lyse rødtone, mer detaljert tekst
- Subtil rødfarget bakgrunn med kant
- 3 px venstre-aksent
- Liten rist-animasjon (360 ms shake) for å trekke oppmerksomhet
- Respekterer `prefers-reduced-motion`

### Distinkte tittel-meldinger

| Situasjon | Tittel | Beskrivelse |
|---|---|---|
| Feil e-post/passord | **Feil e-postadresse eller passord** | Kontroller at du har skrevet riktig e-postadresse og passord, og prøv igjen. |
| Konto deaktivert | **Kontoen er deaktivert** | Tilgangen til denne kontoen er midlertidig sperret. Kontakt administrator for å få den gjenåpnet. |
| Ingen tilganger | **Ingen tilganger tildelt** | Brukerkontoen din er aktiv, men har ingen moduler tildelt. Kontakt administrator. |
| Rate-limit | **For mange forsøk** | Av sikkerhetshensyn er innlogging midlertidig sperret. Vent noen minutter før du prøver igjen. |
| CSRF mislyktes | **Sikkerhetssjekk mislyktes** | Last siden på nytt og prøv å logge inn igjen. |

### Sikkerhetsprinsipp bevart
Vi avslører fortsatt **ikke** om e-posten finnes eller om det var passordet
som var feil. Tittelen «Feil e-postadresse eller passord» er bevisst
flertydig — angripere kan ikke bruke denne meldingen til å enumerere
brukerkontoer.

### Bevart e-post ved feil
`email_value` sendes med i alle feilrespons så brukeren slipper å skrive
e-posten på nytt etter feil passord.

### Filendringer
- **MOD:** `app/templates/login.html` — ny `.login-alert-pro`-struktur
- **MOD:** `app/routers/auth.py` — distinkte titler og beskrivelser
- **MOD:** `app/static/styles.css` — `.login-alert-pro`, `.login-alert-icon`,
  `.login-alert-title`, `.login-alert-msg` + shake-animasjon

---

## 3. Versjon

`1.8.35` → `1.8.36`. Alle `?v=1.8.36`. SW-cache `kv-kontroll-1-8-36-static`.

---

## 4. Filer endret

```
NY/OMSKREVET:
  app/templates/map_overview.html      — full-bleed kart-layout
  app/templates/login.html             — ny profesjonell feilboks-struktur

MOD:
  app/routers/auth.py                  — distinkte feiltitler
  app/static/styles.css                — +320 linjer (kart + login-alert)
  app/static/sw.js                     — versjons-bump
  app/config.py                        — versjon 1.8.36
  alle templates                       — ?v=1.8.36
```

## 5. Ikke berørt

- `app/static/js/map-overview.js` — eksisterende JS fungerer uendret
  fordi alle element-IDs er bevart (`overview-map`,
  `overview-relevant-areas-list`, `overview-map-status`,
  `btn-overview-location`, etc.)
- `app/static/js/case-app.js`, `case_form.html` — ikke berørt
- All Python utenom `app/routers/auth.py`
- DB-skjema, OTP-flyt, sync-orkestrator
