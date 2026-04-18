# V38 endringer

## Oppsummering og anmeldelsestekst
- Autogenerert oppsummering er skrevet om til en mer formell og kortfattet anmeldelsesstil.
- Teksten settes nå opp punktvis under egne seksjoner for kontrollgrunnlag og registrerte avvik.
- Når avvik er knyttet til beslagnummer, beskrives forholdene nå per beslagnummer.
- Hvert beslagpunkt oppsummerer hvilke konkrete avvik som ble registrert på redskapet eller målingen.
- Hvert beslagpunkt avsluttes med en kort setning om hvilket forhold som danner grunnlag for anmeldelse.
- Teksten bruker hele setninger og unngår skråstrek i den autogenererte oppsummeringen og i kort anmeldelsesutkast.
- Oppsummeringen bygger fortsatt bare på kontrollpunkter med status avvik.

## Forhåndsvisning og steg 7
- Feltet i steg 7 er omdøpt til **Anmeldelsestekst og oppsummering**.
- Informasjonsteksten ved autogenerering forklarer nå at utkastet blir satt opp punktvis per beslagnummer når dette finnes.
- Kort anmeldelsesutkast i forhåndsvisning følger samme nye struktur som oppsummeringen.

## Versjon
- Appnavn, versjonslabel og service worker-cache er løftet til **v38**.

## Verifisering
- Python-kompilering bestått.
- JavaScript-syntakssjekk bestått.
- Smoke test bestått på ren testdatabase med `KV_LIVE_SOURCES=0`, egen testdatabase og egne testmapper for opplastinger/genererte filer.
