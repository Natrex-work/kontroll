# V1.1 versjonering og verneområder

- Endret intern og synlig versjonering fra v101/101.0.0 til V1.1/1.0.0.
- Oppdatert cache-bust-parametre, service worker-navn og kart-/temalag-cache til V1.1/v1-1 slik at ny JS/CSS skal lastes etter deploy.
- Endret UI-feltet «Forbudsområder» til «Verneområder» i posisjon/kontrolltype.
- Kortet «Kartoversikt» viser nå verneområder og relevante lovregulerte områder for valgt kontroll.
- Strammet klientfiltreringen slik at kart og verneområdeliste kun viser lag som matcher valgt kontrolltype, art/fiskeri og redskap. Fallback som viste alle lag når ingen match fantes er fjernet.
- Filtrerer områdetreff fra /api/zones/check mot samme relevante lag før de brukes i kart, liste og valgfelt.
- Gjorde «Aktuelle temalag og områder» og hvert temalag/område kollapsbart.
- /api/zones/check hentes med cache: no-store fra klienten og returnerer Cache-Control: no-store fra serveren.
- Standardtekst-polering erstatter eventuell tekst «i aktuelt kontrollområde» med nærmeste sted/lokasjon når den finnes, ellers registrert kontrollposisjon.
