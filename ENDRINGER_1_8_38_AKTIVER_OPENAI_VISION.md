# Endringer 1.8.38 — OpenAI Vision aktivert som primær bildeanalyse

## Hva er endret

OpenAI Vision er nå **primær motor** for bildeanalyse under Person/Fartøy.
Lokal OCR (Tesseract) brukes automatisk som backup når API-nøkkel mangler
eller OpenAI feiler. Hummerregister-oppslag kjøres etter begge.

## Beslutningsflyt

```
Bilde lastet opp
       │
       ├─► API-nøkkel satt? ──► Nei ─► Lokal OCR + hummerregister
       │                       
       │   Ja, USE_OPENAI=0 ──► Lokal OCR + hummerregister
       │                       
       └─► Ja, default      ──► OpenAI Vision
                                    │
                                    ├─► Feil/timeout ─► Lokal OCR + register
                                    │                   (med usikkerhets-merknad)
                                    │
                                    ├─► Tomme felt   ─► Suppler m/ lokal OCR
                                    │
                                    └─► Suksess      ─► Hummerregister-oppslag
                                                        for navn + deltakernr
```

## Konfigurasjon

### Aktivere OpenAI (default når API-nøkkel satt)
Sett i Render eller `.env`:
```
KV_OPENAI_API_KEY=sk-proj-...
```

Det er alt som trengs. OpenAI Vision blir automatisk brukt for alle
påfølgende bildeanalyser.

### Valgfritt: spesifiser modell
```
KV_OPENAI_VISION_MODEL=gpt-4o          # Default
KV_OPENAI_VISION_MAX_IMAGES=4          # 1-8
KV_OPENAI_VISION_MAX_OUTPUT_TOKENS=1200
```

### Tvinge bare lokal OCR (skru av OpenAI midlertidig)
```
KV_PERSON_FARTOY_USE_OPENAI=0
```

## Hva brukeren ser

### I Person/Fartøy-seksjonen

**Når OpenAI er brukt og finner deltakernummer som finnes i registeret:**
- Headline: «OpenAI bildeanalyse fullført og bekreftet mot Fiskeridirektoratet»
- 🤖 Blå callout: «OpenAI bildeanalyse brukt — Avansert AI for håndskrift, slitte merker og dårlig lys.»
- ✓ Grønn callout: «Bekreftet i hummerregisteret»
- Kilde-label: «OpenAI bildeanalyse + hummerregister»

**Når OpenAI er brukt uten registertreff:**
- Headline: «OpenAI bildeanalyse fullført»
- 🤖 Blå callout som over
- Kilde-label: «OpenAI bildeanalyse»

**Når OpenAI feilet og lokal OCR ble brukt:**
- Headline: «Bildeanalyse fullført»
- Usikkerhetsmelding: «OpenAI bildeanalyse var ikke tilgjengelig — lokal OCR ble brukt i stedet.»
- Kilde-label: «Lokal OCR (OpenAI utilgjengelig)»

**Når API-nøkkel mangler / ikke konfigurert:**
- Lokal OCR brukes uten advarsel (ingen feil — det er en gyldig konfig)
- Kilde-label: «Lokal OCR (Tesseract)» eller «Lokal OCR + hummerregister»

## Teknisk detalj

### `analyze_person_marking_images(images)` i `openai_vision_service.py`

Ny beslutningsflyt:

1. **API-nøkkel sjekk**: `_first_configured_api_key()` ser etter
   `OPENAI_API_KEY`, `KV_OPENAI_API_KEY`, eller `OPENAI_KEY`
2. **Opt-out sjekk**: hvis `KV_PERSON_FARTOY_USE_OPENAI=0/false/no/off`,
   tving lokal
3. **Hvis ikke OpenAI**: ren lokal pipeline
4. **Hvis OpenAI**: prøv `_analyze_with_openai_vision()`
   - **Ved exception** (timeout, HTTP, ValueError): fall tilbake til
     lokal pipeline med usikkerhetsmelding
   - **Hvis tomme felt**: hent inn lokal OCR-resultat for å fylle hull
   - **Suksess**: kjør `_enrich_openai_result_with_registry()` for å
     bekrefte deltakernummer mot hummerregisteret
5. **Sett `result['analysis_source'] = 'openai'`** så frontend kan vise
   riktig kilde-label

### Hummerregister-anrikning på begge stier

Funksjonen `_enrich_with_registry()` i `local_marker_analyzer.py` brukes
nå både fra:
- Den lokale OCR-pipelinen (kalt direkte)
- OpenAI-flyten (via `_enrich_openai_result_with_registry()`)

Det betyr at uansett hvilken motor som leste bildet, blir
deltakernummer + navn bekreftet mot Fiskeridirektoratet's offentlige
register.

### Auto-fallback ved tomme OpenAI-resultater
Hvis OpenAI returnerer alle felt tomme (kan skje ved svært dårlig
bildekvalitet), forsøkes lokal OCR i tillegg, og verdier supleres uten
å overskrive eventuelle ikke-tomme OpenAI-felt.

## Kostnad og sikkerhet

- OpenAI Vision koster typisk $0.01-0.03 per bilde med `detail: high`
- API-nøkkel lagres i miljøvariabler — aldri i kode eller logger
- Bildet sendes som base64 over HTTPS til `api.openai.com/v1/responses`
- `store: false` settes i payload så OpenAI ikke lagrer bildet
- `temperature: 0` sikrer deterministisk ekstraksjon
- Strict JSON schema validation — OpenAI tvinges til å returnere kun
  de definerte feltene

## Filer endret

```
MOD:
  app/services/openai_vision_service.py — ny analyze-flyt med 
                                           auto-fallback og registry-
                                           anrikning
  app/static/js/case-app.js              — viser OpenAI-badge når brukt,
                                           riktig kilde-label
  app/static/sw.js                       — cache-bump
  app/config.py                          — versjon 1.8.38
```

## Versjon

`1.8.37` → `1.8.38`. Alle `?v=1.8.38`. SW-cache `kv-kontroll-1-8-38-static`.
