# Endringer 1.7.1

Denne versjonen viderefører 1.6.0 og tilpasser tekstmalene i webappen til føringene i opplastede dokumenter:

- Håndbok for Kystvaktens arbeid med straffesaker, revidert 2026
- Informasjon til mistenkte
- Vedlegg 15 Typiske IKV-anmeldelser
- Dreiebok for avhør av mistenkt/siktet
- Etterforskningsleders erfaringsnotat 002-2026
- KREATIV-faseillustrasjon for avhørsdisposisjon

## Tekstmaler

- Standardtekster bruker nærmeste sted som stedsgrunnlag og erstatter gamle formuleringer som `ved kontrollposisjonen` og `i aktuelt kontrollområde`.
- Patruljeformål er skrevet mer faktabasert: tid, sted, kontrolltema, faktisk gjennomføring, redskap/fangst/person/fartøy og notoritet.
- Lokalt hurtigutkast og servergenerert tekst bruker samme hovedstruktur.

## Anmeldelse og oppsummering

- Anmeldelsesutkast er gjort kortere og mer strukturert rundt hvem, hva, hvor, når, hvordan og bevissituasjon.
- Utkastet peker på aktuelt regelgrunnlag uten lange lov-/forskriftssitater.
- Oppsummering/anmeldelsesgrunnlag er delt i faste deler: tid/sted/tema, bakgrunn/gjennomføring, funn/avvik, beslag/bildebevis, avhør/forklaring og dokumentgrunnlag.
- Egenrapportmal er justert til å beskrive observasjoner og tiltak, ikke juridisk konklusjon.
- Internt Kystvaktpersonell omtales tydeligere som observatør der det passer, ikke automatisk som vitne.

## Avhør

- Avhørspunkter er lagt om til KREATIV-struktur: forberedelser, kontaktetablering, fri forklaring, sondering, avslutning og evaluering.
- Rettighetsinformasjon til mistenkt/siktet er tatt inn i avhørsmomentene: hva saken gjelder, frivillig forklaring, forsvarer, tolk, tilståelse og uriktig forklaring som kan ramme andre.
- Avvik vises som `Lenke 1`, `Lenke 2`, osv. i avhørsmomentene, slik at tema kan holdes adskilt.

## Dokumentpakke

- PDF-/preview-pakken bruker de nye tekstene for:
  - standardgrunnlag/patruljeformål
  - anmeldelse
  - oppsummering
  - egenrapport
  - avhørsrapport
  - avhørspunkter

## Teknisk

- Versjon og cache-bust oppdatert til `1.7.1`.
- Service worker og statiske JS/CSS-parametre er bumpet til `1.7.1`.
