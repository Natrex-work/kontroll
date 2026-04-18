# V36 endringer – reguleringskart tilbake i kartvisningen

## Hva som er rettet

- Kartlaget for reguleringsområder er koblet mot gjeldende MapServer-endepunkt hos Fiskeridirektoratet.
- GeoJSON-spørringer ber nå eksplisitt om `outSR=4326`, slik at polygonene kommer tilbake i koordinatsystemet Leaflet-kartet forventer.
- Pakkede cachefiler for portal-lag er fjernet, slik at appen ikke starter med gamle reserveflater som skjuler de offisielle lagene.
- Kartmotoren beholder fortsatt lokale reserveflater for hummer, kysttorsk, Oslofjorden, flatøsters, korallrev og Saltstraumen dersom live-kartlag ikke kan hentes.
- Reserveflatene i `data/zones.json` er beholdt og strukturert per lag-id, slik at hvert lag viser riktig reserveområde i stedet for feil blanding av soner.

## Teknisk oppsummering

Endret filer:
- `app/live_sources.py`
- `data/zones.json`
- `app/config.py`
- `app/static/sw.js`

## Praktisk effekt

Når appen har nettilgang skal kartet igjen hente og vise offisielle områder for blant annet:
- hummerfredningsområder
- hummer maksimalmålområde
- kysttorsk stengte områder
- kysttorsk forbudsområde
- Oslofjorden fritidsfiskeregler
- Oslofjorden nullfiskeområder
- flatøsters forbudsområde
- korallrev forbudsområde
- Saltstraumen steinbit

Hvis nettet ikke er tilgjengelig, faller appen tilbake til lokale reserveflater slik at kartet fortsatt viser relevante reguleringssoner.

## Verifisering

- Python-kompilering bestått
- smoke test bestått med `KV_LIVE_SOURCES=0`
- cache for portal-lag ryddet før pakking
