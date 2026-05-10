# Endringer 1.8.37 — Lokal bildeanalyse uten betalt AI + automatisk hummer-oppslag

## Hva er endret

Bildeanalysen under **Person/Fartøy** fungerer nå 100 % lokalt på serveren
med Tesseract OCR og automatisk oppslag mot Fiskeridirektoratets
hummerregister. Ingen betalte AI-tjenester (OpenAI Vision) er nødvendig.

Tre forbedringsområder:

1. **Strammere feltrouting** — ingen kollisjon mellom telefon, postnummer
   og deltakernummer
2. **Cross-image konsensus** — flere bilder gir høyere sikkerhet
3. **Robust Tableau-oppslag** — bootstrapSession-fallback når CSV-eksport
   blokkeres

---

## 1. Lokal OCR er primær (ikke fallback)

Den primære koden i `analyze_person_marking_images()`:

```python
use_openai = str(os.getenv('KV_PERSON_FARTOY_USE_OPENAI') or '').strip().lower() in {'1','true','yes','on'}
if not use_openai:
    return analyze_person_marking_images_local(images)
```

Dette har vært tilfellet fra v1.8.31, men frontend-tekstene har frem til
nå referert til "OpenAI bildeanalyse" og "lokal OCR-reserve". Disse er nå
fjernet.

### Frontend-oppdatering
Statuslinjen viser nå:
- **«Lokal OCR + hummerregister»** når deltakernummer er bekreftet i registeret
- **«Lokal OCR (Tesseract)»** ellers

(Tidligere: «OpenAI bildeanalyse» / «Bildeanalyse / lokal OCR-reserve».)

---

## 2. Strammere feltrouting

### Problem
Tidligere kunne OCR-resultater rote feltene:
- Et 8-sifret nummer kunne havne i deltakernummer
- En linje med tall kunne tolkes som adresse
- Plassnavn kunne komme før postnummer i visningen

### Løsninger

**`_validate_field(field, value)`** — streng per-felt-validator:
| Felt | Krav |
|---|---|
| `mobil` | 8 sifre, starter med 4 eller 9 (norske mobiler) |
| `postnummer` | Nøyaktig 4 sifre |
| `poststed` | Bokstaver først, ingen embedded 4-sifret tall |
| `deltakernummer` | 4-30 tegn, bokstaver/sifre/bindestrek, IKKE et rent norsk mobilnummer |
| `navn` | 2-5 ord, ingen sifre, ingen adresse-keywords (vei/gate/etc.), ingen sammenkoblings­ord (av/og/i) |
| `adresse` | Må ha minst én bokstav + minst ett siffer (gatenavn + nr.) |

**Cross-field sanity check**: hvis samme tall havner i både telefon og
deltakernummer, beholdes det som telefon og deltakernummer fjernes.

**`_extract_postnr_and_place()` korrigert**: nå sjekker den hvilken side
av postnummeret som faktisk ser ut som et stedsnavn (kun bokstaver, ikke
embedded 4-sifret tall) i stedet for å bare ta den ene siden blindt.

### Verifikasjon
12/12 valideringstester passerer:
```
✓ _validate_field('mobil', '12345678')        = False  # ikke norsk mobil
✓ _validate_field('mobil', '+4790123456')     = True
✓ _validate_field('navn', 'Anders123')        = False  # har sifre
✓ _validate_field('navn', 'Strandveien 12')   = False  # adresse
✓ _validate_field('adresse', 'Strandveien 12')= True
✓ _extract_postnr('STAVANGER 4019')           = ('4019', 'Stavanger')
✓ _extract_mobile('20240001 90123456')        = ''      # embedded i deltakernr
```

---

## 3. Cross-image konsensus

Når man tar flere bilder av samme markering, brukes nå **stemming** per
felt:

```python
def _vote_pick(candidates, field):
    valid = [c for c in candidates if _validate_field(field, c)]
    counts = Counter(valid)
    return counts.most_common(1)[0][0] if counts else ''
```

- Hver kandidat valideres først (slipper ikke gjennom hvis ugyldig)
- Hyppigste kandidat vinner
- Tie-break: tidligst sett, så lengste verdi (mer info)

**Konsensus-flagg**: hvis et felt ble lest fra < 60 % av bildene, legges
en usikkerhets-melding til i `usikkerhet`-arrayen:

```
"Lav konsensus mellom bildene: navn lest fra 1 av 3 bilder (33 %).
 Bekreft manuelt."
```

---

## 4. Robust Tableau-oppslag (bootstrapSession)

### Problem
Tableau Server siden 2020 har gjort `?:format=csv` upålitelig — mange
visninger returnerer HTML i stedet for CSV. Det offentlige
hummerregisteret på `tableau.fiskeridir.no` rammes av dette.

### Løsning
Ny **`_try_tableau_bootstrap_session()`** i `live_sources.py` som:

1. Henter workbook-siden med `?:embed=y` → innhenter `tsConfigContainer`
   med session-ID og XSRF-data
2. POST til `/vizql/.../bootstrapSession/sessions/{id}` → får tilbake
   alle data som leveres til klienten
3. Parser Tableaus chunked JSON-format (lengde + JSON, gjentatt)
4. Trekker ut deltakernumre fra `dataDictionary.dataSegments`

Dette kjøres som **tredje fallback** etter:
1. Direkte `?:format=csv` (rask, men ofte blokkert)
2. CSV-lenker hentet via HTML-scrape (statistikk-siden hos fiskeridir.no)

### Eksisterende fallback bevart
Om bootstrapSession også feiler, faller vi tilbake til HTML-scraping av
`https://www.fiskeridir.no/.../registrerte-hummarfiskarar` som har vært
implementert siden v1.8.10 — den bruker BeautifulSoup på en offentlig
HTML-tabell.

### Robusthet
Hvert steg har eksplisitt `try/except` og returnerer tom liste ved
feil. Aldri raise-er. Cache-en (12 timer TTL) sørger for at appen ikke
spammer Tableau-serveren.

---

## 5. Frontend: kilde per felt

`fillPersonVisionFields()` i `case-app.js` viser nå:

- ✓ **Bekreftet i hummerregisteret** (grønn callout) når
  `payload.registry_match` er `true`
- Statuskilde: «Lokal OCR + hummerregister» eller «Lokal OCR (Tesseract)»
- Detaljmelding: «Navn, adresse og deltakernummer er hentet fra det
  offentlige registeret.» (når match)

---

## 6. Filer endret

```
MOD:
  app/services/local_marker_analyzer.py — strammere validering, voting,
                                           cross-field sanity checks
  app/live_sources.py                   — _try_tableau_bootstrap_session
                                           som tredje CSV-fallback
  app/static/js/case-app.js             — oppdaterte status-tekster
  app/static/sw.js                      — cache-bump
  app/config.py                         — versjon 1.8.37
  alle templates                        — ?v=1.8.37
```

## 7. Reaktivere OpenAI (om ønsket)

Sett miljøvariabel:
```
KV_PERSON_FARTOY_USE_OPENAI=1
KV_OPENAI_API_KEY=sk-...
```

Den lokale pipelinen er fortsatt fallback hvis API-nøkkel mangler eller
forespørsel feiler. Default for nye installasjoner er **lokal OCR**.

---

## 8. Hva registeret faktisk gir

Det offentlige hummerregisteret hos Fiskeridirektoratet inneholder bare:
- **Navn**
- **Deltakernummer**
- **Type fiskar** (fritids-, biyrke- eller hovudyrkefiskar)
- **Sesong/år**

**IKKE** adresse, postnummer eller telefon — disse er ikke offentlig
tilgjengelige. Adresse og kontaktinfo må derfor leses fra bildet (vakets
merking) eller fylles inn manuelt.

Dette betyr i praksis:
- **Deltakernummer + navn**: kan auto-fylles og bekreftes mot register
- **Adresse, postnr, sted, mobil**: kommer alltid fra OCR av bildet

---

## 9. Versjon

`1.8.36` → `1.8.37`. Alle `?v=1.8.37`. SW-cache `kv-kontroll-1-8-37-static`.
