# Endringer v51

- Ny kontroll er flyttet øverst på hjemmeskjermen.
- OCR- og illustrasjonsbilder lagres nå først lokalt på enheten med IndexedDB.
- OCR kjører nå lokal tekstlesing først og faller bare tilbake til server-OCR ved behov.
- OCR-bilder kan brukes videre i illustrasjonsrapporten mens de synkes til server i bakgrunnen.
- Illustrasjonsbilder og inline bildebevis vises umiddelbart i saken som "lagret lokalt" før opplasting er ferdig.
- Det er lagt inn egen synk-knapp for lokale bilder og automatisk bakgrunnssynk når nettverket er tilgjengelig.
- Forhåndsvisning og eksport forsøker å synke lokale bilder før dokumentene åpnes eller eksporteres.
- Service worker/cache er oppdatert til v51.
