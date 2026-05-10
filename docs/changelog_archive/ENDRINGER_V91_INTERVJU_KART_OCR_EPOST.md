# Endringer v91 - intervju, kart, OCR, dokumentpakke og e-post

## Avhør ikke gjennomført
- Lagt til avkryssing `Avhør ikke gjennomført` i avhørssteget.
- Standard årsak settes til `Ikke fått kontakt med vedkommende.`.
- Når dette er krysset av, tømmes/ignoreres avhørstekst i dokumentpakken.
- Avhørsrapport utelates fra dokumentlisten og PDF-pakken.
- Eksport av kun avhørsrapport blokkeres med forklarende melding når avhør ikke er gjennomført.

## Flere personer
- Lagt til seksjon for flere involverte personer.
- Man kan legge til flere mistenkte, vitner og andre roller.
- Personene kan brukes som utgangspunkt for avhørsoppføringer.

## Avhørsmomenter
- Lagt til autogenererte punkter for avhør basert på avvik/kontrollpunkter.
- Punktene inkluderer rettssikkerhetsmomenter, rolleavklaring, dokumentasjon og forslag til spørsmål.

## Kart og temalag
- Automatisk nedlasting/varming av kartpakker etter hver kartoppdatering er slått av for å redusere treghet.
- Kartet bruker færre aktive detaljlag og mindre rasterchunking for bedre mobilrespons.
- Kartlagpanelet har `Utvid alle` og `Legg sammen`.
- Kartlag prioriteres etter valgt kontrolltype, fiskeri/art og redskap.
- Lagkort viser utvalgs-/regelverkssammendrag der metadata finnes.

## OCR
- OCR-resultater caches midlertidig i minnet på både klient og server basert på bildefingeravtrykk.
- Samme bilde skal derfor ikke OCR-kjøres tungt flere ganger i samme økt/serverlevetid.
- Server-OCR har kortere timeout og mer deterministisk respons.

## Oppsummering og egenrapport
- Standardtekster er strammet inn til mer formell rapportstil.
- Egenrapport får en tydeligere innledning om kontroll, notoritet, observasjoner og regelverk.
- Avhør ikke gjennomført tas inn som egen merknad i egenrapport/oppsummering.

## Illustrasjonsmappe
- Dokumentpakken legger inn to automatiske kart først: oversiktskart og nærkart.
- OCR-kildebilder sorteres etter kartene.
- Øvrige bilder sorteres deretter etter beslag-/referansenummer og beskrivelse.

## E-post
- Lagt til skjema for å sende anmeldelsespakke med vedlegg direkte fra oppsummering/forhåndsvisning.
- Krever SMTP-konfigurasjon via `KV_SMTP_*` miljøvariabler.
- Hvis SMTP mangler, får bruker tydelig feilmelding i stedet for krasj.

## Verifisering
- Python-syntaks kontrollert med `py_compile`.
- JavaScript kontrollert med `node --check`.
- FastAPI smoke-test kjørt.
- Egen v91-flowtest kjørt med avhør ikke gjennomført, PDF-generering og e-postfeil ved manglende SMTP.
- PDF testgenerert og rendret visuelt til PNG.

## Ikke fullverifisert
- Faktisk iPhone/Safari etter deploy.
- Live Render SMTP-oppsett og faktisk e-postlevering.
- Live karttjenester over mobilnett.
