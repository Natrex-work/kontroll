# Endringer 1.8.23 - standardtekster, patrulje/tips og rapportformuleringer

Denne versjonen strammer inn standardtekstene i skjema, tekstgenerering og rapport/PDF slik at de bedre følger vedlagte Kystvakt-føringer for IKV-/ressurskontrollsaker.

## Grunnlag for kontroll

- Synlige valg under `Grunnlag for kontroll` er nå bare:
  - `Patrulje`
  - `Tips`
- Valget `Anmeldelse` er fjernet fra brukergrensesnittet.
- Legacyverdier som `anmeldelse` og `annen_omstendighet` normaliseres til `patruljeobservasjon` / `Patrulje` ved lagring og rapportbygging.
- Eksisterende saker med gamle verdier migreres til `patruljeobservasjon` ved databaseinit.
- Kontrollhistorikken viser nå lesbar tekst `Patrulje` eller `Tips`, ikke rå internverdi.

## Standardtekster

- Standardtekstene for patruljeformål er formulert om:
  - Patrulje: vekt på patruljens egne observasjoner, gjennomførte tiltak og sikret dokumentasjon.
  - Tips: tips/opplysninger brukes som bakgrunn, men holdes tydelig adskilt fra patruljens egne observasjoner.
- Når bruker endrer grunnlag mellom `Patrulje` og `Tips`, oppdateres standardtekst automatisk dersom eksisterende tekst ser autogenerert ut.
- Backend sin `Formulering`-funksjon bruker samme normalisering og fjerner gamle formuleringer.

## Tekst som er fjernet/erstattet

- Uttrykket `involverte personer/fartøy` og varianter av dette fjernes fra genererte tekster.
- Det brukes i stedet mer presise formuleringer som:
  - `kontrollobjekt`
  - `relevante personer og kontrollobjekt`
  - `ansvarlig bruker/eier`
  - `personer i saken`
- `Hovedvitne` i skjema er endret til `Observatør / vitne`.
- `Flere involverte personer` er endret til `Flere personer i saken`.

## Anmeldelse / egenrapport / oppsummering

- Egenrapport og oppsummering er gjort mer nøkterne og politirapport-lignende:
  - kortere punkter
  - mindre intern forklaring
  - klarere skille mellom bakgrunn, faktiske observasjoner og dokumentasjon
- `Oppsummering / anmeldelsesgrunnlag` er endret til `Oppsummering / rapportgrunnlag`.
- Rapportutkast viser `Kontrollobjekt` i stedet for generiske person/fartøy-formuleringer.
- Dersom person/fartøy ikke er identifisert i feltene, står det kort at kontrollobjekt ikke er særskilt identifisert i person-/fartøyfeltene.

## Cache / versjon

- Appversjon er bumpet til `1.8.23`.
- Service worker-cache er bumpet til:
  - `kv-kontroll-1-8-23-static`
  - `kv-kontroll-1-8-23-map-tiles`
- JS/CSS lastes med `?v=1.8.23`.
