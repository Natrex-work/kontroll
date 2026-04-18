# V32 endringer

Denne versjonen retter ønskene under **4. kontrollpunkter** for redskap/avvik.

## Gjennomført

- Endret knappetekst fra **Legg til teine / redskap** til **Legg til Redskap**.
- Fjernet den synlige boksen for **Teine/redskap-ID** i avviksradene.
- Lagt inn ny rullegardin **Tidligere redskap i saken** i hver avviksrad.
  - Bruker kan nå velge tidligere registrert redskap fra samme sak.
  - Flere lovbrudd kan dermed knyttes til samme redskap og samme beslag.
- **Beslagsnr.** opprettes fortsatt automatisk fortløpende fra saksnummer/anmeldelsesnummer.
- Når bruker velger et tidligere redskap i menyen:
  - samme beslag brukes videre
  - type redskap hentes automatisk fra valgt redskap
- Beholdt direkte bildebevis fra kontrollpunktet, slik at redskap med flere lovbrudd fortsatt kan få bildebevis uten å forlate steg 4.
- Oppdatert info-boksen under registrerte avvik:
  - forklarer automatisk beslag
  - forklarer valg av tidligere redskap i saken
  - viser tidligere registrerte redskap i samme sak
- Oppdatert sammendragstekst for avviksrader og valgt kontrollpunkt slik at de bygger på beslag + redskapstype, ikke manuelt redskap-ID-felt.
- Oppdatert cache-/appversjon til **v32** slik at nettleseren henter inn ny frontendkode.

## Teknisk verifisering

- JavaScript syntakssjekk: bestått (`node --check`)
- Python kompilering: bestått (`python -m compileall app`)
- Smoke test: bestått med `KV_LIVE_SOURCES=0`
