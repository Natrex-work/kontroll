# V37 endringer

## Kontrollpunkter – lengdekrav for hummer

Det som er endret i denne versjonen:

- Når kontrollposisjonen ligger i område der hummer har både minstemål og maksimalmål, vises dette nå som **ett samlet kontrollpunkt**:
  - **Lengdekrav hummer (min. 25 cm / maks. 32 cm i sør)**
- Dette gjelder typisk på strekningen fra svenskegrensen til og med Agder.
- Kontrollpunktet vurderer nå automatisk målingen mot **begge grensene** i samme punkt.
- Målingen viser tydelig om hummeren er:
  - **under minstemål**, eller
  - **på/over maksimalmål**
- Avvik vises med differanse i både:
  - **cm**
  - **mm**
- Lengdefeltet er tydeliggjort med støtte for én desimal:
  - `0,1 cm = 1 mm`
- Tidligere saker med separate punkter for `hummer_minstemal` og `hummer_maksimalmal` blir forsøkt **slått sammen** i frontend når kontrollpunktene lastes inn på nytt, slik at eksisterende målinger og notater ikke forsvinner.
- Autogenerert oppsummering/anmeldelsesutkast kjenner nå igjen det nye samlede kontrollpunktet og skriver mer presist om forholdet som:
  - under minstemål,
  - på/over maksimalmål, eller
  - generelt utenfor tillatt lengdekrav.

## Teknisk

Oppdatert:

- `app/rules.py`
- `app/static/js/case-app.js`
- `app/pdf_export.py`
- `smoke_test.py`
- `app/config.py`
- `app/static/sw.js`
- `.env.example`

## Verifisering

Kjørt og bestått:

- Python-kompilering
- JavaScript-syntakssjekk
- smoke test i ren testdatabase
