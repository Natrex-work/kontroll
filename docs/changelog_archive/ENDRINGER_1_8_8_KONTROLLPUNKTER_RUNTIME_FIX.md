# Endringer 1.8.8 - kontrollpunkter vises igjen

- Rettet runtime-feil der `person-mode-hint` manglet i skjemaet, men ble brukt av `case-app.js`.
- La inn null-sikring slik at manglende hjelpetekst-element ikke stopper resten av appen.
- Kontrollpunkter lastes nå også når bare deler av kontrolltype/art/redskap er valgt.
- Ved åpning av steg 4 vises lokale relevante kontrollpunkter umiddelbart mens `/api/rules` hentes.
- `/api/rules` hentes med `cache: no-store` for å unngå gammel regelpakke fra nettleser/PWA-cache.
- Lokal fallback er merket `1.8.8 fallback`.
- Versjon, service worker og JS/CSS cache-bust er bumpet til 1.8.8.
