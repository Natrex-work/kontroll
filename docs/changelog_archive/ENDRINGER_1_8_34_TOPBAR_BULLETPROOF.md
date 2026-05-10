# Endringer 1.8.34 — Topbar fix på iPhone + bulletproof brukeropprettelse

## To konkrete bugs fikset

Etter user-rapport med skjermbilde fra `minfiskerikontroll.no` på iPhone er
to spesifikke problemer rettet:

1. **Topbar overflowet på iPhone** — «MINFISKERIKONTROLL» (versal pga
   tidligere CSS-regel) i stor font kolliderte med back/forward-knappene
   og synk-badgen.
2. **Brukeropprettelse var fragil** — den segmenterte rollevalg-kontrollen
   hadde `preventDefault()` på label-klikk og en hidden select for
   bakoverkompatibilitet. På noen enheter kunne dette feile, og uansett
   ble alle skjemaverdier mistet ved valideringsfeil.

---

## 1. Topbar — iPhone-tilpasset (definitivt)

### Problem
Eksisterende `@media (max-width: 960px)` satt `.brand-org-name` til `1.18rem`
og `.brand-app-name` til `0.94rem`. Min v1.8.31-polish la til
`text-transform: uppercase` globalt på `.brand-org-name`. Resultatet ble
«MINFISKERIKONTROLL» i 19px versal — for langt for en 375 px iPhone:

| Element | Bredde |
|---|---|
| Logo (54px) | 54 px |
| Gap | 14 px |
| «MINFISKERIKONTROLL» | ~192 px |
| Sync badge med tekst | ~80 px |
| Back btn | 40 px |
| Forward btn | 40 px |
| Padding/gaps | ~30 px |
| **Sum** | **450+ px** (fits ikke i 375 px) |

### Løsning
Eksplisitte regler for `≤ 640px` og `≤ 380px`:

**På iPhone (≤ 640px):**
- Logo komprimeres fra 54 → 42 px
- `brand-org-name` blir `0.78rem` (~12.5px), versal og fett, 78 % opasitet
  — fremstår som en kicker over hovednavnet
- `brand-app-name` («Kontroll») blir hovednavnet i `1rem` (16px), bold
- Begge får `white-space: nowrap; overflow: hidden; text-overflow: ellipsis;`
- Sync-badge går til ren ikon (36×36 px), antall flytter til en liten
  rød boble (badge) oppå ikonet — slipper å ta horisontal plass
- History-knapper komprimeres fra 40 → 36 px
- Topbar-grid: `auto minmax(0,1fr) auto` så midten kan krympe

**På iPhone SE / mini (≤ 380px):**
- Logo til 38 px
- `brand-org-name` til 0.7rem
- `brand-app-name` til 0.95rem
- Forward-knappen skjules (back er nok i felt — du går alltid framover via
  trykk på elementer)
- Sync-badge og history-knapper til 34 × 34 px

### Fil
- `app/static/styles.css` (+95 linjer i en ny «1.8.34»-blokk)

---

## 2. Brukeropprettelse — bulletproof

### Frontend-fiks: vanlig `<select>` for rolle
Den segmenterte rollevalg-kontrollen er fjernet til fordel for et vanlig
`<select>`-element. Det er kjent å fungere overalt og krever ingen
JavaScript-magi for å kunne sende `role` korrekt i form-en.

```html
<!-- FØR: kompleks segmentert kontroll med radio + hidden select -->
<div class="admin-role-segmented" role="radiogroup">
  <label data-role="investigator">
    <input type="radio" name="role" value="investigator" />
    ...
  </label>
  ...
</div>
<select name="_role_legacy" hidden>...</select>

<!-- NÅ: bare en select -->
<select id="create-role" name="role" required>
  <option value="investigator">Etterforsker</option>
  <option value="admin">Admin</option>
</select>
```

### Backend-fiks: defensiv create-endpoint
Ny `admin_create_user`-funksjon med:

1. **Skjemaverdier samles inn først** — alle felt leses i en `raw`-dict
   før noen validering.
2. **Lokal `_render_error()`-funksjon** som rendrer admin_users.html på
   nytt med `preserved=raw` slik at brukeren ikke må fylle ut alt på nytt
   hvis bare passordet var for kort.
3. **Tre eksplisitte try/except-blokker:**
   - CSRF-validering
   - Feltvalidering (e-post, passord, rolle, telefon, prefix, permissions)
   - Database-opprettelse (med IntegrityError-håndtering)
4. **Audit-logg skadefri** — selv om `db.record_audit` skulle feile,
   blokkeres ikke brukeropprettelsen.
5. **Detaljert logging** ved hvert feilsteg (`logger.info`,
   `logger.warning`, `logger.exception`).
6. **Aldri 500** — alle exceptions ender i en HTML-respons med feilmelding.

### Frontend-fiks: bevart skjema ved feil
`admin_users.html` tar nå imot `preserved`-context og fyller inn alle
verdier fra forrige forsøk:

```jinja
{% set p = preserved or {} %}
<input name="full_name" value="{{ p.get('full_name', '') }}" required />
<input name="email" value="{{ p.get('email', '') }}" type="email" required />
<select name="role">
  <option value="investigator" {% if p.get('role') != 'admin' %}selected{% endif %}>...</option>
  ...
</select>
```

Avansert-seksjonen åpnes automatisk hvis brukeren hadde fylt inn noen av
de avanserte feltene — slik at de ser hva de tidligere skrev.

Permissions huskes også: hvis admin krysset av flere, beholdes de.

### JavaScript-fiks: forenklet
`admin-users.js` er forenklet og fjernet for `preventDefault()` på label-
klikk. All rolle-håndtering bruker nå standard `<select>`-`change`-events:

```js
function initCreateRole() {
  var sel = document.getElementById('create-role');
  if (!sel) return;
  sel.addEventListener('change', function () { applyCreateRole(sel.value); });
  applyCreateRole(sel.value || 'investigator');
}
```

---

## 3. Verifikasjon

Tre faktiske template-render-tester ble kjørt under bygging:

```
Test 1 (normal render): OK
Test 2 (error w/ preserved): OK — verdier bevart
Test 3 (success modal): OK
```

JS, Python, Jinja og CSS validert syntaktisk.

---

## 4. Versjon

- `app/config.py`: `1.8.33` → `1.8.34`
- `app/static/sw.js`: `kv-kontroll-1-8-34-static`
- Alle `?v=1.8.33` → `?v=1.8.34`

---

## 5. Filer endret

```
MOD:
  app/routers/admin.py             — bulletproof admin_create_user (defensive,
                                     preserves form values, never 500)
  app/templates/admin_users.html   — vanlig <select> for rolle, bevart 
                                     verdier ved feil via preserved-context
  app/static/js/admin-users.js     — forenklet, ingen preventDefault på label
  app/static/styles.css            — +95 linjer for iPhone topbar-fiks
  app/static/sw.js                 — versjons-bump
  app/config.py                    — versjon 1.8.34
  alle templates                   — ?v=1.8.34
```

## 6. IKKE endret

- `app/static/js/case-app.js`, `case_form.html`, kontrollskjema-flow
- `app/static/js/sync-orchestrator.js`, `image-prep.js`
- `app/templates/sync_inspector.html`
- Database-skjema, OTP-flyt, evidence-upload-endepunkter
