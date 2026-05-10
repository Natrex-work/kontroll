# Endringer 1.8.42 — Temagruppe-chips toggler kart-synlighet + verneområde-rendering

## Hva er endret

To målrettede fikser i kart-sidens temalag-funksjon:

1. **Trykk på temagruppe-chip = av/på i kartet**
   Chips (🚫 Forbud, 🛡️ Verne, 🐟 Fiskeri, 🦞 Art, ⚓ Redskap, 📍 Andre)
   toggler nå **faktisk synlighet på kartet** — ikke bare panel-filter
   som i v1.8.40.

2. **Verneområder rendres nå korrekt**
   Lag som er klassifisert som verne (verneområder, naturreservat, korall,
   bunnhabitat) sendes nå til riktig MapServer (`Fiskeridir_vern`) basert
   på lagets navn/status, ikke bare service_url. Dette retter at vern-lag
   tidligere kunne sendes til Yggdrasil-tjenesten der de ikke fantes →
   ingen rendering.

---

## 1. Smart-toggle på chips

### Tidligere (v1.8.40)
Chips filtrerte kun **panel-visningen** (hvilke kort man så i listen).
Brukeren måtte deretter aktivt huke av sjekkbokser for hvert lag for å
faktisk vise dem på kartet.

### Nå (v1.8.42)
Klikk på chip → smart-toggle av kart-synligheten:

```javascript
// Spesifikk kategori (f.eks. 🛡️ Verne):
//   - Hvis < 30% av lagene i kategorien er synlig nå → vis ALLE
//   - Hvis ≥ 30% er synlig → skjul ALLE i kategorien
var visibleRatio = visibleInCat / inCat.length;
setCategoryVisible(cat, visibleRatio < 0.3);

// 🌐 Alle:
//   - Hvis noe er synlig → skjul alt
//   - Hvis ingenting er synlig → vis alt
```

### Visuell tilstand på chips
| Tilstand | Visuell | Når |
|---|---|---|
| **Aktiv** (mørk blå) | `is-active` | ≥ 50% av lagene synlig på kartet |
| **Delvis** (lys blå) | `is-partial` | Noen synlig, men < 50% |
| **Inaktiv** (hvit) | (default) | Alle skjult |

### Tall-badge
Endret fra `[totalt]` til `[synlig/totalt]`:

```
[🛡️ Verneområder 8/12]   ← 8 av 12 lag i kategorien er synlig
[🚫 Forbud 0/8]           ← Alt skjult
[🌐 Alle 22/47]           ← Totalt 22 av 47 lag synlig
```

Slik ser brukeren tydelig hva som faktisk vises uten å scrolle gjennom
panelet.

---

## 2. Verneområder rendres nå korrekt

### Problem
I `layerServiceMeta()` ble lag bare rutet til Fiskeridir_vern hvis deres
`service_url` inneholdt `fiskeridir_vern`. Men flere verne-lag i katalogen
har enten:
- Tomt `service_url`-felt
- Feil URL fra eldre import
- URL som peker på Yggdrasil-fiskeri-tjenesten

Disse ble derfor sendt til feil MapServer og rendret ikke.

### Løsning
Ny `isVerneByContent`-sjekk: hvis lagets navn, status eller beskrivelse
matcher verne-mønstre (`verneområde|nasjonal park|naturreservat|landskapsvern|marint vern|korall|bunnhabitat`), og en `vernServiceUrl` er konfigurert,
så prøver vi å rute til vern-tjenesten:

```javascript
if (isVerneByContent && vernServiceUrl) {
  meta.url = normalizedServiceUrl(vernServiceUrl);
  if (knownVernIds[String(rawId)]) {
    meta.layerId = rawId;
    return meta;
  }
  for (var i = 0; i < legacyIds.length; i++) {
    if (knownVernIds[String(legacyIds[i])]) {
      meta.layerId = legacyIds[i];
      return meta;
    }
  }
  // Fall through til fishery-tjenesten hvis ingen vern-ID match
}
```

`portalVernIdLookup()` kjenner ID-ene `{0, 1, 2, 3, 6, 23, 34, 35, 37}` som
gyldige verne-lag i Fiskeridir_vern MapServer. Hvis lagets `id` eller
noen `legacy_ids` matcher en av disse, brukes den ID-en mot vern-tjenesten.

### Beholdt sikkerhetsnett
Lag uten gyldig vern-ID-match faller tilbake til fishery-tjenesten (som
før), så v1.8.30-fiksen er ikke reversert. Det handler nå om å aktivt
ROUTE verne-lag til riktig sted, ikke å aksidentelt sende fiskerirelaterte
lag dit.

---

## 3. Panelet viser nå alle lag (chips filtrerer kun kartet)

### Endring
`buildLayerPanelGroups(layers, query, activeCategories)` ignorerer nå
`activeCategories`-parameteren — chips påvirker ikke lenger hvilke kort
som vises i panelet.

Dette betyr:
- Chips trykker av/på lag i kartet
- Panelet viser alltid alle valgbare reguleringsområder
- Brukeren kan fortsatt finjustere enkeltlag via sjekkbokser

### Hvorfor bedre
Fordeler:
- **Færre klikk for å se hva som er aktivt**: chip-tilstanden viser det direkte
- **Lett å justere etter chip-toggle**: trykk chip for å aktivere kategori,
  scroll deretter ned i panelet for å skrumelle ned individuelle lag
- **Søkefelt fungerer på tvers av alle lag**: ikke begrenset til synlig
  chip-kategori

### Visuell forsterkning
Hver gruppe i panelet får nå sitt kategori-emoji ved siden av tittelen:

```
▼ 🛡️ Verneområder Skagerrak (3/8)
   ☑ Korallrev sør
   ☐ Marine verneområder Tromsø
   ...

▼ 🚫 Hummerfredningsområder (0/2)
   ☐ Sør for Stavanger
   ☐ Vest for Bergen
```

Slik er det visuelt klart hvilken kategori hver gruppe tilhører.

---

## 4. Touch-targets

På mobil er chips og sjekkbokser større for bedre touchresponse:

```css
.kv-temalag-chip {
  min-height: 36px;     /* Desktop default */
}
@media (max-width: 640px) {
  .kv-temalag-chip {
    min-height: 38px;
    padding: 7px 11px;
  }
  .kv-temalag-item-check {
    min-width: 22px;
    min-height: 22px;
  }
}
```

Apple HIG anbefaler ≥ 44pt; iOS regner emojier med padding mot dette, så
38px-knapp + 8px gap = ca. 44pt total touch zone.

---

## 5. Filer endret

```
MOD:
  app/static/js/common.js   — chip click toggler hidden_ids,
                               renders chip state from visibility,
                               buildLayerPanelGroups ignorerer chip-filter,
                               layerServiceMeta(): isVerneByContent-fallback,
                               group-tittel inkluderer kategori-emoji
  app/static/styles.css     — +50 linjer for .is-partial-state og
                               .kv-temalag-group-emoji
  app/static/sw.js          — cache-bump
  app/config.py             — versjon 1.8.42
  alle templates            — ?v=1.8.42
```

## 6. Filer bevisst IKKE endret

- `app/templates/map_overview.html` — uendret
- `app/static/js/map-overview.js` — uendret (bruker fortsatt
  createPortalMap-kontrakten med portalFisheryService og portalVernService)
- `app/live_sources.py` — uendret (kataloglogikk og vern-URL-konfig
  er stabil)
- `app/templates/case_form.html` — uendret siden v1.8.41

---

## 7. Hvordan teste

1. Last `?v=1.8.42` på kart-siden, åpne temalag-panelet
2. Trykk **🛡️ Verne** → alle vern-lag skal aktiveres på kartet
3. Trykk **🛡️ Verne** igjen → alle vern-lag skal skjules
4. Trykk **🌐 Alle** → alt skal toggles av/på
5. Trykk en chip → relaterte verneområder/fiskerireguleringer skal vises
   som farge-overlay på kartet
6. Sjekk at chip-tallet endrer seg (f.eks. **🛡️ Verne 8/12** → **0/12**)

---

## 8. Versjon

`1.8.41` → `1.8.42`. Alle `?v=1.8.42`. SW-cache `kv-kontroll-1-8-42-static`.
