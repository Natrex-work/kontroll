# Endringer 1.8.18 - Person/Fartøy bildeanalyse

## Person / Fartøy

- Endret Person/Fartøy-steg fra ren bildevedlegg-flyt til bildeanalyse av merke, vak, blåse og redskap.
- Kamera på iPhone/Safari trigges via native filinput:

  ```html
  <input type="file" accept="image/*,.heic,.heif" capture="environment">
  ```

- Bruker kan ta flere bilder ved å trykke «Ta bilde» flere ganger, eller velge flere bildefiler via «Legg ved bilde».
- Bilder forhåndsvises som kort med miniatyr og kan fjernes fra analyseutvalget.
- «Analyser bilde» sender alle valgte bilder til nytt backend-endepunkt.
- Analysefelt vises separat med:
  - navn
  - adresse
  - postnummer
  - poststed
  - mobil
  - deltakernummer
  - annen_merking
  - usikkerhet
- Usikre felt markeres visuelt og med `aria-invalid`.
- Alle analysefelter kan redigeres manuelt.
- Redigerte analysefelter synkes til eksisterende Person/Fartøy-felter før lagring.
- Bildene lagres fortsatt som vedlegg til illustrasjonsrapporten.

## Backend

- Ny service:

  ```text
  app/services/openai_vision_service.py
  ```

- Nytt API-endepunkt:

  ```text
  POST /api/person-fartoy/analyze-image
  ```

- Endepunktet tar imot ett eller flere bilder (`files`).
- Bildene valideres som JPG/PNG/WEBP/HEIC/HEIF.
- Serveren skalerer/komprimerer bilder med PIL før OpenAI-kall:
  - standard maks langside: `KV_OPENAI_VISION_MAX_SIDE=2600`
  - standard JPEG-kvalitet: `KV_OPENAI_VISION_JPEG_QUALITY=92`
- Bildet terskles ikke hardt, slik at håndskrift ikke fjernes.
- OpenAI-kallet bruker Responses API med bildeinput og JSON Schema / structured output.
- Modellen blir bedt om å ikke gjette og returnere tom streng ved uklare felt.
- Backend parser JSON robust og normaliserer alle feltene før svar.
- Hvis API-nøkkel mangler, returnerer endepunktet tydelig 503-feil uten klientkrasj.

## Miljøvariabler

Nye/aktuelle variabler:

```text
OPENAI_API_KEY=
KV_OPENAI_VISION_MODEL=gpt-4.1-mini
KV_OPENAI_VISION_MAX_IMAGES=4
KV_OPENAI_VISION_MAX_IMAGE_MB=16
KV_OPENAI_VISION_MAX_SIDE=2600
KV_OPENAI_VISION_JPEG_QUALITY=92
KV_OPENAI_VISION_TIMEOUT_SECONDS=55
```

`render.yaml` legger inn `OPENAI_API_KEY` som hemmelig verdi (`sync: false`).

## Cache

- Versjon bumpet til `1.8.18`.
- JS/CSS lastes med `?v=1.8.18`.
- Service worker-cache bumpet til `kv-kontroll-1-8-18-static` og `kv-kontroll-1-8-18-map-tiles`.
