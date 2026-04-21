# Endringer i v63 – offline-kartpakker

Denne versjonen utvider offline-kart med flere lagrede områder som egne pakker.

## Nytt i v63

- flere kartområder kan lagres som egne offline-kartpakker på enheten
- oversikt over lagrede pakker i både kontrollkart og Kart og Område
- hver pakke viser område, antall lag, kartobjekter, kartbilder og sist oppdatert
- knapper for å:
  - vise område i kartet
  - oppdatere pakken
  - slette pakken
- gamle pakker ryddes automatisk bort når de blir for gamle eller når det er for mange
- eldre pakker oppdateres automatisk i bakgrunnen når enheten er online
- tilhørende kartbilder slettes også når en pakke fjernes
- cache og service worker oppdatert til v63

## Standardregler for vedlikehold

- maks 8 offline-kartpakker per enhet
- pakker eldre enn 30 dager slettes automatisk
- pakker eldre enn 7 dager markeres som bør oppdateres

## Tekniske detaljer

- IndexedDB-skjema for lokalt kartlager er oppdatert
- egne pakke-metadata lagres sammen med bundle-data og tile-URLer
- kontrollkart og oversiktskart bruker samme lokale pakkeoversikt
