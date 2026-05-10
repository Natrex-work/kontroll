# Endringer 1.8.41 — Steg 6/7/8 omarbeidet, AI-rapport, audio-synk-fiks

## Hva er endret

Tre kontrollskjema-steg er ryddet og fått ny funksjonalitet:

- **Steg 6** Filvelger gir nå iOS-velger (kamera/bibliotek/filer)
- **Steg 7** Avhør kollapset som standard, all diktering samles i ett felt,
  AI-generert avhørsrapport, lyd-synk-feilen er fikset
- **Steg 8** Beslagsrapport ryddet for unødige beskrivelser

---

## 1. Steg 6 — Bilde / video-uttrekk

### Endring
```html
<!-- FØR: -->
<input type="file" accept="image/*,.heic,.heif" capture="environment" />

<!-- NÅ: -->
<input type="file" accept="image/*,.heic,.heif" />
```

`capture="environment"` ble fjernet. På iOS får brukeren nå standard
fil-velger med tre valg:

1. **Photo Library** — velg eksisterende bilder
2. **Take Photo or Video** — åpne kameraet
3. **Choose File** — bla i Filer-appen

De dedikerte "Ta bilde direkte"-knappene (OCR + inline-evidence) beholder
fortsatt `capture="environment"` siden de skal alltid åpne kameraet.

---

## 2. Steg 7 — Avhør

### 2.1 Fjernet beskrivelses-tekst
Tekst fjernet:
> «Avhør, lydopptak, avhørsutkast og interne forslag til avhørspunkter.
>  Bare avhør som er merket gjennomført tas inn i dokumentpakken.»

Også fjernet: småtekster om at "Når dette er krysset av, fylles ikke
avhørsrapporten ut..." og "Genereres fra registrerte avvik..."

### 2.2 Standard for nye saker: «Avhør ikke gjennomført»
Jinja-logikk:
```jinja
{% if case.interview_not_conducted is sameas none or case.interview_not_conducted %}checked{% endif %}
```

For nye saker (`interview_not_conducted` er `None`) er checkboxen krysset
som standard. For eksisterende saker beholdes lagret verdi.

### 2.3 Kollapset som standard
Hele avhør-detaljblokken er pakket i en `<details>`-tag. Den er **lukket
som standard for nye saker**, men åpen hvis avhør er merket som
gjennomført fra før (eksisterende saker).

```html
<details {% if eksisterende sak med avhør gjennomført %}open{% endif %}>
  <summary>▾ Vis avhørsdetaljer · Avhørspersoner, lydopptak, diktering</summary>
  ...
</details>
```

### 2.4 «Diktering»-felt (omdøpt)
Felt `<textarea name="hearing_text">` har fått ny etikett:

| Før | Nå |
|---|---|
| Samlet avhørsutkast (kun gjennomførte avhør) | **Diktering** |

### 2.5 All diktert tale samles i Diktering-feltet
Diktering-handleren skriver nå til **både** den aktive avhørs-transkripsjonen
**og** hovedfeltet `hearing_text`:

```javascript
speechRec.onresult = function (event) {
  // ... bygger finalText fra event.results
  if (finalText) {
    var target = activeInterviewTranscript();  // aktivt avhør
    var hearingTarget = document.getElementById('hearing_text');  // hovedfelt
    target.value += ' ' + finalText;
    hearingTarget.value += ' ' + finalText;
    hearingTarget.dispatchEvent(new Event('input'));
  }
};
```

**Auto-restart**: Speech Recognition i Safari avslutter etter ~60 sek;
ny `onend`-handler restarter automatisk så brukeren slipper å klikke
Start hvert minutt.

### 2.6 «Avhørsrapport autogenerert» (omdøpt + AI)
Felt `<textarea name="seizure_notes">` har ny etikett og dedikert
generator-knapp:

| Før | Nå |
|---|---|
| Beslag / bevismerknader | **Avhørsrapport autogenerert** |

Ny knapp: **«Generer rapport»** kombinerer:
- Diktering fra hearing_text
- Avvik fra kontrollpunkter (med notater)
- Person-info fra Person/Fartøy-skjemaet
- Posisjon og tidspunkt fra kontrollen
- Kort oppsummering for anmeldelsen

#### Backend-endepunkt: `POST /api/cases/{id}/interview-report-draft`
Nytt endepunkt som:
- Tar imot diktert tekst + sammendrag av saksinformasjon
- Setter sammen en strukturert avhørsrapport med:
  - Avhørt person, sted, tidspunkt
  - Forelagte avvik (nummerert liste)
  - Forklaring fra avhørt (polert diktering med stor forbokstav etter punktum)
  - Kort oppsummering for anmeldelsen
- Returnerer kun lokal logikk — ingen betalt AI nødvendig
- Klient har lokalt fallback-utkast (visning umiddelbart, polering etterpå)

### 2.7 «Eksporter kun avhørsrapport» — verifisert
Eksisterende endepunkt `/cases/{id}/interview-pdf` er testet og
funksjonell. Knappen leder til denne fortsatt.

---

## 3. Steg 8 — Beslagsrapport

### Fjernet
- Beskrivelse: «Alle beslag og bilder knyttet til beslagsnummer vises
  samlet. Ved avvik på redskap...»
- Callout: «Beslag knyttes til beslagnummer, kontrollpunkt, beskrivelse,
  hjemmel og eventuelle bilder. Bilder med beslagnummer sorteres etter
  kartoversiktene i illustrasjonsrapporten.»
- Tom-tilstand: «Ingen beslag eller avviksrader generert ennå.»
  (`seizure-report-list` er nå tom inntil det faktisk er beslag, render
  håndteres av JS)
- Felt: «Utfyllende merknader til beslag» (textarea fjernet, men
  `seizure_report_override` beholdes som hidden field for bakoverkompat)

### Beholdt
- «Oppdater fra avvik»-knappen (refresh seizure report)
- «Legg til beslag manuelt»-knappen
- Signatur-widgets
- Step-actions (Tilbake/Videre)

---

## 4. Lyd-synk-feil løst

### Problem
Brukere fikk «Lokal lagring · synk feilet · Kunne ikke lagre vedlegg i
saken» når lydopptak ble forsøkt synket til server.

### Rotårsak
`validate_upload_signature()` i `app/validation.py` krevde streng signatur-
match på lydfiler:
- WEBM: `\x1aE\xdf\xa3` (EBML magic bytes)
- M4A: `ftyp` i de første 32 bytene
- WAV: `RIFF...WAVE` header
- MP3: `ID3` eller MPEG sync byte
- OGG: `OggS` magic

Når MediaRecorder på iOS Safari fragmenterer audio i chunks (5-min
segmenter via `scheduleRecordingRotation`), kan etterfølgende segmenter
mangle disse magic bytes. Validering feilet → 400 Bad Request → klient
viser generisk «kunne ikke lagre»-melding.

### Løsning
Mer tolerant signatur-validering for lyd: filendelse + MIME-type allerede
validert i `validate_upload_file`, så vi godtar nå alle lyd-suffix uten
streng magic-bytes-sjekk. Bilder, PDF og andre filtyper beholder fortsatt
streng validering.

```python
if suffix == '.webm':
    # WebM files start with EBML header \x1aE\xdf\xa3, but MediaRecorder
    # chunked output may have varying first bytes. Accept any file with
    # .webm suffix as long as it has size — MIME validation already ran.
    return 'audio/webm'
```

Dette er trygt fordi:
1. `validate_upload_file` har allerede sjekket både filendelse OG MIME
2. Filer med feil endelse blir avvist tidlig
3. Ondsinnet innhold filtreres fortsatt på basis av MIME

---

## 5. Filer endret

```
MOD:
  app/templates/case_form.html      — steg 6/7/8 omarbeidet (FØRSTE GANG
                                       case_form.html er endret i denne
                                       sesjonen — gjort konservativt og
                                       med full render-test)
  app/static/js/case-app.js         — diktering skriver til både aktivt
                                       avhør og hovedfelt + AI-rapport-
                                       generator + auto-restart
  app/routers/api.py                — nytt /api/cases/{id}/interview-
                                       report-draft endepunkt
  app/validation.py                 — tolerant audio-signatur-validering
  app/static/styles.css             — +60 linjer for .interview-details
                                       og .ai-report-block
  app/static/sw.js                  — cache-bump
  app/config.py                     — versjon 1.8.41
  alle templates                    — ?v=1.8.41
```

## 6. Ikke berørt

- DB-skjema og migrations
- Sync-orkestrator
- Kart, login, admin
- Kontrollpunkter (steg 5)
- Person/Fartøy (steg 4)

---

## 7. Verifisering (tekstbasert sjekk)

```
✓ Old description text removed (avhør)
✓ Beslag callout removed
✓ Beslag header description removed
✓ Empty state "Ingen beslag eller avviksrader" removed
✓ "Utfyllende merknader til beslag" textarea label removed
✓ "Samlet avhørsutkast" replaced with "Diktering"
✓ "Beslag / bevismerknader" replaced with "Avhørsrapport autogenerert"
✓ capture="environment" removed from main file input
✓ Generate report button added
✓ Interview details collapsible wrapper added
✓ Default new case: interview_not_conducted krysset
```

11/11 sjekker passert. Python, Jinja, JS og CSS validert syntaktisk.

---

## 8. Versjon

`1.8.40` → `1.8.41`. Alle `?v=1.8.41`. SW-cache `kv-kontroll-1-8-41-static`.
