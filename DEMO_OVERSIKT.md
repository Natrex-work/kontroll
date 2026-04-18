# KV Kontroll Demo v24 - oversikt

## Hovedendringer
- lagring holder bruker på samme steg og samme skjermbilde
- manuell kartposisjon overstyres ikke før brukeren eksplisitt velger automatisk posisjon igjen
- standardtekster i Roller / grunnlag gir tydeligere patruljeformål med dato, sted og kontrolltema
- søk i Person / fartøy er strammet inn for hummerdeltakernummer, mobilnummer, fiskerimerke og radiokallesignal
- ingen treff i søk vises nå kort som **Ikke søkbar / ingen direkte treff**
- kontrollpunkt kan ha flere teiner / redskap med avvik under samme lovbruddspunkt
- hoved-PDF eksporteres som samlet **Anmeldelse** eller **Kontrollrapport**

## Viktige funksjoner å teste
- manuell lagring skal ikke føre brukeren tilbake til steg 1
- autosave skal ikke få kartnålen til å hoppe tilbake til kontrollørens posisjon når manuell posisjon er satt
- deltakernummer som `RUN-AAR-850` skal gi treff i demo-fallback og fylle ut navn og 2026-sesongen
- standardtekst-knappen skal endre patruljeformål ut fra valgt preset
- flere avviksrader under ett kontrollpunkt skal kunne knyttes til samme eller ulike beslagnummer
- bildebevis skal kunne kobles til valgt avviksrad
- PDF med avvik skal bli **Anmeldelse**
- PDF uten avvik skal bli **Kontrollrapport**
- kun avhørsrapport skal eksporteres separat

## Eksempelfiler
- hoved-PDF med avvik
- kontrollrapport uten avvik
- kun avhørsrapport
- PDF + filer (ZIP)
