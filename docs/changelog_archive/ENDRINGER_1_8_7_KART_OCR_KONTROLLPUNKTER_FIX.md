# Endringer 1.8.7 - kartplassering, verneområder, OCR og kontrollpunkter

## Kart og visning
- Kartet i Posisjon/kontrolltype ligger nå direkte etter Nærmeste sted og før Teknisk posisjon.
- Offline-reguleringer er kollapsbar seksjon under kartet.
- Aktuelle verneområder/reguleringer fra posisjonssjekk tegnes alltid i kartet når treff inneholder geometri.
- Gammelt lokalt valg som skjulte treffområder ignoreres fra 1.8.7.

## OCR
- OCR prioriterer nå merkeskilt-/etikettutsnitt før helbilde for raskere og mer presis avlesing.
- Store utsnitt begrenses i størrelse før OpenCV/Tesseract-behandling for å unngå at OCR låser seg på iPhone-bilder.
- Lagt inn ekstra normalisering for typiske OCR-feil i merke-ID, f.eks. L0B/HUM/I323 -> LOB-HUM-1323.
- Merkeskilt-varianter med tegnliste/whitelist er lagt til som fallback.
- OCR kan fortsatt ikke garanteres 100 %, men usikre felt markeres for manuell kontroll.

## Kontrollpunkter
- Kontrollpunkter vises nå også når API-kall feiler eller returnerer tom liste.
- Lagt inn lokal fallback-liste basert på kontrolltype, art/fiskeri og redskap.
- Listen lastes automatisk når steg 4 åpnes og ved endring av kontrolltype/art/redskap.

## Versjon/cache
- Oppdatert til 1.8.7.
- Service worker, JS/CSS og kartcache er bumpet til 1.8.7.
