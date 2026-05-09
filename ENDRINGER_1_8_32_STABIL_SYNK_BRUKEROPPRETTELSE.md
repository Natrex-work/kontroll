# Endringer 1.8.32 — Stabil bildesynk + forenklet brukeropprettelse

## Mål
1. **Stabilitet** — bilder og lyd skal alltid lagres lokalt og synkes til server, også når nettverket er ustabilt eller appen kun er åpen kort tid.
2. **Brukerstyring** — admin skal raskt og uten friksjon kunne opprette nye brukere fra mobil eller iPad.

Backend, kontrollskjema (`case_form.html`), case-app.js og kjernemodellen er
ikke endret. All ny logikk er lagt til som separate filer og additive lag.

---

## 1. Bakgrunns-synkorkestrator (`sync-orchestrator.js`)

### Hva den gjør
En ny, lettvekts JS-modul som lastes på alle innloggede sider. Den jobber
parallelt med, og overlapper ikke, eksisterende synklogikk i `case-app.js`.

| Funksjon | Detalj |
|---|---|
| **Persistent storage** | Kaller `navigator.storage.persist()` ved oppstart slik at iOS/Safari ikke evicter IndexedDB ved minnetrang. |
| **Globalt skann** | Scanner alle saker (ikke bare den som er åpen) for ventende eller failed media. |
| **Auto-retry** | Failed uploads får eksponentiell backoff: 30s → 1m → 2m → 4m → 8m → 10m (kappet). |
| **Online-event** | Lytter på `online` og kjører synk 1.5 sek etter at nettverket er gjenopprettet. |
| **Visibility-event** | Synker når brukeren bytter tilbake til appen etter ≥30 sek pause. |
| **Polling** | Sjekker hver 60. sekund. |
| **Stale uploads** | "Uploading"-tilstand som er over 2 minutter gammel regnes som stale og prøves på nytt (forhindrer hengende state). |
| **Sekvensiell upload** | Ett bilde om gangen — unngår å hamre serveren over mobilnett. |
| **Offline-aware** | Når `navigator.onLine === false` står koden stille, men oppdaterer fremdeles badgen. |

### Globalt synk-badge i toppbaren
Et nytt knappebadge i topbaren viser status for alle vedlegg:

| Tilstand | Visning |
|---|---|
| Alt synket | Cyan «Synket» m. cyan-ikon |
| Pending uploads | Blå «Synker …» m. spinning ikon + antall |
| Failed (ingen pending) | Rød «Synk feilet» m. antall + klikk for å prøve igjen |

På små skjermer (iPhone) skjules teksten og kun ikon + tall vises, slik at
badgen ikke spiser plass i topbaren.

Klikk på badgen tilbakestiller backoff og forsøker alle failed uploads igjen.

### Filendringer
- **NY:** `app/static/js/sync-orchestrator.js` (270 linjer)
- **MOD:** `app/templates/base.html` — synk-badge i `topbar-actions`, ny script-referanse
- **MOD:** `app/static/sw.js` — synk-orkestrator pre-cached
- **MOD:** `app/static/styles.css` — `.mk-sync-badge` med tilstandene

### Fortsatt riktig
- Eksisterende synk-logikk i `case-app.js` er uendret. Når brukeren er inne
  i et saksskjema, fortsetter `btn-sync-local-media` å funke som før — den
  håndterer den aktive saken. Orkestratoren er en superset som dekker alle
  saker og alle sider.
- Retry-safety mot duplikater er bevart (server identifiserer eksisterende
  evidence-rad via `local_media_id`).

---

## 2. Forenklet brukeropprettelse for admin

### Tidligere problem
Skjemaet hadde 9+ felt synlig samtidig, ingen passordhjelp, små klikkmål
på iPhone, og ingen tydelig bekreftelse på hva som skulle deles med
ny bruker.

### Ny UX
**Hurtigopprettelse**:
- 4 felt synlig: navn, e-post, mobilnummer (med 🇳🇴 +47-prefix), passord
- Rolle som **segmentert kontroll** (Etterforsker / Admin) i stedet for select
- «Generer sterkt» — knapp som lager 16-tegns kryptografisk passord og
  automatisk kopierer det til utklippstavlen
- Vis/skjul-knapp på passordfeltet (øye-ikon)
- Kopier-passord-knapp ved siden av
- Telefon-kravet skifter automatisk basert på valgt rolle (admin = valgfritt)
- Tilgangsmoduler vises kun for ikke-admin (admin får full tilgang automatisk)
- Visuell highlight på checked permissions (border + lys blå bakgrunn)

**Avansert (kollapset)**:
- Adresse, fartøystilhørighet, saksprefix, anmelder, vitne — alle merket
  som «valgfritt» og pakket i en `<details>`-blokk

**Suksess-modal**:
Etter opprettelse vises en sentrert modal med:
- Grønt sjekkmerke
- E-post og telefon med kopier-knapper
- Tydelig forklaring om at passordet ikke vises i etterkant og at
  «Nullstill passord» kan brukes hvis admin har glemt det

**Eksisterende brukere**:
- Hver bruker er en kollapsbar boks. Hovedinformasjon (navn, e-post,
  telefon, rolle, status, 2-trinn) vises i kortheader.
- «Rediger bruker» er en `<details>`-toggle. Skjemaet er ellers identisk
  og bevarer all eksisterende funksjonalitet.

### Filendringer
- **OMSKREVET:** `app/templates/admin_users.html` (mer kompakt og lesbar)
- **OMSKREVET:** `app/static/js/admin-users.js` (passord-helpers, segmentert kontroll, toast)
- **MOD:** `app/routers/admin.py` — redirect inkluderer e-post/telefon for modal-visning
- **MOD:** `app/static/styles.css` — full styling for nytt admin-skjema

### Bevart
- Eksisterende endpoints `/admin/users`, `/admin/users/{id}/update`,
  `/admin/users/{id}/reset-password`, `/admin/users/{id}/remove` er
  uendret. Alle eksisterende formfelt sendes videre.
- Validering i backend (`validate_login_mobile`, `validate_password`,
  `validate_role`, etc.) er uendret.
- 2-trinns SMS-flyten (`/login/2fa`) er uendret.

---

## 3. Småforbedringer

- **Toast-system** lagt til (`.mk-toast-host`, `.mk-toast`) som brukes av
  passordgeneratoren («Passord generert og kopiert»). Lett å gjenbruke.
- **Confirm-dialog** for «Fjern bruker»-knappen flyttet fra inline
  `data-confirm` (uten håndtering) til en faktisk `confirm()`-prompt i JS.

---

## 4. Versjon

- `app/config.py`: `1.8.31` → `1.8.32`
- `app/static/sw.js`: cache-navn `kv-kontroll-1-8-32-static` + alle assets
- Alle templates, JS-filer: `?v=1.8.32`

---

## 5. Filer endret

```
NY:
  app/static/js/sync-orchestrator.js        (270 linjer)

OMSKREVET:
  app/templates/admin_users.html            (208 linjer, før: 184)
  app/static/js/admin-users.js              (296 linjer, før: 49)

MOD:
  app/templates/base.html                   (synk-badge i topbar)
  app/routers/admin.py                      (redirect inkluderer email/phone)
  app/static/sw.js                          (cache-navn + ny asset)
  app/static/styles.css                     (+524 linjer for synk-badge,
                                              admin-skjema, toast, modal)
  app/config.py                             (versjon 1.8.32)

VERSJONS-BUMP:
  Alle templates med v=-parametre
```

## 6. Filer bevisst IKKE endret

- `app/static/js/case-app.js` (kjøreklart, ingen endringer i kjernelogikk)
- `app/templates/case_form.html` (kontrollskjemaet — komplekst, eget steg-system)
- `app/services/case_service.py` (`store_evidence_upload` håndterer allerede idempotens via `local_media_id`)
- `app/routers/cases.py` (evidence-upload-endepunktene er allerede idempotente og fortsetter å virke)
- `app/db.py` (ingen schema-endring nødvendig)
- All Python utenfor `app/routers/admin.py` (validering, OTP, SMS, sesjon,
  CSRF — uendret)

Hele endringen kan rulles tilbake ved å fjerne `sync-orchestrator.js`,
synk-badgen i `base.html`, og det avsluttende «1.8.32»-blokken i
`styles.css`. Admin-skjemaet kan settes tilbake ved å gjenopprette
forrige versjon av `admin_users.html` og `admin-users.js`.
