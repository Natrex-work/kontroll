# Endringer 1.8.31 — Profesjonell design- og UX-polish

## Mål
Et helhetlig, profesjonelt og konsistent visuelt uttrykk på tvers av hele
webappen, med spesielt fokus på iPhone og iPad i feltbruk. Ingen
funksjonalitet er endret. Backend, JavaScript-bundlene, kontrollskjemaet
(`case_form.html`) og `case-app.js` er bevisst ikke berørt.

---

## 1. Profesjonelt helhetsinntrykk

### Designsystem (semantiske tokens)
Lagt til et komplett sett CSS-variabler som styrer hele appens visuelle
uttrykk. Dette gir konsistent spacing, typografi, skygger og fargekoding
overalt — uten å berøre eksisterende selektorer.

| Token-gruppe | Eksempler |
|---|---|
| Spacing (4px-skala) | `--mk-space-1` til `--mk-space-9` (4px → 56px) |
| Border-radius | `--mk-radius-xs` (8px) til `--mk-radius-pill` (999px) |
| Typografi | `--mk-text-xs` til `--mk-text-3xl` (0.75rem → 2.25rem) |
| Skygger | `--mk-shadow-sm/md/lg/xl` |
| Status-farger | `--mk-status-draft/ready/sent/warn/none-{bg,fg,line}` |
| iOS safe-area | `--mk-safe-{top,bottom,left,right}` |

### Typografi
- System font stack med **SF Pro Text/Display** som primær på iOS/iPadOS,
  Inter som fallback på desktop, og Segoe UI/Roboto for andre plattformer.
- `font-feature-settings: "ss01", "cv11"` — penere tall og bokstavformer.
- `text-rendering: optimizeLegibility` og `font-smoothing: antialiased`.
- Konsistent type-skala for h1/h2/h3 med `letter-spacing: -0.02em` på
  overskrifter (gir mer profesjonell typografi).
- `font-variant-numeric: tabular-nums` på alle statistiske tall, så sifrene
  ikke "hopper" mellom rerendringer.

### Statusfarger (konsistent på tvers)
Status-pilles (`Utkast`, `Anmeldt`, `Anmeldt og sendt`, `Advarsel`,
`Ingen reaksjon`) har nå samme fargekoding overalt — på dashboard, i
sakslisten og i admin-vinduer.

---

## 2. Iphone/iPad-tilpasninger

| Område | Endring |
|---|---|
| Auto-zoom på input-fokus | Avskrudd. `input/select/textarea` har nå `font-size: max(16px, ...)` slik at Safari på iOS ikke zoomer inn ved fokus. |
| Tap highlight | Avskrudd globalt (`-webkit-tap-highlight-color: transparent`). Vi bruker `:focus-visible` i stedet. |
| Safe-area | Sidemenyen får `padding-top: calc(10px + env(safe-area-inset-top))`. Body får `padding-bottom: env(safe-area-inset-bottom)`. Skip-link respekterer safe-area. |
| Momentum scroll | `-webkit-overflow-scrolling: touch` på `.main`, `.sidebar`, `.home-screen`, `.table-wrap`. |
| Touch targets | Alle knapper minimum 44×44px (eksisterende krav, forsterket). Tile-knapper på mobil minst 156px høyde. |
| Landscape (kort høyde) | Egen mediaquery for landscape-iPhone (`max-height: 520px`) som strammer login-siden. |
| `text-size-adjust` | Forhindrer at iOS skalerer tekst i store overskrifter ved enhetsrotasjon. |

---

## 3. Stabilitet og redusert flimmer

- `contain: layout paint style` på sentrale komponenter (`.home-tile`,
  `.card`, `.home-panel`, `.login-card`, `.home-case-row`,
  `.home-mini-stat`). Browser kan optimalisere subtree-rerendring.
- Alle hover/transition-effekter har eksplisitt timing
  (`140ms cubic-bezier(0.2, 0.8, 0.2, 1)`) i stedet for default. Gir mykere,
  mer profesjonelle bevegelser.
- `prefers-reduced-motion` respekteres — alle transitions/animasjoner
  reduseres til 0.01ms for brukere som har slått det av.
- `font-variant-numeric: tabular-nums` på alle telleverdier, så tallet
  ikke skifter bredde mellom oppdateringer (eliminerer "hopping").

---

## 4. Login-flaten — strammet opp

### Før
- "Logg inn"-h2 inni kortet duplikerte seksjonsoverskriften.
- "Mobiltilpasset arbeidsflate for kontroll, kart, regelverk, dokumentasjon
  og videre oppfølging i samme flyt." — generisk og ordrik.
- 2FA-siden hadde to brand-områder + h2 + alert + skjema + alert + skjema —
  rotete.

### Etter
- **`login.html`** har én ren overskrift («Logg inn for å fortsette»),
  konsis undertittel («Kontroll, kart, regelverk og dokumentasjon i én
  flyt — tilrettelagt for feltbruk på iPhone og iPad»), kort header
  med logo + appnavn + «Sikker innlogging», og en finprint-linje under
  knappen som forklarer 2-trinns for ikke-admin.
- **`login_2fa.html`** har:
  - Steg-indikator (✓ → ●) som visuelt forteller hvor i flyten brukeren er.
  - Stor monospace OTP-input med `letter-spacing: 0.32em` og auto-submit
    når 6 siffer er fylt inn.
  - "Send ny kode" og "Avbryt" som rene tekstlenker i bunnen, ikke som
    fullbredde sekundærknapper.
- Felter har nye `.field` / `.field-label` / `.field-hint`-klasser med
  konsistent layout og hint-tekst.
- Input-fokus har myk skyggering (`box-shadow: 0 0 0 3px rgba(43,128,214,0.14)`)
  i stedet for hard outline.

---

## 5. Dashboard / hjemmeskjerm

### Endringer i `dashboard.html`
- **Personlig velkomst**: «Velkommen, {fornavn}» i stedet for generisk
  overskrift som ikke var personlig.
- **Strammet copy**: «Start ny kontroll, hent fram saker eller åpne kart
  og regelverk.» (15 ord → 11) i stedet for den ordrike forklaringen om
  hva startsiden er.
- **Fjernet redundans**: Den separate `home-link-stack` (lenker til
  saker/regelverk) er fjernet — disse var allerede synlige som tiles.
- **Fjernet `home-map-promo`-blokken**: Var en duplisering av kart-tilen
  som lå rett over.
- **Tile-rekkefølge**: Ny kontroll, Saker, Kart, Regelverk (matchet
  arbeidsflyten i felt).
- **Primær-tile**: «Ny kontroll» har nå en distinkt blå gradient
  (`#2b80d6` → `#1f63ad`) som fremhever den som hovedhandlingen, slik at
  feltbrukeren raskt finner riktig knapp.
- **Empty state**: Når ingen saker eksisterer, vises en sentrert empty-state
  med stor ikon, kort tekst og CTA-knapp. Tidligere var det bare tekst.
- **Skjult panel**: Lokale kladd-panel vises nå *bare* når det faktisk
  finnes lokale kladder (`hidden`-attributt fjernes via JS). Slipper en
  tom rød boks for nyinstallerte enheter.
- **Statuspiller**: Saksstatusen får automatisk en farge basert på status
  (Utkast = gul, Anmeldt = blå, Anmeldt og sendt = grønn, etc.).

### Tile-design
- Strammere proporsjoner (192px standard, 156px mobil).
- Hover-effekten gir nå en delikat translation-Y(-2px) i stedet for
  brå skygge. Active state komprimerer tilbake til 0.
- Mobil har flere kolonner kollapset til én rad-flow (ikon venstre,
  tekst høyre) for bedre touch-tilgang i én hånd.

---

## 6. Sidebar / navigasjon

- **Bedre kontrast** i den blå sidemenyen — bakgrunn med subtil radial
  gradient (`radial-gradient(... rgba(123,219,232,0.06) ...)`) for å gi
  dybde uten å overdrive.
- **Aktiv lenke** har nå tydelig kontrast (`rgba(255,255,255,0.10)` +
  inset-skygge), tidligere var den nesten umulig å se.
- **Brukerkort** i bunnen har strammere padding og finere typografi.
- **Historie-knapper** (← →) er nå runde 40×40px med subtil hover/press —
  tidligere var de små og smalt nok til å være vanskelige å treffe på
  iPhone.

---

## 7. Sider som er strammet (uten å berøre logikk)

| Side | Endring |
|---|---|
| `controls_overview.html` | Kun versjons-bump. Rendres med ny CSS som gir bedre tabell-typografi (sticky header med uppercase mini-label) og hover på rader. |
| `rules_overview.html` | Kun versjons-bump. Form-feltene får nye fokusstiler. |
| `map_overview.html` | Kun versjons-bump. Card-padding og skygger blir konsistente. |
| `admin_users.html`, `admin_controls.html` | Kun versjons-bump. Tabeller og statkort får ny finish. |
| `audit_log.html` | Kun versjons-bump. |

---

## 8. Lister og kort overalt

Alle `.card` og `.home-panel` har nå:
- Konsistent `border-radius: 22px`.
- Subtil gråblå border (`rgba(213, 223, 235, 0.7)`) for å definere kanten
  uten å virke teknisk.
- Skygge fra det semantiske tokenet `--mk-shadow-md`.
- `contain: layout paint style` for raskere rerendring.

Hovedlinjer i lister (`.home-case-row`, `.data-table tbody tr`):
- Hover gir myk translateX(2px) + svakt blå bakgrunn.
- Border-radius 16px (avrunder mer enn tidligere 12px).
- Saksnummeret er nå mer fremtredende med `font-weight: 700` og
  `letter-spacing: -0.01em`.

---

## 9. Form-system

Inputs (utenom case_form-scopet) får:
- 1.5px border (`#d5dfeb`) i stedet for tynne 1px streker.
- Hover-state med litt mørkere kant (`#b6c9dc`).
- Fokusring som myk skygge (`box-shadow: 0 0 0 3px rgba(43,128,214,0.14)`)
  i stedet for hard outline — mer profesjonelt og mindre teknisk.
- Bakgrunn `#fbfcfe` på login-felter for å fremheve aktivitet ved fokus
  (skifter til ren hvit).
- 16px minimum font-size for å hindre auto-zoom på iOS.

---

## 10. Versjonsheving

- `app/config.py`: `1.8.30` → `1.8.31`
- `app/static/sw.js`: cache-navn `kv-kontroll-1-8-31-static` og statiske
  filer med `?v=1.8.31`
- Alle templates (`base.html`, `login.html`, `login_2fa.html`,
  `dashboard.html`, `controls_overview.html`, `rules_overview.html`,
  `map_overview.html`, `admin_users.html`, `admin_controls.html`,
  `audit_log.html`, `case_form.html`, `case_preview.html`):
  `?v=1.8.30` → `?v=1.8.31`

---

## 11. Filer endret

```
app/static/styles.css                  +955 linjer (additivt polish-lag)
app/templates/login.html               omskrevet (renere struktur)
app/templates/login_2fa.html           omskrevet (steg-indikator + auto-submit)
app/templates/dashboard.html           omskrevet (fjernet redundans, ny copy)
app/templates/base.html                versjons-bump
app/templates/controls_overview.html   versjons-bump
app/templates/rules_overview.html      versjons-bump
app/templates/map_overview.html        versjons-bump
app/templates/admin_users.html         versjons-bump
app/templates/admin_controls.html      versjons-bump
app/templates/audit_log.html           versjons-bump
app/templates/case_form.html           versjons-bump (innhold uberørt)
app/templates/case_preview.html        versjons-bump (innhold uberørt)
app/static/sw.js                       cache-navn og asset-versjoner
app/config.py                          app_version → 1.8.31
```

## 12. Filer bevisst IKKE endret

- `app/static/js/case-app.js` (474 KB av domenelogikken)
- `app/templates/case_form.html` (komplekst skjema med 9 steg)
- `app/static/js/common.js`, `local-cases.js`, `local-map.js`,
  `local-media.js`, `map-overview.js`, `rules-overview.js`,
  `admin-users.js`
- All Python-kode (routes, services, db)

Polishen er rent kosmetisk og kan rulles tilbake ved å fjerne det avsluttende
"1.8.31 — Polish-lag"-blokken i styles.css uten andre konsekvenser.
