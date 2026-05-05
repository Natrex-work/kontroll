# Endringer 1.8.21 - avhør, rapport, illustrasjon og personbilde

## Person / fartøy

- Bildeanalyse feiler ikke lenger hardt dersom OpenAI API-nøkkel mangler på serveren.
- Ved manglende `OPENAI_API_KEY`/`KV_OPENAI_API_KEY` brukes lokal OCR som reserve, og resultatet markeres tydelig som usikkert.
- Feltene fylles fortsatt i samme JSON-struktur: navn, adresse, postnummer, poststed, mobil, deltakernummer, annen_merking og usikkerhet.

## Anmeldelse / rapport

- Avhørsrapport genereres ikke med standardtekst dersom avhør ikke er gjennomført eller avhørsfelt står tomt.
- Egenrapport er gjort kortere, mer formell og mindre repetitiv.
- Dobbeltføring av beslagslister i egenrapport/anmeldelse er fjernet.
- Standardforklaringer om hva egenrapporten er, fjernes fra generert rapporttekst.
- Aktuelle lovhjemler i anmeldelsen hentes nå fra registrerte avvik, ikke fra alle mulige kilder/regelverk i saken.

## Illustrasjonsrapport

- Oversiktskarttekster er kortet ned.
- Karttekst er endret til `Oversiktskart av kontrollposisjon` og `Detaljert oversiktskart av kontrollposisjon`.
- Hjemmeltekst under kartbildene fjernes.
- Bildetekster er kortere og mer beskrivende.
- Detaljkartet genereres med mer zoomet utsnitt.
- Avviksposisjoner/beslagsposisjoner markeres i detaljkartet når posisjon er registrert på avviket/beslaget.
- Bilder tatt fra avvik synkes automatisk, slik at de ikke bare blir liggende lokalt på iPhone/iPad, men kommer med i illustrasjonsrapport etter synk.

## Cache

- Appversjon og cache er bumpet til 1.8.21.
- JS/CSS lastes med `?v=1.8.21`.
