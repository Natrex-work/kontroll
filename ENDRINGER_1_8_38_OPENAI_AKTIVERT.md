# Endringer 1.8.38 — OpenAI Vision aktivert som primær bildeanalyse

## Hva er endret

OpenAI Vision er igjen primær motor for bildeanalyse under Person/Fartøy.
Lokal Tesseract-OCR er nå **automatisk fallback** ved feil — slik at
appen aldri står helt uten analyse selv om OpenAI er nede eller treg.

---

## 1. Ny flyt — robust tre-tier-pipeline

```
┌─────────────────────────┐
│ Bilde lastet opp        │
└────────────┬────────────┘
             ▼
   ┌─────────────────────┐    Hvis API-nøkkel mangler
   │ Har OpenAI-nøkkel?  │ ─NEI──→ Lokal Tesseract OCR
   └─────────┬───────────┘         (med hummer-registeroppslag)
             │ JA
             ▼
   ┌─────────────────────┐    Hvis tomt resultat
   │ OpenAI Vision (gpt) │ ─►(supplér med lokal OCR)
   └─────────┬───────────┘
             │ Suksess  │ Feil/timeout
             │          ▼
             │     ┌─────────────────────┐
             │     │ Lokal Tesseract OCR │
             │     └─────────┬───────────┘
             ▼               ▼
   ┌─────────────────────────────────┐
   │ Hummerregister-oppslag          │  Bekrefter
   │ (tableau.fiskeridir.no)         │  navn + deltakernummer
   └─────────────────────────────────┘
```

### Nøkkelregler
- **Standard**: OpenAI brukes når `KV_OPENAI_API_KEY` er satt
- **Auto-fallback**: ved timeout, HTTP-feil eller tomt resultat brukes
  lokal OCR i stedet
- **Eksplisitt avslag**: `KV_PERSON_FARTOY_USE_OPENAI=0` tvinger lokal
- **Registeroppslag**: kjøres etter begge veier — fyller manglende
  navn/deltakernummer fra Fiskeridirektoratets register

---

## 2. Frontend: tydelig kildemerking

Statusboksen viser nå nøyaktig hvilken kombinasjon som ble brukt:

| Tilstand | Tekst |
|---|---|
| OpenAI + register | **OpenAI bildeanalyse + hummerregister** |
| OpenAI uten register | **OpenAI bildeanalyse** |
| OpenAI feilet → lokal | **Lokal OCR (OpenAI utilgjengelig)** |
| Lokal + register | **Lokal OCR + hummerregister** |
| Lokal uten register | **Lokal OCR (Tesseract)** |

I tillegg setter backend `analysis_source: 'openai'` i resultat-payloaden
så frontend kan rendre meldingen presist.

---

## 3. Robust feilhåndtering

`_analyze_with_openai_vision()` er separert ut som privat funksjon som
kaster ved alle feil. Hovedflyten fanger:

```python
except (RuntimeError, ValueError, httpx.HTTPError, httpx.TimeoutException) as exc:
    logger.warning('OpenAI bildeanalyse feilet, faller tilbake til lokal OCR: %s', exc)
    result = analyze_person_marking_images_local(images)
    usikkerhet.insert(0, 'OpenAI bildeanalyse var ikke tilgjengelig — lokal OCR ble brukt i stedet.')
```

Brukeren merker aldri direkte feil — får alltid et resultat, med tydelig
markering når OpenAI ikke var tilgjengelig.

### Tomt OpenAI-resultat
Hvis OpenAI returnerer alle felt tomme (sjelden, men kan skje med veldig
vanskelige bilder), supplerer vi med lokal OCR per felt:

```python
for field in ('navn', 'adresse', 'postnummer', ...):
    if not result.get(field) and local_result.get(field):
        result[field] = local_result[field]
```

---

## 4. Hummer-registeroppslag på OpenAI-resultat

Lokal pipeline har gjort dette siden v1.8.37; nå kjøres samme
`_enrich_with_registry()` også etter OpenAI:

```python
if not result.get('registry_match'):
    result = _enrich_openai_result_with_registry(result)
```

Dette gir to fordeler:
- **Verifiserer** deltakernummer mot Fiskeridirektoratets register
- **Korrigerer** navn-stavelser hvis OpenAI har lest dem litt feil

---

## 5. Aktivering

For å bruke OpenAI Vision, sett i Render eller `.env`:

```
KV_OPENAI_API_KEY=sk-...
```

Det er det. Ingen andre endringer kreves.

For å tvinge lokal OCR (uten betalt AI):
```
KV_PERSON_FARTOY_USE_OPENAI=0
```

For å justere modell:
```
KV_OPENAI_VISION_MODEL=gpt-4o
```

---

## 6. Filer endret

```
MOD:
  app/services/openai_vision_service.py — ny analyze_person_marking_images
                                           med fallback-flyt, separat
                                           _analyze_with_openai_vision og
                                           _enrich_openai_result_with_registry
  app/static/js/case-app.js              — UI-tekst tilpasset 5 forskjellige
                                           tilstander
  app/static/sw.js                       — versjonsbump
  app/config.py                          — versjon 1.8.38
  alle templates                         — ?v=1.8.38
```

## 7. Versjon

`1.8.37` → `1.8.38`. SW-cache `kv-kontroll-1-8-38-static`.
