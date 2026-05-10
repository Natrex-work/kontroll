# Endringer i v73 MK

Denne pakken inneholder følgende hovedendringer:

- KV-logo/badge er endret til MK i appen og i PWA-ikonene.
- Toppmenyen på mobil er gjort om til en sideveis rullbar meny.
- Kartets temalag/overlay er justert slik at kartet ikke blokkeres like lett av lagpanelet.
- Ny kontroll oppretter nå aktiv sak via `/cases/new` med løpende LBHN-nummer med en gang.
- OCR/autofyll under Person/Fartøy er forbedret for bilde og kamera, med mer aggressiv utfylling av navn, adresse, poststed, deltakernummer og mobil.
- Registertolking på serveren er utvidet med flere etiketter for persondata.

Verifisert:
- Python-filer kompilerer.
- JavaScript-filer består syntakssjekk.
- Appen starter lokalt med TestClient.
- Innlogging og opprettelse av ny sak med aktivt LBHN-nummer fungerer i lokal test.
