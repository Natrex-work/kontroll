# Endringer 1.8.30 - brukerstyring og 2-trinns SMS-login

- Rettet brukerstyring slik at opprettelse/oppdatering av brukere håndterer valideringsfeil og databasefeil uten serverkrasj.
- Duplikat e-post gir tydelig feilmelding i adminflaten.
- Ikke-adminbrukere må ha registrert norsk mobilnummer.
- Ikke-adminbrukere må logge inn med passord + engangskode sendt på SMS.
- Adminbrukere er unntatt 2-trinnskravet, slik at administrasjon fortsatt er mulig ved SMS-feil.
- Lagt til OTP-tabell, kodeutløp, maks antall kodeforsøk og rate limiting for SMS-utsending.
- Lagt til Twilio-basert SMS-tjeneste via miljøvariabler.
- Lagt til egen side for engangskode med iPhone/Safari-vennlig input og autocomplete=one-time-code.
- Oppdatert Render/.env-eksempler med nødvendige SMS/OTP-variabler.
