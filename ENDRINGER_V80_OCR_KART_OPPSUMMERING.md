# Endringer v80

Denne versjonen retter tre hovedområder:

1. **OCR/autofyll fra bilde og kamera**
   - OCR prøver nå alltid fullbildet først, ikke bare etikett-kutt.
   - Treffer fra flere OCR-forsøk slås sammen for å få bedre autofyll.
   - `LBHN 26 xxx` gjenkjennes nå som hummerdeltakernummer både i backend og frontend.
   - Bedre utfylling av navn, adresse, poststed, mobil og deltakernummer ved OCR.

2. **Visning av områder i kartet**
   - Kartlag som faktisk traff kontrollposisjonen blir nå tvunget inn i kartvisningen.
   - Trefflag markeres tydeligere visuelt i selve kartet.
   - Områdelag løftes foran øvrige kartlag slik at de er lettere å se.

3. **Bedre autogenerert oppsummering**
   - Områdeavvik får mer naturlig og tydelig språk.
   - Oppsummeringen beskriver nå redskap, posisjon, område og hvilke forbud/begrensninger som gjelder mer presist.

## Verifisert lokalt
- `python3 -m compileall app manage.py smoke_test.py`
- `python3 smoke_test.py`
- `python3 render_smoke_test.py`
- `node --check app/static/js/case-app.js`
- `node --check app/static/js/common.js`
- `node --check app/static/js/map-overview.js`

## Merknad
Live-oppslag mot eksterne kataloger som 1881/Gulesider bør fortsatt prøves i produksjon etter deploy, fordi eksterne sider kan endre struktur over tid.
