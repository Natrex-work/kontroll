# Endringer 1.8.27 - rapporttekster, patruljeformål og IKV-stil

## Formål
Denne versjonen strammer inn autogenererte tekster slik at de ligger nærmere tidligere IKV-/Kystvakt-anmeldelser og føringene i straffesakshåndboken.

## Endret

### Patruljeformål / begrunnelse
- Skrevet om genererte standardtekster for patrulje og tips.
- Fjernet dårlige formuleringer som "kontrollere fiskerikontroll".
- Teksten bygger nå på faktisk kontrolltype, art/fiskeri, redskap, registrerte avvik og eventuell områdestatus.
- Tips-tekst skiller tydeligere mellom tipsopplysninger som bakgrunn og patruljens egne observasjoner/dokumentasjon.

### Anmeldt forhold
- Flere avvik vises som egne linjer.
- Kortere og mer presise titler for anmeldte forhold.
- Saksfeltene i PDF beholder dynamisk høyde for flere forhold.

### Beskrivelse av anmeldt forhold
- Omskrevet til mer formell, tettskrevet og IKV-nær tekst.
- Teksten fokuserer på hvem/hva/hvor/når/hvordan, kontrolltema og bevissituasjon.
- Dobbeltføring av samme faktum fjernes i kort faktumbeskrivelse.
- Lange generiske forklaringer og kunstig AI-språk er fjernet.

### Aktuelle lovhjemler
- Lovhjemler tas kun fra kontrollpunkter med status Avvik.
- Viser korte relevante utdrag knyttet til registrerte avvik.
- Lange områdekataloger, koordinatlister og store forskriftstekster fjernes fra hjemmelsteksten.

### Egenrapport
- Omskrevet til mer formell egenrapport med tydeligere patrulje-/oppsynsnarrativ.
- Fjerner dobbeltføring av posisjon, beslag og avvik.
- Skiller bedre mellom patruljeformål, gjennomføring, faktiske observasjoner, avvik og dokumentasjon.
- Posisjon skal primært fremgå av beslagsrapporten, ikke gjentas i løpende tekst.

### Frontend/API
- Oppdatert lokal tekstgenerering i Person-/saksflyt for patruljeformål.
- Oppdatert API-polering av patruljeformål slik at gamle dårlige standardtekster erstattes.

## Cache / deploy
- Appversjon: 1.8.27
- Service worker-cache: kv-kontroll-1-8-27-static / kv-kontroll-1-8-27-map-tiles
- JS/CSS lastes med ?v=1.8.27

## Testet
- Python compileall
- Node syntax checks for alle relevante JS-filer
- render_smoke_test.py
- Målrettet PDF-generering med flere avvik, korte lovhjemler og deduplisert faktum
- smoke_test.py forsøkt, men stoppet på timeout i miljøet
