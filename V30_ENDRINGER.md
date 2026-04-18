# V30 endringer

## Kontroll – Roller / grunnlag
- `Sett inn standardtekst` er skjerpet slik at teksten i **Patruljeformål / begrunnelse** alltid byttes etter valgt standardtekst.
- Automatisk forslag tar nå også hensyn til **grunnlag for kontroll** (`tips`, `anmeldelse`, `annen omstendighet`, `patruljeobservasjon`).
- Tekstene er gjort mer forklarende og mer egnet for videre bruk i oppsummering og anmeldelsesutkast.

## Kontroll – Person / fartøy
- Hummeroppslag er utvidet fra lokal demofil til søk i lokal liste **og** hurtigbufret/offentlig hummerregister når live-kilder er tilgjengelige.
- Navn med format `Etternavn, Fornavn` og vanlige deltakernummer søkes bredere.
- Valg av kandidat fra hummerlisten kjører nå et nytt oppslag automatisk for å hente inn mer kontaktinformasjon.
- Treff i hummerregisteret viser nå også adresse og mobil når slike opplysninger blir funnet via videre katalogoppslag.
- Backend er oppdatert slik at hummerregistertreff kan berikes med adresse og mobilnummer uten å miste deltakernummer og registreringsstatus.

## Kontroll – Kontrollpunkter / teine-redskap
- Når et kontrollpunkt settes til **avvik**, opprettes det automatisk en første rad under **Teiner / redskap med avvik**.
- Knappen **Legg til teine / redskap** fungerer nå med ferdig standardrad.
- **Beslagsnr.** settes automatisk til saks-/anmeldelsesnummer med løpende tresifret nummer.
- Samme beslag-/referansenummer gjenbrukes når samme teine/redskap registreres på flere lovbrudd.
- **Hva er avviket** forhåndsfylles fra aktuelt lovbrudd/kontrollpunkt.
- **Teine/redskap-ID** er beholdt som manuelt felt, mens type redskap velges fra rullegardin.
- Felt for bildereferanse er fortsatt fjernet i denne delen.

## Teknisk
- `registry.py` støtter nå søk i lokal og hurtigbufret hummerliste.
- `live_sources.py` støtter oppfrisking av hurtigbuffer for hummerregister.
- `registry_service.py` er utvidet med sammenslåing av hummerdata og kontaktdata.
- `case-app.js` er oppdatert for bedre kandidatvalg, standardtekstflyt og avviksrader.
- Appversjon er løftet til **v30**.
- Service worker-cache er oppdatert for å tvinge ny frontend lastet inn.

## Verifisering
- Python-kompilering bestått
- JavaScript-syntakssjekk bestått
- Smoke test bestått med `KV_LIVE_SOURCES=0`
- Ekstra registertest kjørt for hummercache + automatisk kontaktberiking
