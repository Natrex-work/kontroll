# KV Kontroll Demo v26 – endringer gjennomført

## Hjemside / første side
- Fjernet øverste intro-/hero-rute.
- Endret navn fra **Kart og områdestatus** til **Kart og Område**.
- Endret navn fra **Regelverk per fiskeri** til **Regelverk Fiskeri**.
- Oppdatert ikonene på:
  - Kontroller og historikk
  - Ny kontroll
  - Regelverk Fiskeri
  - Kart og Område

## Kontroll – 1. Roller / grunnlag
- Standardtekst-funksjonen er strammet opp.
- Alle preset-valg gir nå tydelig forskjellige og mer forklarende standardtekster i en mer formell anmeldelsesstil.
- `Sett inn standardtekst` overskriver patruljeformål / begrunnelse med teksten for valgt preset.

## Kontroll – 2. Posisjon / kontrolltype
- Manuell kartplassering blir stående til bruker aktivt trykker **Oppdater automatisk posisjon**.
- Lagt inn egen infoboks som viser at **manuell posisjon er valgt**.
- Fjernet feltet **Treff / område** fra skjemaet.
- Lagt inn eget statusfelt under områdestatus som viser hvilket område kontrollen står i, inkludert stengt/fredet/regulert område.
- Endret label fra **Nærmeste stednavn** til **Nærmeste sted**.

## Kontroll – 3. Person / fartøy
- Hummerregister-status er gjort tydeligere i UI.
- Treffer viser nå navn, deltakernummer og sesongformulering som **Påmeldt hummerfisket i 2026** når det finnes.
- Kandidatvalg fra trefflisten oppdaterer skjemaet og registerstatus mer robust.
- Demo-/fallback-oppslag for hummerdeltakere fungerer fortsatt, inkludert eksempel som `RUN-AAR-850`.

## Kontroll – 4. Kontrollpunkter
- Ved **Legg til teine / redskap**:
  - Beslags-/saksnummer genereres automatisk med løpende suffiks.
  - Samme beslagreferanse gjenbrukes bare når samme redskap-ID faktisk er brukt.
  - Lovbrudd / avvik fylles automatisk med tydeligere standardtekst basert på kontrollpunktet.
  - Dropdown for redskapstype beholdes og feltet for manuell ID er tydeliggjort.
- Fjernet bildefeltet fra lengdemålinger i kontrollpunktene, siden bildebevis håndteres i steg 5.

## Kontroll – 7. Oppsummering
- Autogenerering oppdaterer nå grunnlag, notater og sammendrag hver gang knappen trykkes.
- Sammendrags-/anmeldelsesteksten er omskrevet til en mer formell struktur:
  - kontrolltidspunkt
  - kontrollsted
  - grunnlag for kontrollen
  - registrerte forhold
  - hjemler per forhold
- Utkastet bygger kun på registrerte avvik/lovbrudd fra kontrollpunktene.

## Tekniske filer endret
- `app/templates/dashboard.html`
- `app/templates/map_overview.html`
- `app/templates/rules_overview.html`
- `app/templates/case_form.html`
- `app/static/js/case-app.js`
- `app/pdf_export.py`

## Verifisering
- Python-kompilering kjørt uten feil.
- JavaScript-syntakssjekk kjørt uten feil.
- Smoke test kjørt og bestått før opprydding av testartefakter.
