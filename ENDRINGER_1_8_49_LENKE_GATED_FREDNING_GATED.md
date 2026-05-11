# Endringer 1.8.49 — Lenke-funksjonen gated på checkbox + fredningsfilter

To målrettede UX-/korrekthetsfikser etter brukerrapport:

1. **Lenke-funksjonen** vises kun når «Lenke»-avkrysning er huket av.
   Fram til det er boksen kollapset, og lenke-prefiks vises ikke i avvik.
2. **Forskrift om fredningsområder for hummer (§ 1 / § 1a / § 3)**
   kommer kun fram når brukerens posisjon faktisk er i et fredningsområde
   med hummer-relevans i kartet — ikke speculativt fra serveren.

---

## 1. Lenke-funksjonen kollapset til kun checkbox

### Tidligere (v1.8.48)
Lenke-toolbaren viste alltid:
- Avkrysningsboks «Lenke»
- Tabs (Lenke 1, Lenke 2 …)
- Start-/stopp-posisjon
- Merknad-felt
- «Legg til lenke»-knapp

Selv om bruker ikke hadde aktivert lenke-modus.

### Nå (v1.8.49)
Når lenke-modus er **AV** (default for nye saker), viser toolbaren kun:

```
☐ Lenke (start- og sluttposisjon for redskap)
Huk av for å registrere lenker av redskap (f.eks. teine- eller
garnlenker) med egne start- og sluttposisjoner. Hver lenke får
egen kontrollpunktliste og egne beslagsnumre.
```

Kompakt boks med lys grå bakgrunn. Når bruker hukker av checkboxen,
ekspanderer boksen til full layout med tabs, posisjoner og «Legg til
lenke»-knapp.

### Tilhørende ryddinger
- `deviationLinksHtml(row)` returnerer tom streng når
  `controlLinkModeEnabled === false` → ingen lenke-faner i avviksrader
- Avvik-rad-header: «Lenke 1 · Beslag 1» → bare «Beslag 1»
- Beslagsrapport-kort: samme regel
- Start/stopp-summering under avvik-rad: vises ikke uten lenke-modus

Lenke-metadata bevares stille i state slik at re-aktivering ikke mister
informasjon.

---

## 2. Hummer-fredningsområde gated på faktisk karttreff

### Problem
Kontrollpunktet «Forskrift om fredningsområder for hummer § 1 / § 1a / § 3»
kunne dukke opp uten at brukeren var i et fredningsområde. Årsaker:

- Servern legger til regelen ved `area_status='fredningsområde'` + `species='hummer'`
- `area_status` kan komme fra stale state, manuell entry, eller live
  MapServer-treff som ikke faktisk er en hummer-fredning
- Områdetreffene fra `autoAreaFindingsFromZoneResult` filtreres allerede
  via `areaHitMatchesCurrentSelection`, men regelpakken fra `/api/rules`
  gjør ikke det samme filtreringen

### Løsning
Klient-side filter i `applyRuleBundle()` etter at server returnerer regler:

```javascript
bundle.items = (bundle.items || []).filter(function (item) {
  var key = String(item.key).toLowerCase();
  if (key === 'hummer_fredningsomrade_redskap') {
    // Krev konkret hummer-fredning-treff i siste sone-sjekk
    var hasFredningHit = latestZoneResult && latestZoneResult.match &&
      latestZoneResult.hits.some(function (hit) {
        var blob = norm(hit.name + hit.status + hit.layer + hit.layer_name);
        return /fredningsomr/.test(blob) && /hummer/.test(blob);
      });
    return hasFredningHit;
  }
  ...
});
```

Tilsvarende filter for:
- `fredningsomrade_status` (generisk fredning)
- `stengt_omrade_status` (stengt område / nullfiske)

### Effekt
Punktene vises NÅ kun når:
1. Brukeren har faktisk kjørt «Sjekk posisjon»
2. `latestZoneResult.match === true`
3. Et av treffene har lagets navn/status som matcher mønsteret
   - hummer_fredning: må ha både `fredningsomr` OG `hummer`
   - fredning: bare `fredningsomr`
   - stengt: `stengt` eller `nullfiske`

Hvis filteret fjerner alle punkter (svært usannsynlig), faller appen
tilbake til lokal kontrollpunktliste med en forklarende melding.

---

## 3. Filer endret

```
MOD:
  app/static/js/case-app.js
    - renderControlLinkToolbar()         : kollapset/utvidet states
    - deviationLinksHtml()                : returnerer '' når modus av
    - Avviksrad-header                    : betinget "Lenke X · "-prefiks
    - Seizure-rapport-header              : betinget "Lenke X · "-prefiks
    - applyRuleBundle()                   : klient-filter for områderegler
  app/static/styles.css                  : +25 linjer for .is-collapsed/.is-expanded
  app/static/sw.js                       : cache-bump
  app/config.py                          : versjon 1.8.49
  alle templates                         : ?v=1.8.49
```

## 4. Filer bevisst IKKE endret

- `app/rules.py` — server-logikken er korrekt for det den ser. Klient
  legger på ekstra forsiktighetsfilter siden klienten har bedre
  kontekst (faktiske karttreff).
- Database-skjema og migrasjoner
- Lenke-state-persisting (controlLinkGroups bevares ved av/på-toggle)

---

## 5. Verifisering (14/14 sjekker passert)

```
✓ Toolbar har is-collapsed-tilstand
✓ Toolbar har is-expanded-tilstand
✓ Tabs vises kun når state.enabled
✓ Hjelpetekst når kollapset
✓ deviationLinksHtml returnerer tom hvis ikke enabled
✓ Avvik-rad uten Lenke-prefix når av
✓ Seizure-rapport uten Lenke-prefix når av
✓ Client filter for hummer_fredningsomrade_redskap
✓ Filter sjekker latestZoneResult.hits
✓ Filter sjekker hummer+fredningsomr i hits
✓ Filter for generisk fredningsomrade_status
✓ Filter for stengt_omrade_status
✓ CSS for .control-link-card.is-collapsed
✓ CSS for .control-link-card.is-expanded
```

Python, Jinja og JS validert syntaktisk.

---

## 6. Versjon

`1.8.48` → `1.8.49`. Alle `?v=1.8.49`. SW-cache `kv-kontroll-1-8-49-static`.
