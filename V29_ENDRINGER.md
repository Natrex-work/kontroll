# V29 endringer

Denne oppdateringen gjelder **1. Roller / grunnlag** og sørger for at valgt standardtekst faktisk følger saken videre.

## Endret funksjon
- **Sett inn standardtekst** gir nå tydeligere og mer formelle tekster for hvert valg.
- Hver preset har egen tekst som er knyttet til valgt kontrollgrunnlag, for eksempel:
  - ordinær patrulje
  - faststående redskap
  - hummeroppsyn
  - samleteine / sanketeine
  - garnlenke / lenkekontroll
  - tips om redskap
  - tips om område
  - tips om minstemål
  - oppfølging etter anmeldelse
- Teksten som settes inn i **Patruljeformål / begrunnelse** blir nå **bevart** når bruker senere trykker **Autogenerer tekst**.
- Valgt patruljeformål / begrunnelse blir nå også videreført inn i:
  - **Oppsummering / anmeldelsestekst**
  - **kort anmeldelsesutkast**
  - **notatutkast**
- Oppsummering og anmeldelsesutkast viser nå tydelig:
  - `Patruljeformål / begrunnelse:`
  - `Bakgrunn for kontrollen:`

## Teknisk justert
- Autogenerering overskriver ikke lenger manuelt valgt standardtekst med en generisk bakgrunnstekst.
- Tekstforbedringsfunksjonen for grunnlag er justert slik at den ikke ødelegger ferdige setninger som allerede starter korrekt.
- Standard appversjon er oppdatert til **v29**.

## Verifisering
- Python-kompilering bestått
- JavaScript-syntakssjekk bestått
- Smoke test bestått med `KV_LIVE_SOURCES=0`
