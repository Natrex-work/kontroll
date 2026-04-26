# Endringer v93 - formelle tekster, beslag, signatur og OCR-fiks

## Standardtekst og rapporttekst

- Patruljeformål/standardtekst er skrevet om for å beskrive tid, sted, kontrolltype, valgt fiskeri/redskap og kontrollformål mer nøytralt.
- Tekstgeneratoren skal ikke lenger bruke formuleringer om at forhold dokumenteres i anmeldelsesegnet form eller at kontrollen ses i sammenheng med tidligere registrerte opplysninger.
- Egenrapport og oppsummering er strammet inn mot objektiv, kronologisk og etterprøvbar rapportstil.
- Gamle referanser til Kystvakten, KV NORNEN og hardkodet tjenestested er fjernet fra aktuelle standardfelt/generering.

## Roller og grunnlag

- Synlig statusfelt er fjernet fra registreringssiden. Status håndteres automatisk av saken.
- Feltet Kilde / tips / patruljenavn er fjernet fra synlig registrering.
- Grunnlagstekst er fortsatt lagret som standardtekst/patruljeformål.

## Områder og avvik

- Under posisjon/kontrolltype er det lagt inn et områdevalg som fylles fra treff/områdekontroll og avvikskontrollpunkter.
- Valgt område kan brukes som saksområde når posisjonen/fiskeriet tilsier forbud eller regulering.

## OCR

- Feilen `Can't find variable: ocrAutofillPreview` er rettet ved å flytte OCR-autofyllreferanser til felles scope.

## Beslagsrapport

- Ny side `Beslagsrapport` er lagt inn før oppsummering.
- Appen genererer beslagsposter automatisk fra relevante avvik på redskap, fangst, minstemål/maksimalmål, beslag og lignende.
- Bruker kan oppdatere, slette og legge til manuelle beslagsposter.
- Beslag lagres i `seizure_reports_json` og brukes i PDF/forhåndsvisning.

## Signatur

- Signaturfelter er gjort om til låste navn med `Signer`-knapp.
- Signering kan gjøres med finger/penn på mobil/iPad i eget lerret.
- Signaturdata lagres som JSON med navn, tidspunkt og touch-signaturbilde.
- PDF viser elektronisk signaturtekst. Selve signaturbildet er lagret i saken og kan senere plasseres visuelt i PDF-malene.

## Person/fartøy

- Personseksjonen støtter flere involverte personer.
- Roller inkluderer mistenkt, siktet, vitne, fornærmet, eier, fører/skipper og annen person.
- Involverte personer tas med i oppsummering når de er registrert.

## Mobil header

- Mobilvisning beholder MK/header og sidenavigasjon synlig.
- Hjem, ny kontroll og øvrig hovednavigasjon holdes skjult til MK-menyen åpnes.

## Teknisk

- App-versjon/cache er oppdatert til v93.
- Database har ny kolonne `seizure_reports_json`.
- Forhåndsvisning lagrer ikke lenger over signaturer/beslagsrader hvis feltene ikke finnes i skjemaet.
