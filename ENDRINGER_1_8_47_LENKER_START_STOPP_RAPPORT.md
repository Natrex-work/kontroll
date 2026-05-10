# Endringer 1.8.47 - lenker med start/stopp og egne beslag

## Kontrollpunkter

- Global lenkefunksjon i steg 5 har nå startposisjon, stopposisjon og merknad for valgt lenke.
- Start og stopp kan oppdateres separat med "Bruk posisjon som start" og "Bruk posisjon som stopp".
- Ved "Legg til lenke" opprettes ny lenke med egen fane og eget lenkegrunnlag.
- Avviks-/beslagsrader knyttes til aktiv lenke og får egne beslagsnumre.
- Avviksrader viser tydelig om de tilhører Lenke 1, Lenke 2 osv.
- Hvert kontrollpunkt med avvik viser lenkefaner slik at beslag/avvik for Lenke 1 og Lenke 2 holdes adskilt i brukerflaten.
- Start-/stopposisjon fra valgt lenke kopieres til beslagene som opprettes under lenken.

## Beslagsrapport

- Beslagsrapporten viser nå egen seksjon for lenker med startposisjon, stopposisjon og tilhørende beslag.
- Registrerte beslag grupperes under Lenke 1, Lenke 2 osv.
- Hvert beslag viser hvilken lenke det tilhører.

## Anmeldelse og egenrapport

- Anmeldelsen får kort opplysning om at beslag/redskap er fordelt på flere lenker når dette er registrert.
- Egenrapporten viser tilsvarende at beslag/redskap er fordelt på lenker og at detaljer fremgår av beslagsrapporten.
- Posisjon og start-/stopposisjon gjentas ikke unødvendig i anmeldelse/egenrapport, men henvises til beslagsrapporten.

## Cache / versjon

- Appversjon bumpet til 1.8.47.
- Service worker-cache og statiske ressursversjoner er oppdatert til 1.8.47.
