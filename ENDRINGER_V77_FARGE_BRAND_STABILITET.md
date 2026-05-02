# Endringer v77 – farge, branding og stabilitet

Denne pakken bygger videre paa v76 og retter tre konkrete forhold:

- samme fargeprofil paa alle skjermer via felles bla bakgrunnstema
- brand-organisasjon satt til `Minfiskerikontroll` i kode, manifest, `.env.example` og `render.yaml`
- stabil aapning av `Ny kontroll` uten a vente paa treg ekstern kartkatalog

## Gateway-crash ved Ny kontroll

`/cases/{id}/edit` og kartoversikten brukte tidligere live-katalog direkte under server-rendering. Hvis karttjenesten svarte tregt eller ikke svarte, ble sideaapningen forsinket og kunne gi gateway-feil i Render.

Dette er endret slik at server-renderte sider naa bruker:

- sist kjente cache hvis den finnes
- lokale fallback-lag hvis cache mangler

Live kartkatalog er fortsatt tilgjengelig via API ved behov, men blokkerer ikke lenger selve aapningen av `Ny kontroll`.

## Branding

Synlig organisasjonsnavn bruker naa `Minfiskerikontroll` som standard.

Viktig: Hvis Render-tjenesten din allerede har miljoevariabelen

`KV_BRAND_ORG_NAME=Fiskeridirektoratet`

maa den endres manuelt i Render til:

`KV_BRAND_ORG_NAME=Minfiskerikontroll`

Ellers vil Render fortsatt overstyre standardverdien i koden.

## Testet

Verifisert lokalt med:

- `python3 -m compileall app manage.py`
- `python3 smoke_test.py`
- `python3 render_smoke_test.py`
- `node --check app/static/js/case-app.js`
- `node --check app/static/js/map-overview.js`
- `node --check app/static/js/common.js`

I tillegg er aapning av `Ny kontroll` kontrollert med simulert treg karttjeneste. I denne testen gikk aapningstiden ned fra omtrent 4.6 sekunder til omtrent 0.12 sekunder.
