# Endringer 1.8.37 — Hummerregister-admin og forbedret bildeanalyse

## Hva er endret

To målrettede forbedringer i Person/Fartøy-flyten:

1. **Bildeanalyse uten betalt AI** — vote-basert aggregering med strenge
   feltvalidatorer slik at deltakernr, adresse, navn, postnummer, sted og
   mobilnummer havner i riktig felt med høy presisjon.

2. **Hummerregister-administrasjon** (`/admin/registry`) — lar admin laste
   opp CSV manuelt fra Tableau-visningen til Fiskeridirektoratet, eller
   prøve automatisk live-henting. Cachen brukes til automatisk oppslag når
   et deltakernummer leses fra et bilde.

---

## Ærlig om «100 % nøyaktig»

Ingen OCR-løsning kan garantere 100 % nøyaktighet på håndskrevet tekst,
slitte merker, dårlig lys eller buede flater. Det vi kan gjøre er å
maksimere **presisjon** (få false positives — feltverdier blir ikke fylt
inn med feil data) og bruke **autoritative oppslag** (registre) for å
verifisere det OCR fant.

Den nye løsningen oppnår dette ved:
- Strenge typesjekkere før et felt fylles inn
- Stemmegivning på tvers av flere bilder
- Krysssjekk mot Fiskeridirektoratets hummerregister

Hvis OCR er usikker, fylles ikke feltet ut og det legges en
«Bekreft manuelt»-merknad — slik at brukeren selv leser av merket og
fyller inn riktig verdi.

---

## 1. Forbedret bildeanalyse (lokal OCR)

### Tidligere problem
Den gamle aggregeringen tok **første treff** per felt fra første bilde
som ga utslag. Hvis OCR mistolket et tall som telefon, ble det stående
selv om de andre bildene inneholdt det riktige nummeret.

### Ny aggregator: vote-basert
For hvert felt samler vi opp **alle kandidater** fra alle bilder. Deretter:

1. **Strenge validatorer** filtrerer bort verdier som ikke passer feltet:
   - `mobil`: 8 siffer som starter med 4 eller 9 (norsk mobil)
   - `postnummer`: nøyaktig 4 siffer
   - `poststed`: bare bokstaver, mellomrom og bindestrek
   - `navn`: 2–5 store-første-bokstav-ord, ingen tall
   - `adresse`: minst én bokstav OG minst ett tall (gate + nr)
   - `deltakernummer`: 4–20 alfanumeriske tegn med bindestreker

2. **Vote** velger den hyppigste verdien blant validerte kandidater.
   Like-stemmer brytes etter første-sett rekkefølge og lengde.

3. **Cross-validation**: hvis samme tall havner i både `mobil` og
   `deltakernummer`, beholdes det som mobil og merknad legges til.

4. **Konsensus-måler**: hvis et felt bare ble lest fra under 60 % av
   bildene som faktisk ble OCR-et, legges en «Lav konsensus»-merknad
   slik at brukeren får signal om å verifisere.

### Resultat
- Færre feilplasserte verdier (telefon i deltakernr-feltet osv.)
- Flere korrekte verdier (ekte korrespondanse mellom flere bilder vinner)
- Tydelig signal når OCR er usikker

### Filer
- `app/services/local_marker_analyzer.py` — vote-aggregator + strenge validatorer

---

## 2. Hummerregister-administrasjon

### Ny side: `/admin/registry`
Tilgjengelig fra sidemenyen for brukere med `user_admin`-tilgang.

#### Cache-status
Viser om en deltakerliste er lastet inn:
- Antall deltakere
- Når sist oppdatert (med alder i timer)
- Hvor data kom fra (live-henting eller manuell opplasting)

«Vis eksempler»-knapp henter de 10 første radene som tabell, så admin kan
verifisere at data er korrekt parset.

#### Manuell CSV-opplasting
Tableau-visningen til Fiskeridirektoratet
(`tableau.fiskeridir.no/.../Pmeldehummarfiskarar`) blokkerer ofte
automatisk nedlasting (returnerer 403 til ikke-godkjente klienter).
Løsningen er at admin laster ned CSV manuelt fra Tableau og laster opp
på serversiden:

1. Åpne Tableau-visningen i nettleser
2. Klikk «Last ned» → velg «Crosstab» eller «Data» som format → CSV
3. Last opp filen i admin-UI
4. Server parser, normaliserer og lagrer i samme cache som live-henting

Parseren håndterer:
- UTF-8, UTF-8 BOM, UTF-16, ISO-8859-1, CP1252
- Semikolon, komma, tabulator, pipe som skilletegn (auto-detektert)
- Norske og engelske kolonneoverskrifter (`navn`, `namn`, `name`,
  `deltakarnummer`, `deltakernummer`, `participant_no`, `type fiskar`,
  `fisher_type`, `sesong`, `år`, `year`)
- Ulike formater for deltakernummer (`H-2024-001`, `2024001`, `ABC-DEF-123`)

#### Live-henting (forsøk)
«Prøv live-henting nå»-knapp kjører `refresh_hummer_registry_cache(force=True)`
som forsøker:
1. Tableau CSV-eksport-URLer (`?:format=csv`, `.csv`)
2. Fall-back til scraping av offentlig statistikkside

Hvis Tableau svarer 403 (vanlig), faller den tilbake til offentlige
sider. Hvis ingen kilde fungerer, vises feilmelding og admin må bruke
manuell opplasting.

#### Tøm cache
For å rense feilaktig importert data eller starte på nytt.

### Audit
Alle handlinger logges i audit-loggen:
- `hummer_registry_upload` (med antall rader og filnavn)
- `hummer_registry_live_refresh` (med antall rader)
- `hummer_registry_clear`

---

## 3. Auto-oppslag i Person/Fartøy-flyt

Eksisterende `_enrich_with_registry()` i `local_marker_analyzer.py` slår
opp deltakernummer i hummerregisteret etter OCR. Den fant allerede sted i
v1.8.34, men nå med en større og mer pålitelig kilde:

1. OCR finner deltakernummer på bildet
2. Server slår opp i `hummer_registry_cache.json` (lastet via admin eller live)
3. Hvis treff: navn fra registeret er **autoritativt** og overstyrer OCR
   (mindre risiko for feillesing)
4. Hvis OCR-navn og register-navn er forskjellige: merknad legges til så
   admin kan verifisere
5. Hvis ingen treff: liste over kandidater foreslås

---

## 4. Filer endret

```
NY:
  app/templates/admin_registry.html         — admin-flate for register

MOD:
  app/routers/admin.py                      — 4 nye endepunkter:
                                                /admin/registry
                                                /admin/registry/hummer/upload
                                                /admin/registry/hummer/refresh
                                                /admin/registry/hummer/clear
                                                /admin/registry/hummer/sample.json
  app/services/local_marker_analyzer.py     — vote-aggregator + validatorer
  app/ui.py                                 — nav-link til /admin/registry
  app/static/styles.css                     — +85 linjer for register-UI
  app/static/sw.js                          — versjons-bump
  app/config.py                             — versjon 1.8.37
  alle templates                            — ?v=1.8.37
```

## 5. Versjon

`1.8.36` → `1.8.37`. Alle `?v=1.8.37`. SW-cache `kv-kontroll-1-8-37-static`.

## 6. Bruksinstruksjoner for admin

For å aktivere automatisk oppslag av deltakernummer:

1. **Logg inn som admin**
2. **Gå til Hummerregister** i sidemenyen (eller `/admin/registry`)
3. **Last ned CSV** fra
   [Tableau-visningen](https://tableau.fiskeridir.no/t/Internet/views/Pmeldehummarfiskarargjeldander/Pmeldehummarfiskarar):
   - Klikk «Last ned» (Download) i Tableau-verktøylinjen
   - Velg «Crosstab» → CSV → lagre filen
4. **Last opp** filen i admin-UI
5. **Verifiser** med «Vis eksempler»-knappen

Etter dette vil alle Person/Fartøy-bilder med synlig deltakernummer
automatisk få fylt ut navn (og evt. annen registerinfo) ved OCR.
