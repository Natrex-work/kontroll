# V40 endringer

## Kart og posisjon
- Stabilisert kartoppdatering ved at Leaflet-kartet gjenbrukes i stedet for å opprettes på nytt for hver oppdatering.
- Lagt til separat blå posisjonsprikk med nøyaktighetssirkel for enhetens faktiske GPS-posisjon.
- Kontrollposisjon vises som egen nål, og kan settes manuelt ved å trykke i kartet eller dra nålen.
- Når GPS ikke er tilgjengelig, kan bruker likevel sette kontrollposisjon manuelt direkte i kartet.

## Saksnummer
- De tre siste sifrene i saksnummeret kan nå endres manuelt uten å påvirke prefix og år.
- Doble saksnummer stoppes med tydelig feilmelding.

## Forhåndsvisning
- Forhåndsvisning åpnes i ny fane fra sakssiden.
- Lagt til tydelig og sticky knapp for å gå tilbake til saken i forhåndsvisningen.

## Drift / testing
- Lagt til /healthz-endepunkt for enklere health checks.
- Lagt til Dockerfile og .dockerignore for Render/Docker-testing.
