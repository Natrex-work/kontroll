# Endringer v81 – OCR, kart og oppsummering

## Rettet
- Mobil OCR sender nå original/høyoppløselig bildefil til server-OCR før lokal OCR overtar.
- Flere OCR-forsøk kjøres automatisk (original, forbedret original og dokumentmodus) for bedre treff på bøye-/skiltmerking.
- Treff i områdekontroll kobles nå riktig mot både gamle og nye lag-ID-er, slik at stengte/fredede områder vises visuelt i kartet.
- Kart-bundle og lagoppslag godtar nå både legacy-ID-er og gjeldende portal-ID-er.
- Autogenerert oppsummering har fått bedre formulering for område- og reguleringstekst.

## Verifisert
- Python-kode kompilerer.
- JavaScript-filer består syntakksjekk.
- Smoke-test verifiserer karttreff, bundle for legacy lag-ID og syntetisk OCR-uttrekk.
