# Endringer 1.8.40 — Velg fiskeriregulerte områder i temalag

## Hva er endret

Kart-siden lar deg nå **velge mellom fiskeriregulerte områder i temalag**
gjennom et nytt kategori-chip-filter. Tidligere viste panelet bare det
strenge underutvalget av "lov-restrektive" områder. Nå kan du velge
mellom seks kategorier av reguleringer.

---

## 1. Seks kategorier av temalag

| Kategori | Emoji | Eksempler |
|---|---|---|
| **Forbud / Fredning** | 🚫 | Bunntrålingsforbud, Hummerfredningsområder, Stengte områder, Nullfiskeområder |
| **Verneområder** | 🛡️ | Marine verneområder, Naturreservater, Korallrev, Bunnhabitat |
| **Fiskerireguleringer** | 🐟 | J-meldinger, Generelle reguleringer, Forskriftsområder |
| **Artsspesifikke** | 🦞 | Maksimalmål kysttorsk, Kongekrabbeområde, Hummerregulering |
| **Redskap / Bruk** | ⚓ | Reketrålgrenser, Snurrevadgrenser, Garn-spesifikt |
| **Andre temalag** | 📍 | Gytefelt, Oppvekst-/beiteområder (referanse-info) |

Klassifiseringen skjer automatisk basert på lagets navn, status,
beskrivelse og panel-gruppe — bruker en hierarkisk regex-matching som
prioriterer mest spesifikk kategori.

---

## 2. Klassifiserings-test (verifisert)

```
🚫 Hummerfredningsområder     → forbud
⚓ Reketrålgrenser            → redskap
🚫 Bunntrålingsforbud         → forbud
🛡️ Marine verneområder        → verne
⚓ Snurrevadgrenser           → redskap
🦞 Maksimalmål kysttorsk      → art
🛡️ Korallrev                  → verne
📍 Gytefelt for torsk         → andre  ← korrekt: referanse, ikke regulering
🐟 J-melding 12-2024          → fiskeri
🦞 Kongekrabbeområde          → art
📍 Oppvekstområde sei         → andre  ← korrekt: referanse, ikke regulering
```

Spesielt: gytefelt, oppvekst- og beiteområder klassifiseres som "andre"
(ikke "art") fordi de er referanse-info, ikke regulering. De vises
fortsatt i panelet hvis brukeren velger "Andre temalag"-chip eller "Alle".

---

## 3. UI: Kategori-chip-filter

Et nytt chip-filter er lagt til over kartlag-listen i temalag-panelet:

```
┌────────────────────────────────────────────────────┐
│ Velg kartlag i kartet                       [×]    │
│ 12 av 47 lag vises                                 │
├────────────────────────────────────────────────────┤
│ [🔍 Søk i lag                          ]           │
├────────────────────────────────────────────────────┤
│ [🌐 Alle 47] [🚫 Forbud 8] [🛡️ Verne 12]            │
│ [🐟 Fiskeri 9] [🦞 Art 6] [⚓ Redskap 8] [📍 12]    │
├────────────────────────────────────────────────────┤
│ ▼ Verneområder (12)                                │
│   ☐ Korallrev                                      │
│   ☑ Marine verneområder Skagerrak                  │
│   ...                                              │
└────────────────────────────────────────────────────┘
```

### Chip-funksjonalitet
- **🌐 Alle**: aktiv som standard, viser alle reguleringsområder
- **Trykk en spesifikk kategori**: deaktiverer "Alle", aktiverer kun den
  trykkede kategorien
- **Trykk flere**: legger til/fjerner kategorier (multi-select)
- **Trykk siste aktive**: faller tilbake til "Alle" automatisk
- **Tall-badge** på hver chip: antall tilgjengelige lag i kategorien

### Tilstand bevares
- Aktive chips lagres i `localStorage` per bruker (samme nøkkel-system som
  resten av temalag-panelet)
- Refresh av siden bevarer valgt kategori-filter

### iPhone-tilpasning
- På skjermer < 480px: chip-tekst krymper, padding reduseres
- På skjermer < 380px: chip-tekst skjules helt — bare emoji + tall vises
- Touch-targets fortsatt minst 32 × 32 px

---

## 4. Mer inkluderende lag-filter

### Tidligere
`isRestrictiveLawLayer()` var den eneste filteren. Den ekskluderte mange
fiskerireguleringer som *ikke* hadde tydelige lov-keywords, f.eks.:
- Reketrålgrenser (ikke matcher "forbud" eksplisitt)
- Snurrevadgrenser
- Generelle reguleringsområder uten "regulert"-status

### Nå
Ny `isSelectableRegulatedLayer()` returnerer `true` for alle lag som
klassifiseres til en av de seks reguleringskategoriene. Den eldre
`isRestrictiveLawLayer()` brukes fortsatt internt for å skille
"strengt lov-restriktivt" fra "fiskerirelevant".

Resultat: **flere fiskeriregulerte områder er nå tilgjengelige for
seleksjon** i kartet, uten å miste den strenge lov-filtreringen for
default-visning.

---

## 5. Filer endret

```
MOD:
  app/static/js/common.js   — classifyLayerCategory, categoryDisplayInfo,
                               isSelectableRegulatedLayer (NY),
                               buildLayerPanelGroups m/ category-filter,
                               countLayersPerCategory (NY),
                               syncLayerPanel m/ chip-rendering,
                               ensureLayerPanelRoot m/ chip-DOM
  app/static/styles.css     — +90 linjer for .kv-temalag-chip,
                               .kv-chip-emoji, .kv-chip-label, .kv-chip-count
  app/static/sw.js          — cache-bump
  app/config.py             — versjon 1.8.40
  alle templates            — ?v=1.8.40
```

## 6. Filer bevisst IKKE endret

- `app/templates/map_overview.html` — kart-siden er uendret; chip-filteret
  rendrer seg i det eksisterende kartlag-panelet
- `app/static/js/map-overview.js` — uendret, bruker fortsatt
  `createPortalMap` fra common.js
- `app/live_sources.py` — kataloglogikk uendret; klassifiseringen skjer
  klientsiden basert på eksisterende `panel_group`/`status`-felt
- `app/templates/case_form.html` — ikke berørt
- DB-skjema, sync-orkestrator, login-flyt

---

## 7. Versjon

`1.8.39` → `1.8.40`. Alle `?v=1.8.40`. SW-cache `kv-kontroll-1-8-40-static`.
