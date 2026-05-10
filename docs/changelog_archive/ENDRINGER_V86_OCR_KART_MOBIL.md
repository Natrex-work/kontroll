# Endringer v86

## OCR / bildeavlesing
- Safari/iPhone bruker nå XHR-basert opplasting til server-OCR for å unngå heng i `fetch`-flyten ved bildeopplasting.
- Mobil forsøker nå først et optimalisert mobilbilde, deretter forbedret original, og til slutt originalfilen som reserve.
- Opplastingsprosent vises under server-OCR slik at brukeren ser fremdrift i stedet for at skjermen bare står og jobber.
- Server-OCR-flyten er beholdt som hovedløp, og automatisk lokal OCR i mobilnettleseren brukes fortsatt ikke som standard på iPhone/iPad.

## Kart / temalag
- Temalagvelgeren på kontrollkartet ligger ikke lenger oppå selve kartflaten.
- Lagvelgeren er flyttet til et eget panel under kartet som kan åpnes/lukkes og rulles uten å blokkere kartet.
- Treffområder / stengte felt kan slås av og på med egen bryter over kartet.
- Treffsoner tegnes med tydeligere kantlinje i kartet.
- Temalagpanel-preferanser er versjonert på nytt (`v86`) slik at gamle åpne paneler ikke henger igjen fra tidligere deploy.

## Cache / mobil
- CSS, JavaScript og service worker er versjonert til `v86` for å tvinge mobilklienter til å hente ny kode.

## Kontrollert lokalt
- `python3 -m compileall app manage.py smoke_test.py render_smoke_test.py`
- `node --check app/static/js/common.js`
- `node --check app/static/js/case-app.js`
- `python3 smoke_test.py`
- `python3 render_smoke_test.py`
- OCR-endepunkt testet mot faktisk opplastet merkebilde (`LOB-HUM-1323`).
