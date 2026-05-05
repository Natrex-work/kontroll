# Endringer 1.8.24 - tekstrydding, rapportstil og bildestabilitet

## Kontrollpunkter / redskap-beslag

- Fjernet den lange hjelpetekst-/statusboksen som lå under avviksrader og gjentok tidligere/valgt beslag, posisjon, avvik og bildeinfo.
- Fjernet fritekstfeltet `Beslagsrapporttekst` fra avviksraden i kontrollpunktet. Beslagsrapport bygges nå fra strukturerte felter.
- Fjernet lang strukturert forhåndsvisning av avviksrad under kontrollpunktet.
- Kortet ned avvikssammendraget slik at posisjon ikke gjentas i kontrollpunktvisningen.
- Knappene `Kamera`, `Legg til bilde` og `Fjern` beholdes i raden.
- Bildeantall beholdes bare som kort statuslinje.

## Stabilitet ved bilde/redskap på mobil

- Fjernet automatisk `scrollIntoView` ved valg/legging til avviksrad. Dette reduserer hopping i skjermbildet når nytt beslag/redskap eller bilde legges til.
- Fjernet dobbel render etter `Legg til redskap/beslag`.
- Lagt til CSS for å hindre scroll anchoring på avviksrader og bilde-/opplastingsstatus.

## Anmeldelse / rapport / egenrapport

- Ny 1.8.24-tekstmal for anmeldelse, egenrapport, avhørsrapport, beslagsrapport og bildetekster.
- Anmeldelsen er gjort kortere og mer direkte, med hvem/hva/hvor/når/hvordan først.
- `Aktuelle lovhjemler` tar fortsatt kun med hjemler fra registrerte avvik og viser korte utdrag.
- Lange inline-beslagsoppsummeringer fjernes fra anmeldelse og egenrapport.
- Posisjon fjernes fra fritekst og gjentas bare som egen strukturert linje i beslagsrapporten.
- Egenrapporten er skrevet om til kort patruljenarrativ etter IKV-stil, uten gjentakelse av tid/sted og uten beslagsliste i brødteksten.
- Avhørsrapporten er kortet ned og viser bare gjennomførte avhør.

## Illustrasjonsrapport / fotomappe

- Bildetekster er kortet ned til `Bilde viser ...`, med kort beslag/avvik der dette finnes.
- Posisjonsfraser, lenkestart/slutt og hjemmelstekst fjernes fra bildetekster.
- Karttekstene beholdes korte:
  - `Bilde viser oversiktskart av kontrollposisjon.`
  - `Bilde viser detaljert kartutsnitt med kontrollposisjon og registrerte avviks-/beslagsposisjoner.`

## Versjon / cache

- Appversjon bumpet til 1.8.24.
- Service worker-cache bumpet til `kv-kontroll-1-8-24-static` og `kv-kontroll-1-8-24-map-tiles`.
- JS/CSS-versjonsparametre bumpet til `?v=1.8.24`.
