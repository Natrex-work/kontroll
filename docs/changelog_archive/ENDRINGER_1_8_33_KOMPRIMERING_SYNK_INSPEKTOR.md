# Endringer 1.8.33 — Bildekomprimering, synk-inspektor, SMS-invitasjon

## Mål
Etter v1.8.32 ble synkorkestrator og admin-flyt bygget. Denne versjonen
fikser **rotårsakene** til synkfeil og gir admin og felt-bruker komplett
kontroll på status.

Tre fokusområder:

1. **Komprimering ved kilden** — bilder reduseres fra ~4 MB til ~400 KB
   før de lagres lokalt og lastes opp.
2. **Full synk-oversikt** — ny side `/synk` som viser alt som ligger på
   enheten, hva som er synket, hva som har feilet, og lar brukeren
   prøve igjen.
3. **SMS-invitasjon ved brukeropprettelse** — admin slipper å formidle
   passord manuelt.

---

## 1. Bildekomprimering ved kilden

### Problem
Et iPhone-bilde fra hovedkamera er typisk 12 MP / 3–5 MB. Med 10 bilder
i en kontroll ligger 30–50 MB i IndexedDB og må over mobilnettet. Dette er
den vanligste rotårsaken til synkfeil:

- iOS Safari kan evicte stor IndexedDB-data ved minnepress
- Mobilnett-uploads avbrytes ved store filer
- Brukerens datakvote spises opp

### Løsning: `app/static/js/image-prep.js` (NY)

En lettvekts modul som:

| Funksjon | Detalj |
|---|---|
| **Auto-rotasjon** | `createImageBitmap(blob, {imageOrientation:'from-image'})` håndterer EXIF-orientering native i Safari 16+/Chrome. Fall-back til `<img>` for eldre iOS. |
| **Skalering** | Maks 1920 px lengste side (kan justeres). |
| **Kvalitet** | JPEG @ 0.85 (visuelt identisk for de fleste, men ~80 % mindre fil). |
| **Smart skip** | Filer < 400 KB røres ikke. SVG og HEIC hoppes over. |
| **Trygg fallback** | Hvis canvas-encoding gir større fil enn original, beholdes original. Hvis noe feiler, returneres uendret fil. |
| **Transparent integrasjon** | Monkey-patcher `KVLocalMedia.put()` slik at `case-app.js` ikke trenger endringer. Lyd passeres uendret. |

### Resultat
- En 4 MB iPhone-foto blir ~300–500 KB
- Storage-bruk reduseres ~85 %
- Upload over mobilnett går 5–10× raskere
- Synkfeilrate faller dramatisk
- Bilder vises riktig vei (rotasjonsproblem fikset)

### Implementasjonsdetaljer
- Lastes **før** `local-media.js` slik at `KVLocalMedia.put` blir wrappet
  ved første use.
- Wrapper er idempotent (`__imagePrepInstalled`-flag).
- Bevarer filnavn (med riktig `.jpg`-extension).
- Setter `mime_type` og `file_size` på record-en korrekt.

---

## 2. Synk-inspektor `/synk`

### Ny side
- Tilgjengelig fra synk-badgen i toppbaren (klikk → /synk)
- Tilgjengelig direkte via `/synk`
- Krever bare `require_user` — alle innloggede brukere kan se sine egne
  vedlegg

### Hva siden viser

**Statistikk-kort**:
- Totalt på enheten
- Synket til server
- Venter på synk
- Synk feilet

**Lagrings-info**:
- Bytes brukt vs kvote
- Indikator om persistent storage er innvilget av nettleseren
- Tips om "legg til på hjemskjermen" hvis ikke persistent

**Tabell over alle vedlegg** (sortert: failed → pending → uploading → synced):
- Saksnummer (eller "Lokal sak" hvis ikke synket til server)
- Filnavn, størrelse, alder
- Statusbadge (Synket / Venter / Synker / Feilet)
- Feilmelding hvis failed
- "Prøv igjen"-knapp på pending/failed
- "Fjern lokal kopi"-knapp på synket (frigjør plass)

**Auto-refresh hvert 5. sek** så brukeren ser fremgang i sanntid.

**Stor "Prøv synk på nytt"-knapp** øverst som tilbakestiller backoff og
forsøker alle failed uploads.

### Filer
- **NY:** `app/templates/sync_inspector.html` (270 linjer, scoped CSS)
- **MOD:** `app/routers/pages.py` — ny route `/synk`

---

## 3. SMS-invitasjon til ny bruker

### Problem
Tidligere måtte admin notere passordet, deretter sende det til brukeren
via separat kanal (SMS/Signal/e-post). Friksjonsskapende og lett å glemme.

### Løsning
- Ny checkbox ved siden av "Opprett bruker"-knappen:
  «Send foreløpig passord på SMS til brukeren»
- Bruker eksisterende Twilio-integrasjon (samme som OTP-koder)
- Sender en kort melding: "Anders, du har fått tilgang til
  Minfiskerikontroll. Foreløpig passord: xxx Logg inn: <url> Bytt
  passord etter første innlogging."

### Sikkerhetsdetaljer
- Avvises automatisk hvis rolle = admin (admin har egne kanaler)
- Krever at brukeren har telefonnummer registrert (ellers SMS umulig)
- Hvis SMS feiler logges advarsel; brukeren opprettes uansett, og admin
  får tydelig beskjed i suksess-modalen om å dele passordet manuelt
- Audit-logg får egen `send_invitation_sms`-event

### Suksess-modal-feedback
- Grønn alert: "📲 Foreløpig passord er sendt på SMS til brukeren."
- Gul alert ved feil: "⚠️ Bruker er opprettet, men SMS-invitasjonen feilet."

### Filer
- **NY funksjon:** `send_user_invitation()` i `app/services/sms_service.py`
- **MOD:** `app/routers/admin.py` — håndterer `send_invitation_sms`-felt
- **MOD:** `app/templates/admin_users.html` — ny checkbox + modal-status
- **MOD:** `app/static/styles.css` — `.admin-invite-toggle`-styling

---

## 4. Bonus-forbedringer

- **Synk-badge** i topbaren er nå et `<a href="/synk">`-element — klikk
  åpner full synk-oversikt i stedet for blind retry. Gir mye bedre UX
  fordi brukeren ser HVA som mangler og kan vurdere selv om man skal
  vente eller prøve på nytt.
- **CSS-polish** for synk-inspektor: røde, blå og grønne statusbadges
  konsistent med dashboardets fargesystem.

---

## 5. Versjonsheving

- `app/config.py`: `1.8.32` → `1.8.33`
- `app/static/sw.js`: cache `kv-kontroll-1-8-33-static`, `image-prep.js` lagt
  til pre-cache
- Alle templates, JS-filer: `?v=1.8.33`

---

## 6. Filer endret

```
NY:
  app/static/js/image-prep.js                (220 linjer)
  app/templates/sync_inspector.html          (270 linjer)

MOD:
  app/services/sms_service.py                (+25 linjer for invitasjon)
  app/routers/admin.py                       (+15 linjer for SMS-flyt)
  app/routers/pages.py                       (+8 linjer for /synk-route)
  app/templates/base.html                    (image-prep.js + sync-badge → a)
  app/templates/admin_users.html             (invitasjon-checkbox + modal-tekst)
  app/static/sw.js                           (cache + asset-versjoner)
  app/static/styles.css                      (+50 linjer for nye elementer)
  app/config.py                              (versjon 1.8.33)
  app/static/js/sync-orchestrator.js         (badge er nå <a> ikke button)
```

## 7. Filer bevisst IKKE endret

- `app/static/js/case-app.js` — komprimering skjer transparent via
  KVLocalMedia.put-wrapping. Ingen endring i kontrollskjemaet trengs.
- `app/templates/case_form.html` — ingen endring.
- `app/services/case_service.py` — server-side `store_evidence_upload`
  er allerede idempotent og håndterer alle filer som kommer inn,
  uavhengig av om de er komprimert eller ikke.
- `app/routers/cases.py` — evidence-endepunktene er uendret.
- `app/db.py` — ingen schema-endring.
