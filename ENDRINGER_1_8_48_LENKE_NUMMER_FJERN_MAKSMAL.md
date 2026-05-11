# Endringer 1.8.48 — Lenke-nummerformat, fjern lenke + maksmål kun i maks-område

Fire målrettede forbedringer av lenke- og lengdemåling-funksjonalitet
fra v1.8.47.

---

## 1. Nytt nummerformat for beslag: `LBHN 26 001 L1 001`

### Tidligere (v1.8.47)
```
LBHN 26 001-001
LBHN 26 001 - Måling -001
```
Ingen referanse til hvilken lenke beslaget tilhører.

### Nå (v1.8.48)
```
LBHN 26 001 L1 001      ← Lenke 1, beslag 1
LBHN 26 001 L2 002      ← Lenke 2, beslag 2
LBHN 26 001 L1 Måling 003   ← Lenke 1, lengdemåling
```

Format: `{caseNumber} L{lenkeNr} {beslagNr}`

`formatSeizureRef(sequence, linkIndex)` og
`formatMeasurementSeizureRef(sequence, linkIndex)` tar nå link-indeks
som andre parameter. Alle kallesteder (auto-genererte avvik, manuelt
lagte beslag, ensureDeviation-defaults) sender med riktig indeks.

Sekvensnummeret er fortsatt GLOBALT per sak (001, 002, 003...) — det
spilles ikke om for hver lenke. Slik kan man enkelt referere til
"beslag 001" uavhengig av hvilken lenke det tilhører, mens
lenke-prefikset viser tilhørighet.

---

## 2. Fjern lenke — `×` på hver lenke-fane

Hver lenke-fane har nå en `×`-knapp (når > 1 lenke eksisterer). Klikk:

1. **Bekreft-dialog**: «Fjern Lenke X og alle tilknyttede avviksrader?»
2. **Rydd opp**:
   - Lenke fjernes fra `controlLinkGroups`
   - Alle avviksrader med `link_group_index === removed` fjernes
   - Alle beslag i seizureReportsState med samme indeks fjernes
   - Resterende lenker re-nummeres: lenker > removed flyttes en posisjon ned
   - Aktiv lenke-indeks justeres
3. **Hvis kun én lenke igjen**: lenke-modus deaktiveres automatisk
4. **Re-rendrer** kontrollpunkter og beslagsrapport
5. **Auto-lagrer** med status «Lenke fjernet»

Den siste lenken kan ikke fjernes (knappen vises ikke når `count === 1`).

---

## 3. Eksempel-nummer i hjelpetekst

Lenke-toolbarens hjelpetekst viser nå konkrete eksempel-nummer slik bruker
forstår formatet umiddelbart:

```
Valgt lenke får egen kontrollpunktliste/avviksrader og egne
beslagsnumre (f.eks. LBHN 26 001 L1 001, LBHN 26 001 L2 002).
Start- og stopposisjon følger beslagene i rapportene.
```

---

## 4. Lengdemåling: maksimalmål-felt kun i maks-område

### Problem
Tidligere viste lengdemåling-seksjonen ALLTID både `Gjeldende minstemål`-
og `Gjeldende maksimumsmål`-felt. Maksimumsmål gjelder kun i spesifikke
områder (f.eks. Skagerrak-kysten for hummer), så feltet skapte forvirring
ved kontroller utenfor disse områdene.

### Løsning
Ny hjelper `activeMaksimalmalArea()` sjekker `latestZoneResult.hits` mot
mønsteret `/maksimalmal/` på lagets navn/status/beskrivelse, og verifiserer
treffet mot `areaHitMatchesCurrentSelection()` (samme filter som brukes
for å begrense automatiske områdeavvik til relevant fiskeri/redskap).

I `measurementSectionHtml()`:
```javascript
var maksArea = activeMaksimalmalArea();
var itemIsMaksimalmal = String(item.key || '').toLowerCase().indexOf('maksimalmal') !== -1;
var showMaxField = Boolean(maksArea) || itemIsMaksimalmal;
```

`showMaxField` er sant når:
- Kontrolløren faktisk står i et maksimalmål-område som er relevant for
  valgt fiskeri (typisk hummer i Skagerrak)
- ELLER når kontrollpunktet selv er spesifikt maksimumsmål-relatert
  (f.eks. servergenerert `hummer_maksimalmal`-punkt)

Ellers rendres feltet som skjult input (beholder lagret verdi for
bakoverkompatibilitet), og overskriften nevner ikke maksimumsmål.

### Område-context-callout
Når brukeren ER i et maks-mål-område, vises en blå info-callout i
lengdemåling-seksjonen:

```
┌─────────────────────────────────────────────────┐
│ ℹ Maksimalmål-område                            │
│ Kontrollstedet ligger i Hummer - maksimalmål   │
│ område Skagerrakkysten. Maksimumsmål-kontroll  │
│ er aktivert. Hummer over tillatt mål skal      │
│ settes ut igjen.                                │
└─────────────────────────────────────────────────┘
```

### Tilpasset hjelpetekst
Hjelpeteksten under overskriften reagerer på samme flagg:
- Uten maks-område: «… vurderer automatisk under minstemål …»
- I maks-område: «… vurderer automatisk under minstemål og over/på maksimumsmål …»

---

## 5. Fra v1.8.47 (uendret men verifisert)

Følgende fra v1.8.47 er fortsatt aktivt og verifisert:

- ✅ Områdetreff filtreres mot valgt fiskeri/redskap
  (`areaHitMatchesCurrentSelection`)
- ✅ Hummer-områdefilter inkluderer `maksimalmal|minstemal|fredning`-tokens
- ✅ Kontrollpunkt-sortering: redskap/vak → øvrige → område → lengdemåling
- ✅ Start-/stopposisjon kan oppdateres separat per lenke

---

## 6. Filer endret

```
MOD:
  app/static/js/case-app.js
    - formatSeizureRef(sequence, linkIndex)
    - formatMeasurementSeizureRef(sequence, linkIndex)
    - syncDeviationDefaults() bruker link-indeks
    - Auto-avvik-rader bruker link_group_index
    - Manuelt beslag bruker controlLinkActiveIndex
    - renderControlLinkToolbar() viser × per fane
    - Klick-handler for data-link-remove
    - activeMaksimalmalArea() hjelper
    - measurementSectionHtml() betinget maks-felt
    - Område-context-callout

  app/static/styles.css
    +60 linjer for .control-link-tab-remove og .callout.area-info

  app/static/sw.js                — cache-bump
  app/config.py                   — versjon 1.8.48
  alle templates                  — ?v=1.8.48
```

---

## 7. Verifisert (13/13 funksjonelle sjekker passert)

```
✓ formatSeizureRef tar linkIndex
✓ Output har " L1 ", " L2 "-format
✓ formatMeasurementSeizureRef oppdatert
✓ Auto-rad bruker link_group_index
✓ Manuelt beslag bruker controlLinkActiveIndex
✓ Remove-X-knapp på tabs
✓ Remove-handler i toolbar click
✓ Beslag tied to link blir også fjernet
✓ Hjelpetekst viser eksempel-nummer
✓ activeMaksimalmalArea-hjelper finnes
✓ measurementSectionHtml bruker showMaxField
✓ Maks-feltet er skjult når ikke i maks-område
✓ Område-context-melding i lengdemåling
```

Python, Jinja og JS validert syntaktisk.

---

## 8. Versjon

`1.8.47` → `1.8.48`. Alle `?v=1.8.48`. SW-cache `kv-kontroll-1-8-48-static`.
