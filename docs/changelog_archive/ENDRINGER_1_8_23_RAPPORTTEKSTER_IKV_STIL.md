# Endringer 1.8.23 - rapporttekster etter IKV-/Kystvaktstil

Denne versjonen strammer inn autogenererte tekster i anmeldelse, egenrapport og illustrasjonsmappe.

## Anmeldelse / rapport

- `Anmeldt forhold` er gjort kortere og mer sakstilpasset.
- `Beskrivelse av det anmeldte forhold` starter nå direkte med hvem/hva/hvor/når og kort faktisk grunnlag.
- Standardoverskriften `Anmeldelse` fjernes fra selve friteksten, fordi dokumentmalen allerede har dokumenttittel.
- Teksten viser til egenrapport, beslagsrapport og illustrasjonsmappe/fotomappe for detaljer, tilsvarende typiske IKV-anmeldelser.
- Ved tips beskrives tipsopplysningene som bakgrunn for kontrollen, mens patruljens egne observasjoner holdes adskilt.
- `Aktuelle lovhjemler` begrenses til hjemler som faktisk kommer fra kontrollpunkter med status `Avvik`.
- Lange lov-/forskriftstekster avkortes til korte utdrag som forklarer aktuell regel. Fullstendige områdebeskrivelser og lange tabeller tas ikke inn i anmeldelsesteksten.
- Preview viser lovhjemmel som strukturert `forskrift/lov - paragraf` med kort `Utdrag`, ikke rå Python-/JSON-dict.

## Egenrapport

- Egenrapporten er omskrevet fra skjematisk punktliste til kortere, mer formell førstperson-/patruljenarrativ.
- Starten kobles til `Patruljeformål / begrunnelse`.
- Formuleringene er mer i retning av tidligere IKV-rapporter: patrulje/oppsyn, inspektørlag, kontrolltema, observasjoner, avvik og dokumentasjon.
- Overflødige standardforklaringer og dobbeltføring av beslag fjernes fortsatt.

## Illustrasjonsmappe

- Bildetekster starter nå normalt med `Bilde viser ...`.
- Teksten holdes kort og bevisrettet.
- Beslagsnummer og kort avvik legges til når bildet er knyttet til beslag/avvik.
- Kartbilder får enkle tekster om oversiktskart/detaljert kartutsnitt.

## Frontend

- Feltet heter nå `Patruljeformål / begrunnelse`.
- Standardtekst-knappen genererer mer IKV-tilpasset patrulje-/tipsformulering.
- Lokal fallback for tekstutkast er justert bort fra eldre generiske rapporttekst.

## Cache

- Versjon bumpet til 1.8.23.
- Service worker-cache og JS/CSS-versjon er bumpet.
