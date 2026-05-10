# Endringer 1.8.0 - ytelse, OCR og beslag/avvik

## Kart og posisjon

- Raskere første posisjonsvisning med lagret siste enhetsposisjon på klient.
- Geolokasjon starter med rask lavpresisjon og oppdaterer med høyere presisjon i bakgrunnen.
- Verneområdesjekk viser mellomlagret resultat umiddelbart når samme posisjon/profil er sjekket nylig.
- Live punktsjekk mot kartlag kjøres med total tidsgrense slik at trege kartlag ikke låser appen.
- Standard cache for verneområdesjekk på server er økt til 300 sekunder.

## OCR

- Større bildegrunnlag før OCR og flere OCR-varianter.
- Flere utsnitt for topp/bunn/helbilde og flere etikettkandidater.
- Flere rotasjoner, inkludert 180 grader.
- Lengre OCR-forsøk per variant.

## Mobilnummeroppslag

- Eksisterende knapp `Søk mobilnummer` er beholdt og tydeliggjort i flyten.
- Oppslag skjer bare når bruker trykker knappen, og bruker mobilnummer som søkegrunnlag for navn, adresse og poststed.

## Kontrollpunkter, avvik og beslag

- `Legg til redskap/beslag` setter kontrollpunktet til avvik, oppretter rad, genererer beslagsnummer og markerer raden for bildebevis.
- Ny rad scroller/markeres visuelt slik at funksjonen blir synlig på mobil.
- Flere lenker per avvik er flyttet tydeligere øverst i avviksseksjonen.
- Brukeren kan bla mellom `Lenke 1`, `Lenke 2`, `Lenke 3` osv.
- Nye avvik kan legges direkte til valgt lenke.
- Mobilvisning av avviksrader er strammet inn til en kolonne på iPhone.

## Versjon

- Synlig versjon og cache-bust er oppdatert til `1.8.0`.
