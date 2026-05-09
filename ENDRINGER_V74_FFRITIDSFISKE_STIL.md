# Endringer v74 – mobil stil, kart og autofyll

Denne pakken gjør tre hovedting:

- gir appen et mer mobilvennlig uttrykk med tydeligere startside og mykere kart-/handlingskort
- fjerner det blokkerende lagpanelet i kartene og viser aktuelle temalag i en egen liste under kartet
- forbedrer OCR/autofyll slik at etiketter som står på én linje og verdien på neste linje også fylles inn automatisk

## Kart

- temalag-panelet i selve kartet er slått av på mobil
- filterchips over kartet er synlige igjen
- kontrollkartet viser en egen liste over aktuelle områder og prioriterte lag
- oversiktskartet viser samme type liste og oppdateres ved filtervalg og posisjon

## Autofyll

- frontend-parseren støtter nå label på én linje og verdi på neste
- backend-parseren støtter allerede dette og brukes fortsatt på server-OCR
- OCR-resultat fyller skjema direkte før registeroppslag er ferdig
- autofylte felter vises i et eget sammendrag under OCR-feltet

## Utseende

- justert sidehode på kartvisningen
- beholdt horisontal, rullbar toppmeny på mobil
- beholdt MK-profil fra forrige versjon
