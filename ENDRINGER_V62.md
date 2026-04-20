# Endringer i v62 – kartytelse og offline-kart

- Ny offline-kartpakke for kontrollkartet via `/api/map/offline-package`
- Utvidet offline-område rundt gjeldende kartutsnitt
- Lokal lagring av beste dekningsområde i IndexedDB
- Forhåndslagring av OSM- og fiskerikartbilder til cache
- Mindre og raskere kartpayload ved å trimme unødvendige attributter
- Server-side bundle-cache for raskere gjentatte kartkall
- Roligere oppfrisking av kart ved pan/zoom
