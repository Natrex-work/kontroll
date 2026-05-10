# Endringer 1.8.36 — Forbedret kart-flate og profesjonelle login-feilmeldinger

## To områder fikset

### 1. Kart og områder — full-bleed, mobil-optimalisert flate
### 2. Login-feilmeldinger — profesjonelt språk + bevart e-postfelt

---

## 1. Kart og områder — redesignet

### Før
- To kart stablet over hverandre: en `<iframe>` til Fiskeridirektoratets
  portal *og* et separat Leaflet-kart. Begge små og forvirrende.
- Brukeren måtte trykke «Bruk min posisjon» for å se hvor de var.
- Lag-velger og offline-pakker tok mye vertikal plass over kartet.
- Status, knapper og info-kort spredt utover siden — ikke mobilvennlig.

### Etter
- **Ett full-bleed Leaflet-kart** som fyller skjermen.
- **Iframe-portal fjernet fra siden** (en liten «Kartportal»-lenke åpner
  den i ny fane hvis ønsket).
- **Auto-posisjonering ved sidelast** hvis nettleseren har lagret
  tillatelse — du ser deg selv på kartet umiddelbart.
- **Floating Action Buttons (FAB)** i kart-hjørnet:
  - 📍 Min posisjon (primær, blå)
  - ⬇️ Lagre offline
  - 🗂️ Vis/skjul kartlag
- **Statusbanner** flyter over kartet (mørk pill nederst), gir alltid
  tydelig tilbakemelding om hva som skjer.
- **Bunnpanel** (`<details>`) med treff-listen og offline-pakker. Lukket
  som standard på mobil for å gi maks kart-areal.
- **Lag-panel-popover** dukker opp når man trykker lag-FAB, lukkes ved
  klikk utenfor.
- **Auto-tellern** i bunnpanelet oppdateres når posisjonssjekken
  finner regulerte områder («3 områder i nærheten»).

### iPhone/iPad-tilpasninger
- Header (`Kart og områder`) komprimeres til en strek på 10 px topp/bunn
  med 1.05 rem h1.
- Topbar's synk-badge skjules på kart-siden for å spare plass.
- Floating buttons reduseres fra 48 → 44 px.
- Bunnpanelet får drag-grip-stripe og kan dras helt åpent (60 vh).
- Safe-area-inset respekteres alle veier (`var(--mk-safe-*)`).

### Hvordan det virker
1. Sidelast → JS sjekker `navigator.permissions.query({name:'geolocation'})`.
2. Hvis tillatelse er **gitt**, kalles `btn-overview-location.click()`
   etter 800 ms — kartet sentrerer seg automatisk på brukeren.
3. Hvis tillatelse er **prompt**, vises melding: «Trykk på 📍-knappen
   for å vise din posisjon.»
4. Hvis tillatelse er **avslått**, vises melding: «Posisjonsdeling er
   avslått. Bruk kartet manuelt eller endre tilgangen i nettleseren.»
5. Når posisjon er tilgjengelig, identifiserer eksisterende kode
   regulerte områder via `/api/zones/check` og fyller bunnpanel-listen.
6. `MutationObserver` på treff-listen oppdaterer telleren live.

### Filer
- **OMSKREVET:** `app/templates/map_overview.html` (76 linjer, kompakt)
- **MOD:** `app/static/js/map-overview.js` (+115 linjer mobile enhancement
  IIFE som kjører etter hovedinit, ingen rewrites av eksisterende kode)
- **MOD:** `app/static/styles.css` (+330 linjer for full-bleed layout,
  FABs, bottom sheet, status banner, layer popover)

### Ikke berørt
- `app/static/js/common.js` — hele `createPortalMap`-infrastrukturen
  brukes uendret.
- `app/static/js/local-map.js` — offline-pakkelogikk uendret.
- Server-endepunkter `/api/zones/check`, `/api/map/*` uendret.

---

## 2. Login-feilmeldinger — profesjonelle og hjelpsomme

### Før (kort, brusk)
| Trigger | Melding |
|---|---|
| Feil passord/epost | «Feil e-post eller passord.» |
| Deaktivert konto | «Brukeren er deaktivert av admin.» |
| Ingen moduler | «Brukeren har ingen aktive moduler. Kontakt admin.» |

### Etter (forklarende, profesjonelt språk)
| Trigger | Melding |
|---|---|
| Feil passord/epost | «Innloggingen mislyktes. Kontroller at e-postadressen og passordet er skrevet riktig, og prøv igjen.» |
| Deaktivert konto | «Brukerkontoen er deaktivert. Kontakt en administrator for å gjenopprette tilgangen.» |
| Ingen moduler | «Brukeren har ingen aktive moduler tildelt. Kontakt en administrator for å få nødvendige tilganger.» |

### Visuell forbedring
- Alert har nå et **info-ikon** ⓘ ved siden av teksten
- Pent gradient-fargekort med myk skygge:
  ```css
  background: linear-gradient(180deg, #fdebec 0%, #faddde 100%);
  border: 1px solid #f4c5c5;
  border-radius: 16px;
  ```
- Tekst er rødbrun (`#911e1e`), god kontrast
- Padding 14×16 px gir luft

### Bevart e-post på feilforsøk
Ved feil innlogging blir e-postfeltet **forhåndsutfylt** med det brukeren
skrev — slipper å skrive den på nytt etter hvert mislykkede forsøk.

### Filer
- **MOD:** `app/routers/auth.py` — tre nye, lengre feilmeldinger og
  passering av `email_value` til templaten
- **MOD:** `app/templates/login.html` — `value="{{ email_value }}"`
  på e-postinput, `.login-alert` med ikon
- **MOD:** `app/static/styles.css` — `.login-alert`-klasse

---

## 3. Sikkerhetsdetaljer

For å unngå å lekke om en e-post finnes i systemet, sier feilmeldingen
fortsatt det samme uavhengig av om brukeren ikke finnes eller passordet
er feil («Innloggingen mislyktes…»). Vi er bare mer høflige om det.

Konto-deaktivert og «ingen moduler» varsles bare når
e-post+passord-kombinasjonen var korrekt — disse er greit å vise eksplisitt.

---

## 4. Versjon

- `app/config.py`: `1.8.35` → `1.8.36`
- `app/static/sw.js`: cache `kv-kontroll-1-8-36-static`
- Alle `?v=1.8.36`

---

## 5. Filer endret

```
MOD:
  app/templates/map_overview.html       — full-bleed redesign (76 linjer)
  app/static/js/map-overview.js         — +115 linjer mobile enhancements
  app/static/styles.css                 — +330 linjer (kart-layout + login)
  app/templates/login.html              — alert med ikon, email_value
  app/routers/auth.py                   — profesjonelle feilmeldinger
  app/static/sw.js                      — cache-versjon
  app/config.py                         — versjon 1.8.36
  alle templates                        — ?v=1.8.36
```

## 6. IKKE endret

- `app/static/js/common.js` (createPortalMap)
- `app/static/js/local-map.js` (offline-pakker)
- `app/static/js/case-app.js`, `case_form.html`
- `app/services/case_service.py`, `app/db.py`
- API-endepunkter `/api/zones/check`, `/api/map/*`
- 2FA-infrastrukturen (fortsatt avskrudd, kan gjenaktiveres via env)
