# Endringer v53

- Bilder lagres local-first på enheten og synkes senere til server.
- OCR bruker lokal kopi for raskere prosessering og kan falle tilbake til server ved behov.
- Lyd lagres local-first og opptak deles i korte segmenter slik at lange intervjuer på 1 time eller mer blir mer robuste.
- Oppsummering og autogenererte tekster viser en rask lokal kladd først og oppgraderes i bakgrunnen.
- Kartet bruker roligere oppdateringer, grovere bbox-cache og lengre cache-tid for mer sømløs bevegelse.
- Lokal media-status viser både bilder og lyd, og eksport/synk prøver å laste opp lokale mediafiler først.
- Standard maks filstørrelse for opplasting er økt til 150 MB.
- Appversjon, service worker og kartlag-cache er oppdatert til v53.
