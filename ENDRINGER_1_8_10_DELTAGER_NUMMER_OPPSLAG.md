# Endringer 1.8.13 - deltaker- og nummeroppslag

## Mål
Forbedre manuelt søk på mobilnummer og hummerdeltakernummer uten at eksterne kilder overstyrer OCR automatisk.

## Endret
- Lagt til knapp `Søk deltakernummer` i Person / fartøy.
- Mobilnummeroppslag sender nå eksplisitt `lookup_mode=phone` og bruker `cache: no-store`.
- Deltakersøk sender nå eksplisitt `lookup_mode=participant` og prioriterer direkte treff i hummerregister/lokal hurtigbuffer.
- Registeroppslag skiller tydeligere mellom deltakeroppslag, mobiloppslag og generelt oppslag.
- `controlLinkToolbar`-runtimefeilen fra 1.8.9 er inkludert i denne pakken.
- Versjon/cache er bumpet til 1.8.13.

## Ikke endret
- OCR starter fortsatt ikke eksterne katalogoppslag automatisk.
- 1881/Gulesider brukes fortsatt bare ved manuelt mobilnummeroppslag.
