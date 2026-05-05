# Endringer 1.8.21 - avhør, rapporttekst og bildeanalyse

## Avhør

- Avhør tas nå bare inn i avhørsrapport/dokumentpakke når det enkelte avhøret er merket `Avhør gjennomført - ta med i avhørsrapport`.
- Avhør som ikke er gjennomført, ikke avkrysset eller mangler faktisk forklaring/sammendrag, gir tom avhørsrapport.
- Samlet avhørsutkast bygges bare fra gjennomførte avhør.
- Forhåndsvisningstekst er presisert slik at fravær av avhør ikke fremstår som en ferdig rapport.

## Anmeldelse / egenrapport

- Backend returnerer ikke lenger hele generert egenrapport i fritekstfeltet `notes` ved tekstforslag.
- Fritekstfeltet brukes dermed ikke lenger til å gjenta egenrapporten inne i egenrapporten.
- Genererte standardtekster som har havnet i `notes` fra eldre versjoner filtreres bort.
- Egenrapport er strammet inn med kortere, formell struktur:
  - Tid og sted
  - Kontrolltema
  - Bakgrunn
  - Faktiske observasjoner
  - Tiltak og dokumentasjon
- Anmeldelsen lister lovhjemler kun som korte referanser for registrerte avvik, ikke lange forskriftssitater.

## Person / fartøy - bildeanalyse

- Dersom OpenAI-nøkkel mangler og lokal OCR-reserve heller ikke er tilgjengelig i servermiljøet, returnerer bildeanalysen nå et kontrollert tomt JSON-resultat med `usikkerhet` i stedet for å feile hardt med 503.
- Brukeren får fortsatt redigerbare felt og beskjed om manuell kontroll.

## Cache / versjon

- Versjon bumpet til 1.8.21.
- Service worker-cache og JS/CSS-cache busting er oppdatert til 1.8.21.
