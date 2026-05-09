# Endringer 1.8.39 — Kollapsbare kontrollpunkter + lenke kun for teine + ytelse

## Hva er endret

Kontrollpunkter-seksjonen er totalrenovert:

1. **Lenke-funksjonen** (start/sluttposisjon-toggle) vises nå **kun for
   teine-relaterte kontrollpunkter**. For garn, line, ruse og andre
   redskap er den skjult.

2. **Alle kontrollpunkter kollapses som standard** — kun overskriften vises.
   Trykk på overskriften for å ekspandere og se status, notater, målinger
   og beslag.

3. **Avvik er alltid ekspandert automatisk** — enten det er manuelt valgt
   eller satt automatisk av systemet (auto_note). Når status endres til
   "avvik" ekspanderes kortet umiddelbart, og kollapses ved "godkjent" eller
   "ikke relevant".

4. **Ytelse og stabilitet** — render-debouncing via requestAnimationFrame,
   scoped DOM-queries, CSS containment.

---

## 1. Lenke-funksjon kun for teine

### Problem
Tidligere viste alle vak_merking- og hummer_merking-kontrollpunkter en
"Redskapet er lenke / har start- og sluttposisjon"-checkbox. Dette var
forvirrende for garn-kontroller (der start/slutt alltid er aktuelt) og
overflødig for line, ruse, jukse osv.

### Løsning
Ny helper `itemSupportsLinkToggle(item)` sjekker om kontrollpunktet er
teine-relatert basert på:
- Item-key (`hummer_*`, `*teine*`, `*samleteine*`, `*sanketeine*`)
- ELLER global gear-context (gear-type select inneholder "teine")

Når sjekken returnerer `false`:
- **Lenke-checkbox skjules**
- **Start/slutt-felt skjules**
- `pos.is_linked` tvinges til `false` så lagret tilstand ikke kommer i
  konflikt

Etiketter er også oppdatert: «Teinelenke (start- og sluttposisjon)» i
stedet for det generiske «Redskapet er lenke / har start- og
sluttposisjon». Tydeligere intensjon.

### Filer
- `app/static/js/case-app.js`:
  - `itemSupportsLinkToggle()` (NY)
  - `_gearContextString()` og `_itemIsTeineRelated()` (NY)
  - `markerSectionHtml()` bruker `showLinkToggle`-flagg

---

## 2. Kollapsbare kontrollpunkter

### Layout
Hver finding-card har nå to tilstander:

**Kollapset** (standard):
```
┌─────────────────────────────────────────────────┐
│ ⚠ Hummerteine — Manglende merking      [⚠ Avvik]│
│ Lov om saltvannsfiske § 13              [?] [▼] │
└─────────────────────────────────────────────────┘
```

**Ekspandert** (etter klikk):
```
┌─────────────────────────────────────────────────┐
│ ⚠ Hummerteine — Manglende merking      [⚠ Avvik]│
│ Lov om saltvannsfiske § 13              [?] [▲] │
├─────────────────────────────────────────────────┤
│ Status: [avvik ▾]                               │
│ Notat: [...]                                    │
│ Lengdemålinger: [...]                           │
│ Posisjoner: [...]                               │
│ Beslag/redskap: [...]                           │
└─────────────────────────────────────────────────┘
```

### Auto-ekspansjons-regler
Et kort er ekspandert som standard hvis ANY av:
- `status === 'avvik'` (manuelt eller automatisk)
- `auto_note` er satt (systemet har flagget noe)
- `_expanded === true` (brukeren har manuelt ekspandert det)

### Klikk-oppførsel
Hele topplinjen er en `<button>` (semantisk korrekt). Klikk = toggle.
Trykk på `[?]` (hjelp-ikon) trigger ikke toggle (event.stopPropagation).

### Statusbadge i topplinjen
Hver topplinje viser nå en badge:
- ⚠ **Avvik** (rød pille)
- ✓ (grønn sirkel) for godkjent
- – (grå sirkel) for ikke relevant
- ● (lys sirkel) for ikke kontrollert

Slik ser kontrolløren status uten å måtte ekspandere.

### Auto-ekspansjon ved status-endring
Når brukeren endrer status til "avvik" via dropdown:
- Kortet ekspanderes umiddelbart
- Lengdemåling/beslag-felt blir tilgjengelig

Når status settes til "godkjent" eller "ikke relevant":
- Kortet kollapses automatisk for cleaner overview

### Tilgjengelighet (a11y)
- `<button>` med `aria-expanded` og `aria-controls`
- Body-element får `id` og `hidden`-attributt
- Tastatur-tilgjengelig (Enter/Space toggler)
- Focus-ring på header-knappen
- `prefers-reduced-motion` respekteres (chevron har 220ms transition)

### Filer
- `app/static/js/case-app.js`:
  - `buildEditableFindingHtml()` omskrevet med kollaps-struktur
  - Ny event handler i `findingsList.addEventListener('click', ...)` for
    head-toggle (i FØRSTE posisjon, før help-toggle)
  - Status-change-handler setter `_expanded` automatisk
- `app/static/styles.css`: ~120 linjer for `.finding-card.is-collapsed`,
  `.finding-card.is-expanded`, `.finding-head-toggle`,
  `.finding-status-badge`, `.finding-chevron` rotasjon

---

## 3. Hurtighet og stabilitet

### renderFindings debouncing
Tidligere: hver state-endring (status-change, måling-add, posisjon-fill,
osv.) kalte `renderFindings()` som re-tegnet hele listen synkront. Hvis
flere endringer skjedde i samme tick (vanlig under komplekse handlinger),
ble DOM-en re-bygget flere ganger på rad.

Nå:
```javascript
var _renderFindingsScheduled = false;
function renderFindings() {
  if (_renderFindingsScheduled) return;
  _renderFindingsScheduled = true;
  requestAnimationFrame(function () {
    _renderFindingsScheduled = false;
    _doRenderFindings();
  });
}
```

Resultat: **maks én re-render per browser-frame** (~60fps), uansett hvor
mange state-endringer som inntreffer i samme tick.

### Scoped DOM queries
Tidligere: `document.querySelectorAll('#findings-list .finding-card')` gikk
gjennom hele DOM-en.

Nå: `findingsList.querySelectorAll('.finding-card')` — bare innenfor
findings-list-elementet. Mindre arbeid, raskere på lange skjemaer.

### CSS containment
```css
.finding-card { contain: layout style; }
```
Ber browseren behandle hvert kort som en isolert layout-rot. Layout/paint
av ett kort vil ikke trigge layout av andre kort — viktig på lange lister
med mange ekspanderte/kollapsede tilstander.

### Filer
- `app/static/js/case-app.js`: rAF-debouncing i `renderFindings()`
- `app/static/styles.css`: `contain: layout style` på `.finding-card`

---

## 4. Verifisering

Spot-check av byggets korrekthet:
```
✓ shouldExpand logic: isAvvik || hasAutoNote || item._expanded === true
✓ card uses shouldExpand class: YES
✓ avvik auto-expand: YES
✓ finding-head-toggle in code: 2 occurrences
✓ itemSupportsLinkToggle defined and used: 2 occurrences
✓ rAF debouncing in renderFindings: YES
```

Python, Jinja, JS og CSS validert syntaktisk.

---

## 5. Versjon

`1.8.38` → `1.8.39`. Alle `?v=1.8.39`. SW-cache `kv-kontroll-1-8-39-static`.

---

## 6. Filer endret

```
MOD:
  app/static/js/case-app.js     — kollaps-struktur, lenke-restriksjon,
                                   ytelses-debouncing
  app/static/styles.css         — +120 linjer for kollaps + badges + perf
  app/static/sw.js              — cache-bump
  app/config.py                 — versjon 1.8.39
  alle templates                — ?v=1.8.39
```

## 7. Filer bevisst IKKE endret

- `app/templates/case_form.html` — kontrollskjema-template aldri rørt
- `app/services/*.py` — ingen serverlogikk endret
- DB-skjema, sync-orkestrator, kart-side, login-flyt
