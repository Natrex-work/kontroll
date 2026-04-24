# Endringer v78 - topplinje og meny

Denne versjonen rydder mobilnavigasjonen slik brukeren beskrev:

- bunnmenyen med Hjem / Ny / Kart / Regler / Saker er fjernet
- hamburger-ikonet med tre streker er fjernet
- MK-badgen i topplinjen er nå menyutløser på mobil
- hovedfunksjonene åpnes som en horisontal rullemeny øverst når man trykker på MK
- toppfeltet har egne tilbake/frem-knapper på vanlige sider
- i kontrollsaken brukes stegknappene videre øverst, mens egen nettleserhistorikk skjules for å spare plass
- visningsnavn for organisasjonen normaliseres til Minfiskerikontroll hvis gammel verdi som starter med Fiskeridirektoratet fortsatt ligger i miljøet

Kontrollert lokalt:

- Python kompilerer
- smoke_test.py går grønt
- render_smoke_test.py går grønt
- common.js består syntakksjekk
- case-app.js består syntakksjekk
