# V33 endringer

## Kontrollpunkt 4 – redskap og lengdemåling

Det som er oppdatert i denne versjonen:

- **Legg til Redskap** er videreført som knappetekst i avviksdelen.
- **Samme redskap kan brukes på flere avvik i samme sak** ved å velge fra menyen **Tidligere redskap i saken**. Da beholdes samme **beslagsnr.** slik at flere lovbrudd kan knyttes til samme redskap.
- **Lengdemålinger får nå automatisk ref./beslagsnr.** i samme løpende serie som øvrige redskap og avvik i saken.
- **Lengdemålinger tas nå med i beslag-/bevisrapporten** på samme måte som registrerte redskap med avvik.
- Ved lengdemåling vises det nå automatisk:
  - hvor mange **cm og mm under minstemål** målingen ligger, eller
  - hvor mange **cm og mm over maksimalmål** målingen ligger.
- For hummer er **maksimalmål-kontrollpunktet gjort posisjonsstyrt**:
  - kontrollpunktet vises når kart-/områdegrunnlaget tilsier maksimalmålområde, eller
  - når kontrollposisjonen ligger innenfor demoens geografiske område for strekningen Sverige–Agder.
- Hummer minstemål og maksimalmål bruker nå tydeligere automatisk tekst i sammendrag og PDF.

## Teknisk

Berørte filer:

- `app/static/js/case-app.js`
- `app/static/styles.css`
- `app/rules.py`
- `app/pdf_export.py`
- `app/config.py`
- `app/static/sw.js`
- `smoke_test.py`

## Verifisering

Følgende er kjørt og bestått:

- `python -m compileall app`
- `node --check app/static/js/case-app.js`
- `KV_LIVE_SOURCES=0 python smoke_test.py`

## Versjon

- Appnavn: **Kontroll Og Oppsyn v33**
- Versjon: **33.0.0**
- Cache bumpet for å tvinge innlasting av ny frontendkode.
