# Endringer 1.8.29 - politifaglige autotekster

## Formål
Denne versjonen forbedrer autogenererte tekster for patruljeformål, anmeldt forhold/beskrivelse, egenrapport, avhørsrapport, lovhjemler og illustrasjonsrapport. Målet er mer objektiv, kort, etterprøvbar og politifaglig språkføring tilpasset IKV-/Kystvakt-saker.

## Endret
- Patruljeformål/begrunnelse genererer nå nøktern tekst med faktisk valgt kontrolltype, fiskeri/art, redskap, område og om saken bygger på patrulje eller tips.
- Kunstige formuleringer som "kontrollere fiskerikontroll", "kontrollere kontroll" og "gjennomføre kontroll av kontroll" renses bort.
- Tips-tekst skiller tydelig mellom tipsopplysninger som bakgrunn og patruljens egne observasjoner/dokumentasjon.
- Beskrivelse av anmeldt forhold er gjort kortere og mer formell:
  - hvem/hva/hvor/når
  - kort faktumbeskrivelse
  - mulig rettslig relevans uten skyldkonklusjon
  - henvisning til egenrapport, beslagsrapport og illustrasjonsmappe/fotomappe
- Egenrapport er skrevet mer som rapportskrivers observasjonsrapport:
  - tid/sted/patrulje
  - kontrolltema
  - formål
  - gjennomføring
  - registrerte avvik
  - dokumentasjon/beslag/bilder
  - avhør kun hvis gjennomført
- Avvikslinjer renses for dobbeltføring, posisjonsgjentakelser og lange beslagstekster.
- Aktuelle lovhjemler hentes fortsatt bare fra kontrollpunkter med status Avvik, og lovtekst kortes ned til relevant normtekst.
- Avhørsrapport er gjort mer formell og rettighetsorientert når avhør faktisk er merket gjennomført. Tom avhørsrapport forblir tom.
- Bildetekster i illustrasjonsrapport er kortet ned og renset for posisjonsgjentakelser.
- Lokal/offline tekstgenerering i frontend er oppdatert til samme stil.
- Summary API tar nå også imot fartøysnavn, etterforsker og tipskilde, slik at utkastene blir bedre tilpasset saken.

## Cache/versjon
- Appversjon: 1.8.29
- Service worker-cache: `kv-kontroll-1-8-29-static` og `kv-kontroll-1-8-29-map-tiles`
- JS/CSS og ikoner lastes med `?v=1.8.29`
