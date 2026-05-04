# 1.8.16 - Kontrollpunktbeslag og flyttet Person/fartoy

- Fikset runtime-feil der `seizureReportsState` var deklarert lokalt i init-koden, mens kontrollpunkt-rendering brukte den fra ytre scope. Dette stoppet `Legg til redskap/beslag` etter klikk med `ReferenceError` og gjorde at beslagsraden ikke ble synlig.
- Kontrollpunktavvik kan naa opprette flere beslagslinjer under samme kontrollpunkt, og radene beholder beslagnummer/type/avvik/merknad/bildekobling i samme `findings_json`-struktur.
- Person/fartoy er flyttet til steg 3. Ny hovedstruktur er 1 Roller/grunnlag, 2 Kontrollvalg, 3 Person/fartoy, 4 Posisjon/Kart, 5 Kontrollpunkter, 6 Illustrasjonsrapport/bilder og 7 Avhor/signatur/dokumentpakke.
- Kart- og kontrollpunkt-JS er oppdatert til nye stegkonstanter slik at kart startes paa steg 4 og regler/kontrollpunkter lastes paa steg 5.
- Versjon/cache er bumpet til 1.8.16. Service worker bruker nytt cache-navn, nye asset-URLer, og `/api/rules` samt `/api/zones/check` hentes nettverksdirekte for aa unngaa stale kontrollpunkt- og posisjonsdata.

- Rettet ogsa illustrasjons-preview for opplastede bilder: rapportpakken setter naa preview_url for lagrede evidence-rader, slik at bilder knyttet til beslag/avvik faktisk vises i forhåndsvisningen og ikke bare omtales i beslagsrapporten.
