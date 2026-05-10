# Endringer v88 - kartzoom, kartlag og malbasert PDF

Denne versjonen er laget etter test av v87 der OCR og fysisk kartvisning fungerte, men kartet re-sentrerte/zoomet for ofte, kartlagpanelet var vanskelig på mobil, og forhåndsvisning/dokumentgenerering feilet.

## Kart og mobil

- GPS-oppdateringer oppdaterer fortsatt posisjon og markør, men tvinger ikke kartet tilbake til standardzoom ved hver posisjonsoppdatering.
- Kartet re-sentrerer nå bare ved første posisjonsfunn eller når brukeren aktivt trykker `Bruk min posisjon`.
- Manuell zoom/pan i kartet bevares bedre når ny GPS-posisjon kommer inn.
- Treffområde-bryteren har tydelig tekst: `Treffområder er synlige i kartet` / `Treffområder er skjult i kartet`.
- Kartlagpanelet er bygget om fra `<details>/<summary>` til knappebaserte grupper fordi dette er mer stabilt på iPhone/Safari.
- Laggrupper kan åpnes/lukkes med egne knapper, og `Vis alle i gruppen` / `Skjul alle i gruppen` skal ikke lenger oppleves som om logikken er snudd.
- Kartlagpanelet har ny lokal lagringsnøkkel (`v88`) slik at gamle v87-visningsvalg ikke forstyrrer testen.

## Forhåndsvisning og dokumentgenerering

- Forhåndsvisning bygges nå i threadpool slik at tung tekst-/dokumentbygging ikke blokkerer webrequesten like hardt.
- Forhåndsvisning har fallback-pakke dersom tekstbygging feiler, slik at siden ikke skal stoppe med 500/gateway uten forklaring.
- Manglende CSRF-felt i forhåndsvisnings-/eksportskjemaene er lagt inn eksplisitt.
- PDF-generering bruker igjen malbasert dokumentrekkefølge som hovedløp:
  1. Dokumentliste
  2. Anmeldelse
  3. Egenrapport
  4. Avhør / forklaring
  5. Rapport om ransaking / beslag
  6. Illustrasjonsmappe
- Den enklere tekst-PDF-en beholdes bare som sikker fallback dersom en malside mangler eller PDF-layout feiler.
- Originalmalene som ble lastet opp er lagt i `app/document_templates/` som kildegrunnlag. Runtime bruker stabile PNG-bakgrunner i `app/pdf_templates/` for å unngå at gamle `.dot`-maler må åpnes med LibreOffice ved hver eksport.
- Tjenestested/felttekst bruker nå `basis_source_name`/service-felt der det finnes, ellers `Minfiskerikontroll`, i stedet for hardkodet `KV NORNEN`.
- Dokumentlistetabellen er justert slik at teksten ikke ligger gjennom tabellinjene.

## Verifisering utført i container

- Python syntax: `py_compile` på sentrale backendfiler.
- JavaScript syntax: `node --check` på `common.js`, `case-app.js`, `local-cases.js`, `local-map.js`, `local-media.js`.
- Testgenerering av malbasert PDF: OK.
- Render av test-PDF til PNG: 7 sider, visuelt kontrollert for hovedsider.

## Må testes i faktisk miljø

- iPhone/Safari: zoom/pan mens GPS-posisjonen oppdateres.
- iPhone/Safari: åpne/lukke `Velg kartlag`, åpne/lukke laggrupper, vis/skjul lag.
- Render/produksjonsmiljø: forhåndsvisning og PDF/ZIP-eksport fra reell sak med bilder og kontrollpunkter.
- Live kartlag: fysisk polygonvisning ved kjente posisjoner i stengte/fredede områder.
