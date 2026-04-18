# Refaktorering v25

## Gjennomført
- `app/main.py` redusert til app-fabrikk, middleware og router-registrering.
- Route-logikk flyttet til `app/routers/`.
- Domene-/arbeidsflytlogikk flyttet til `app/services/`.
- Session, katalogvalg og mal-kontekst samlet i egne moduler.
- `.env.example` lagt til for konfigurasjon av session secret, database, opplastingsstørrelse og kataloger.
- `db.py` og `pdf_export.py` koblet til sentral `settings`-konfigurasjon.
- Base-template endret til page-specific script loading.

## Delvis ryddet, men fortsatt stor
- `app/static/js/case-app.js` er fortsatt største enkeltfil og er neste naturlige kandidat for videre deling per steg.
- `app/live_sources.py` er fortsatt stor og bør ved behov deles i kart-/register-/katalogkilder.
- `app/pdf_export.py` er beholdt, men er nå kapslet bak `pdf_service.py` fra rutene.

## Verifisert
- `python -m py_compile ...`
- `python smoke_test.py`
