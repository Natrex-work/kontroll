# Endringer 1.8.43 — Synlig chip-stripe på kartet + FAB-feedback fikset

## Hva er endret

To målrettede fikser etter brukerinnsigelse om at FAB-knappene på kartet
"ikke fungerer":

1. **Chip-stripe direkte på kartet** — alltid synlig, klikk for å toggle
   reguleringsområder uten å åpne paneler
2. **FAB-knappene gir nå tydelig respons** — pulse-animasjon ved klikk +
   touch-state-styling, og layers-FAB scroller faktisk til lag-seksjonen

---

## 1. Problem fra brukerrapport

Skjermbilde fra iPhone viser tre FAB-knapper øverst til høyre på kartet
(☀️ lokasjon, 📚 lag, ⬇️ offline) og en kommentar:
> "De merkete funksjonen i bildet fungerer ikke. Jeg ønsker at det er
>  mulig å velge områder som skal framvise visuelt i kartet."

Etter analyse var dette de faktiske problemene:

- **Layers-FAB** kalte `setExpanded(true)` og `scrollIntoView()` på samme
  tick — på iOS Safari ble scroll utført FØR body var lagt ut, så ingenting
  visibelt skjedde
- **Lokasjon- og offline-FABs** ga ingen visuell respons på trykk, så
  brukeren trodde de ikke registrerte klikket
- **Kategori-chips** (fra v1.8.40-42) lå inne i bottom-sheet — du måtte
  først åpne sheet, scrolle ned, og *deretter* trykke chip. Skjult bak
  flere lag UX.

---

## 2. Løsning: Synlig chip-stripe rett på kartet

Ny **alltid-synlig chip-stripe** i bunnen av kartet, like over
bottom-sheet-håndtaket:

```
[🌐 Alle 22/47] [🚫 Forbud 5/8] [🛡️ Verne 8/12] [🐟 Fiskeri 3/9] ...
                                                                  
[━━━━ Bruk min posisjon for å sjekke regulerte områder ━━━━]   ← bottom sheet
```

### Funksjonalitet
- **Alltid synlig** — ingen panel-åpning nødvendig
- **Horisontalt skrollbar** ved mange kategorier
- **Smart-toggle**: trykk en chip → vis/skjul alle lag i kategorien
- **Tall-badge** `synlig/totalt` per kategori — øyeblikkelig oversikt
- **Tilstand**:
  - Mørk blå = ≥ 50% synlig på kartet
  - Lys blå = noen synlig, < 50%
  - Hvit = alle skjult
- **Pulse-animasjon** ved trykk (visuell bekreftelse)

### Iphone-tilpasning
- < 380px: skjul tekst, vis kun emoji + tall (sparer plass)
- Backdrop-blur (12px) for Apple Maps-look
- Touch-target ≥ 30px høyde + padding

### Synkronisering med panel
Chip-stripens tilstand leses fra og lagres til **samme localStorage-
nøkkel** som panel-chips (state.layerPanelKey). Endringer reflekteres
øyeblikkelig i panelet og omvendt.

---

## 3. Layers-FAB scrollIntoView fikset

```javascript
// FØR (v1.8.42 — funket ikke konsistent på iOS Safari):
btnLayers.addEventListener('click', function () {
  if (sheet.dataset.state !== 'expanded') setExpanded(true);
  if (section) section.scrollIntoView({ behavior: 'smooth' });
});

// NÅ (v1.8.43):
btnLayers.addEventListener('click', function () {
  btnLayers.classList.add('map-fab-pulse');
  setTimeout(function () { btnLayers.classList.remove('map-fab-pulse'); }, 260);
  var wasCollapsed = sheet.dataset.state !== 'expanded';
  if (wasCollapsed) setExpanded(true);
  // Vent på at body blir layoutet før scroll — scrollIntoView på et
  // hidden element feiler stille på iOS Safari
  setTimeout(function () {
    if (section) section.scrollIntoView({ behavior: 'smooth', block: 'start' });
  }, wasCollapsed ? 60 : 0);
});
```

60ms-delay gir browseren tid til å gjøre layout etter `body.hidden = false`
før scroll-mål beregnes. Sammen med pulse-animasjon viser dette tydelig
at klikket ble registrert.

---

## 4. Visuell respons på alle FABs

Alle tre FABs (locate, layers, offline) får nå:

### Touch-state-styling
```css
.map-fab.map-fab-touched {
  background: rgba(43, 128, 214, 0.10);
  border-color: rgba(43, 128, 214, 0.30);
}
```

Reagerer på `touchstart`-event, fjernes på `touchend` med 200ms forsinkelse
(så brukeren hinner se det selv ved kjapp tap).

### Pulse-animasjon ved klikk (kun layers-FAB foreløpig)
```css
@keyframes fabPulse {
  0%   { transform: scale(0.92); }
  50%  { transform: scale(1.08); box-shadow: 0 6px 18px rgba(43,128,214,0.45); }
  100% { transform: scale(1.0); }
}
```

260ms ease — kort nok til å føles snappy, lang nok til å være synlig.

---

## 5. Eksponerte funksjoner i KVCommon

For at map-overview.js skal kunne kalle på samme klassifiserings­logikk
som panel-chips, er flere funksjoner nå eksponert via `window.KVCommon`:

```javascript
window.KVCommon = {
  ...,
  classifyLayerCategory,        // (NY) klassifiser et lag
  categoryDisplayInfo,          // (NY) emoji + label per kategori
  isSelectableRegulatedLayer,   // (NY) er laget en reguleringssone?
  countLayersPerCategory,       // (NY) per-kategori-tellinger
  loadLayerPanelPrefs,          // (NY) les lagrede prefs
  saveLayerPanelPrefs,          // (NY) skriv prefs
};
```

Dette gjorde at chip-strip-koden i map-overview.js bruker NØYAKTIG
samme logikk som panel-chips — ingen duplikering, ingen drift mellom
de to UIene.

---

## 6. Filer endret

```
MOD:
  app/templates/map_overview.html  — chip-strip-DOM lagt til,
                                      layers-FAB-handler fikset,
                                      touchstart/end-events på FABs
  app/static/js/map-overview.js    — renderQuickChips, handleQuickChipClick
                                      og kobling til redrawMap
  app/static/js/common.js          — eksponert klassifiseringsfunksjoner
                                      via KVCommon
  app/static/styles.css            — +120 linjer for .map-quick-chips,
                                      .map-quick-chip + .map-fab-pulse
                                      og .map-fab-touched animasjoner
  app/static/sw.js                 — cache-bump
  app/config.py                    — versjon 1.8.43
  alle templates                   — ?v=1.8.43
```

## 7. Filer bevisst IKKE endret

- `app/templates/case_form.html` — ikke berørt
- `app/services/*.py` — ingen serverlogikk endret
- `app/live_sources.py` — kataloglogikk uendret
- DB-skjema, sync-orkestrator, login-flyt

---

## 8. Slik tester du

1. Last `?v=1.8.43` på kart-siden (Hard refresh på iPhone Safari:
   åpne Innstillinger → Safari → Slett historikk og nettstedsdata, eller
   bruk privat fane første gang)
2. Du skal se en chip-stripe i bunnen av kartet:
   `🌐 Alle  🚫 Forbud  🛡️ Verne  🐟 Fiskeri  🦞 Art  ⚓ Redskap  📍 Andre`
3. Trykk **🛡️ Verne** → chip pulse-animeres, vern-områder skal synes
4. Trykk **🌐 Alle** → alle reguleringer skrus av/på i ett trykk
5. Trykk **📚 lag-FAB** øverst til høyre → FAB pulse-animeres,
   bottom-sheet glir opp, scroller automatisk til "Kartlag"-seksjonen
6. Trykk **☀️ lokasjon-FAB** → kartet sentrerer på posisjon
7. Trykk **⬇️ offline-FAB** → starter offline-pakke-nedlasting

---

## 9. Verifisering (16/16 sjekker passert)

```
✓ Template: chip strip element added
✓ Template: layers FAB has scroll-after-render fix
✓ Template: FAB pulse on click
✓ Template: FAB touchstart/end feedback
✓ common.js: classifyLayerCategory exposed
✓ common.js: loadLayerPanelPrefs exposed
✓ map-overview.js: renderQuickChips defined
✓ map-overview.js: handleQuickChipClick defined
✓ map-overview.js: renderQuickChips called after redrawMap
✓ map-overview.js: chip click bound
✓ map-overview.js: initial chips render
✓ CSS: .map-quick-chips defined
✓ CSS: .map-quick-chip is-active style
✓ CSS: .map-quick-chip is-partial style
✓ CSS: qcPulse animation
✓ CSS: fabPulse animation
```

Python, Jinja, JS og CSS validert syntaktisk uten feil.

---

## 10. Versjon

`1.8.42` → `1.8.43`. Alle `?v=1.8.43`. SW-cache `kv-kontroll-1-8-43-static`.
