# Endringer 1.8.26 - rapporttekst, patruljeformål og bildeanalyse

## 1. Roller / grunnlag

- Standardtekst for `Patruljeformål / begrunnelse` er skrevet om.
- Generiske kombinasjoner som `kontrollere fiskerikontroll / aktuelt fiskeri / redskap` fjernes.
- Teksten bygges nå som naturlig sakstekst, for eksempel `fritidsfiske etter hummer med teine`.
- Tips skiller tydelig mellom tipsopplysninger som bakgrunn og patruljens egne observasjoner/dokumentasjon.

## 3. Person / fartøy

- OpenAI vision-standardmodell er endret fra `gpt-4.1-mini` til `gpt-4.1` for bedre lesing av håndskrift, slitte merker og buede overflater.
- Bildene beholdes større før analyse (`KV_OPENAI_VISION_MAX_SIDE=3400`, kvalitet 94).
- Prompten er skrevet om til en mer presis ChatGPT/vision-instruks for norske navn, adresser, postnummer, poststed, mobilnummer, deltakernummer og annen redskapsmerking.
- JSON-skjemaet er beholdt uendret, slik at frontend fortsatt får feltene `navn`, `adresse`, `postnummer`, `poststed`, `mobil`, `deltakernummer`, `annen_merking` og `usikkerhet`.

## Anmeldelse / rapport

- `Anmeldt forhold` viser nå alle registrerte avvik som egne linjer når det er flere forhold.
- PDF-feltene i sakshodet får dynamisk høyde, slik at lange/multiple anmeldte forhold ikke klippes etter f.eks. `Fiske i`.
- Anmeldelsesteksten er omskrevet til mer formell IKV-stil:
  - hvem som anmeldes
  - hvilke forhold som anmeldes
  - hvor/når forholdet ble avdekket
  - kort faktum
  - henvisning til egenrapport, beslagsrapport, fotomappe/illustrasjonsmappe og eventuell avhørsrapport
- `Aktuelle lovhjemler` er ytterligere strammet inn til korte utdrag fra hjemler knyttet til registrerte avvik.
- Egenrapporten er skrevet om med kortere og mer formelt patruljenarrativ, uten gjentakelse av tid/sted i patruljeformålet.
- Avhørsrapporten bruker mer formell oppbygning når avhør faktisk er merket gjennomført. Ellers forblir rapporten tom.

## Illustrasjonsrapport

- Bildetekster er strammet inn og posisjonstekst fjernes fra bildetekst dersom posisjon allerede fremgår av beslag/rapport.
- Bilde- og avvikstekst bevarer faglige skråstreker som `vak/blåse`.

## Versjon/cache

- Appversjon bumpet til 1.8.26.
- Service worker-cache bumpet til `kv-kontroll-1-8-26-static` og `kv-kontroll-1-8-26-map-tiles`.
- JS/CSS-versjonsparametre bumpet til `?v=1.8.26`.
