# Endringer v95 - OCR, beslag, lenke, posisjon og avhør

## Person/fartøy og OCR-feltplassering

- Skilt/vak/blåse/merke-ID lagres nå i eget felt `gear_marker_id`.
- OCR skal ikke lenger tolke merke-ID som `LOB-HUM-1323` som hummerdeltakernummer.
- Hummerdeltakernummer normaliseres kun når OCR faktisk finner H-/årsformat, for eksempel `H-2026-123`.
- Fartøysnavn, fiskerimerke, radiokallesignal, navn, adresse, telefon og merke-ID skilles tydeligere i både frontend og backend.
- Server-side OCR-hints og frontend-autofyll er oppdatert slik at linjer som `Merke-ID`, `Fartøysnavn`, `Fiskerimerke` og `Radiokallesignal` ikke feilplasseres som navn/adresse.

## Standardtekst og sted

- Autogenerert standardtekst/patruljeformål bruker nå nærmeste sted fra posisjon/områderesultat når det finnes.
- Teksten tar med posisjon og område på en mer konkret måte.
- Koordinater vises som `breddegrad ... , lengdegrad ...`.

## Posisjon/kontrolltype

- Under feltet `Nærmeste sted` vises nå breddegrad og lengdegrad når posisjon er satt.
- Områdestatus kan fortsatt bruke registrert område/treff fra kart- og sonesjekk.

## Kontrollpunkter, lenke og beslag

- Under merking av vak/blåse er det lagt inn avhuking for om redskapet er lenke.
- Start- og sluttposisjon er skjult frem til `Redskapet er lenke` krysses av.
- Kontrollørposisjon kan settes uavhengig av lenke.
- Avviksrader har nå posisjon bundet til beslagnummer.
- Lengdemålinger har nå posisjon og kan få målingsreferanse.
- Alle avviksrader kan kobles til tidligere beslag/redskap i saken.
- Flere avvik kan knyttes til samme beslagnummer.
- Bildebevis kan velges fra avviksrad og følger samme beslagnummer til illustrasjonsrapporten.
- Beslagsrapport/PDF tar med posisjon per beslag der denne finnes.

## Beslagsnummer

- Automatisk beslagnummer bruker sakens nummer som base, for eksempel `LBHN 26 003-001`.
- Målinger bruker eget format, for eksempel `LBHN 26 003 - Måling -001`.
- Løpenummer sorteres etter beslagets sluttløpenummer i illustrasjons-/beslagsrekkefølge.

## Avhør

- Forslag til avhørspunkter er skrevet om i mer punktvis struktur.
- Rettssikkerhetsmomenter vises tydeligere i egne punkter.
- Avvik og beslag listes med beslagnummer og posisjon der dette finnes.
- Det er lagt inn knapp for å åpne avhørsmomenter som hel side med utskriftsmulighet.

## PDF/illustrasjon

- Dokumentpakken tar med nye beslag-/måleposisjoner i beslagstekst og rapport.
- Illustrasjonsrekkefølge sorterer bedre etter kart, OCR-bilder og beslagnummer.
- PDF er testgenerert og rendret til PNG i testmiljø.

## Tester kjørt

- `python -m compileall` på app og testskript.
- `node --check` på sentrale JS-filer.
- `smoke_test.py` kjørt OK.
- `render_smoke_test.py` kjørt OK.
- Test av OCR-hints for `LOB-HUM-1323`, `H-2026-123`, fartøysnavn og fiskerimerke.
- Testgenerert PDF rendret til 7 sider.

## Ikke fullverifisert

- Faktisk iPhone/Safari.
- Faktisk kamera/OCR i felt.
- Live GPS og live karttjenester.
- Render-deploy med persistent disk.
- SMTP/e-postutsending.
