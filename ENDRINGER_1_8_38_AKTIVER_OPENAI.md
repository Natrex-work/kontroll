# Endringer 1.8.38 — OpenAI Vision aktivert som primær bildeanalyse

## Hva er endret

OpenAI Vision er nå **primær bildeanalyse** når API-nøkkel er
konfigurert på serveren. Lokal Tesseract OCR brukes som automatisk
fallback hvis OpenAI ikke er tilgjengelig eller mislykkes.

Hummerregister-oppslag (Fiskeridirektoratet via tableau.fiskeridir.no)
kjøres på resultatet **uansett kilde** — så deltakernummer + navn
auto-bekreftes.

---

## 1. Slik aktiverer du OpenAI Vision

Sett miljøvariabel i Render (eller `.env`):

```
KV_OPENAI_API_KEY=sk-...
```

(Alternative variabelnavn som også støttes: `OPENAI_API_KEY`,
`OPENAI_KEY`, `KV_OPENAI_API_KEY_FILE`.)

Restart applikasjonen. Det er alt.

### Valgfri konfigurasjon

```
KV_OPENAI_VISION_MODEL=gpt-4o          # default
KV_OPENAI_VISION_MAX_IMAGES=4          # max bilder per analyse
KV_OPENAI_VISION_MAX_OUTPUT_TOKENS=1200 # respons-størrelse
```

### Slik deaktiverer du midlertidig

```
KV_PERSON_FARTOY_USE_OPENAI=0
```

(Beholder API-nøkkel, men tvinger lokal OCR. Nyttig for testing eller
når OpenAI-tjenesten har problemer.)

---

## 2. Synlig statusindikator

Et nytt **statusbånd** vises automatisk over «Kjør bildeanalyse»-knappen
i Person/Fartøy-seksjonen. Det viser hvilken pipeline som vil brukes
**før** du sender bildet:

| Tilstand | Visning |
|---|---|
| OpenAI aktiv | 🤖 **OpenAI Vision** — Avansert AI-analyse (modell: gpt-4o) |
| Ingen API-nøkkel | 📷 **Lokal Tesseract OCR** — Sett miljøvariabel KV_OPENAI_API_KEY for å aktivere OpenAI Vision. |
| API-nøkkel deaktivert | 📷 **Lokal Tesseract OCR** — OpenAI-nøkkel er konfigurert, men er deaktivert via KV_PERSON_FARTOY_USE_OPENAI=0. |

Statusbåndet hentes via det nye API-endepunktet
`GET /api/person-fartoy/analyzer-status` som returnerer:

```json
{
  "primary": "openai" | "local",
  "primary_label": "OpenAI Vision" | "Lokal Tesseract OCR",
  "primary_detail": "...",
  "openai_active": true | false,
  "openai_key_source": "OPENAI_API_KEY" | "",
  "fallback": "local" | null,
  "registry_lookup_active": true,
  "registry_source": "Fiskeridirektoratet — registrerte hummerfiskere"
}
```

---

## 3. Hvordan analysen flyter (uendret fra v1.8.37)

```
┌──────────────────────────────────────────────────┐
│ 1. Bilde lastes opp                              │
└──────────────────────────────────────────────────┘
                       ↓
┌──────────────────────────────────────────────────┐
│ 2. Velg primær pipeline:                         │
│    • API-nøkkel satt? → OpenAI Vision             │
│    • Ingen nøkkel?    → Lokal Tesseract           │
└──────────────────────────────────────────────────┘
                       ↓
┌──────────────────────────────────────────────────┐
│ 3. Hvis OpenAI valgt:                            │
│    • Send til /v1/responses med JSON-skjema       │
│    • Ved feil → fall tilbake til lokal OCR        │
│    • Ved tomt resultat → suppler med lokal OCR    │
└──────────────────────────────────────────────────┘
                       ↓
┌──────────────────────────────────────────────────┐
│ 4. Hummerregister-oppslag (begge pipelines):     │
│    • Sjekk deltakernummer mot Fiskeridirektoratet │
│    • Tableau.fiskeridir.no → bootstrapSession     │
│    • HTML-fallback om Tableau blokkerer           │
│    • Marker `registry_match: true` ved treff      │
└──────────────────────────────────────────────────┘
                       ↓
┌──────────────────────────────────────────────────┐
│ 5. Returner JSON med:                            │
│    {navn, adresse, postnummer, poststed,          │
│     mobil, deltakernummer, annen_merking,         │
│     usikkerhet, analysis_source,                  │
│     registry_match, registry_source}              │
└──────────────────────────────────────────────────┘
```

---

## 4. Frontend-tilbakemelding

Etter at analysen er fullført vises:

- **🤖 OpenAI bildeanalyse brukt** — info-callout (grønn) når OpenAI ble
  brukt
- **✓ Bekreftet i hummerregisteret** — suksess-callout (grønn) når
  deltakernummer ble auto-bekreftet
- **Kildelinje** under Bildeanalyse-knappen oppdateres til
  `OpenAI bildeanalyse + hummerregister` (eller varianter avhengig av
  hva som lyktes)

---

## 5. Filer endret

```
MOD:
  app/routers/api.py                — nytt /api/person-fartoy/analyzer-status
                                       endepunkt
  app/static/js/case-app.js         — henter og viser pipeline-status,
                                       injecter status-bånd ved knappen
  app/static/styles.css             — .person-analyzer-status-styling
  app/static/sw.js                  — cache-bump
  app/config.py                     — versjon 1.8.38
  alle templates                    — ?v=1.8.38
```

## 6. Filer bevisst IKKE endret

- `app/services/openai_vision_service.py` — pipelinen var allerede
  bygget for auto-aktivering ved API-nøkkel (v1.8.37)
- `app/services/local_marker_analyzer.py` — fortsetter som fallback
- `app/live_sources.py` — Tableau bootstrapSession-scrape uendret
- `app/templates/case_form.html` — case-form aldri rørt
- DB-skjema, sync-orkestrator, kart-side

---

## 7. Versjon

`1.8.37` → `1.8.38`. Alle `?v=1.8.38`. SW-cache `kv-kontroll-1-8-38-static`.
