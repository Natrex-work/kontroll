# Endringer 1.8.17 - illustrasjonsrekkefolge, kartstabilitet, avhor og beslagsrapport

## Versjon/cache

- Appversjon bumpet til `1.8.17`.
- Service worker-cache bumpet til `kv-kontroll-1-8-17-static` og `kv-kontroll-1-8-17-map-tiles`.
- JS/CSS lastes med `?v=1.8.17`.

## 6. Illustrasjonsrapport / bilder

- Lagt til varig `display_order` pa vedlegg/bilder i databasen.
- Bilder i illustrasjonsrapporten kan flyttes opp/ned i appen.
- Rekkefolgen lagres via nytt API-endepunkt:
  - `POST /api/cases/{case_id}/evidence/order`
- Valgt rekkefolge brukes i preview/PDF/anmeldelse etter automatiske oversiktskart.
- Lokalt lagrede bilder beholder ogsa valgt rekkefolge fram til synk.

## Automatiske oversiktsbilder

- Automatiske oversiktskart i illustrasjonsrapporten bruker som standard fliskart med raster-export fra Fiskeridirektoratets Yggdrasil/Fiskerireguleringer MapServer.
- Lagene velges fra samme kontrollprofil som kartet i steg 4, basert pa kontrolltype, art/fiskeri og redskap.
- Hvis ekstern kart-export ikke svarer, faller rapporten tilbake til eksisterende vektor-/lokalkart.

## 4. Posisjon / Kart

- Rettet kritisk runtime-feil i rasterlaget: ArcGIS-export fikk tallbaserte lag-IDer, mens helperen bare leste `layer.id` fra objekter. Dette kunne gi tomt eller ustabilt `layers=show:` ved tegning/zoom.
- Omradelag vises na via riktige lag-IDer og blir liggende ved inn-/utzoom.
- Detalj-/feature-henting er begrenset til naermere zoom for a hindre at kartet venter pa tunge live-sporringer for alle lag pa lav zoom.
- `tapt redskap` holdes fortsatt utenfor kontrollkartprofilene.

## 7-9. Avhor, beslagsrapport og oppsummering

- Tidligere felles steg `Avhor / signatur / dokumentpakke` er splittet til:
  - `7. Avhor`
  - `8. Beslagsrapport`
  - `9. Oppsummering / signatur / dokumentpakke`
- `8. Beslagsrapport` viser alle beslagsrader og bilder knyttet til hvert beslagsnummer.
- Person/fartoy ligger fortsatt som steg 3 og er flyttet foran kartseksjonen i faktisk HTML-rekkefolge.

## Avhorspunkter/rettssikkerhetsmomenter

- Forslag til avhorspunkter og rettssikkerhetsmomenter beholdes som intern arbeidsstotte i steg 7.
- Forslagene eksporteres ikke i anmeldelse/dokumentpakke/preview/PDF.
- Knapp for a kopiere forslagene direkte inn i samlet avhorsutkast er fjernet for a hindre at interne forslag utilsiktet blir del av dokumentpakken.

## Tester kjort

- `python3 -m compileall -q app`
- `node --check` pa sentrale JS-filer
- `python3 render_smoke_test.py`
- Mal-/rekkefolgetest for steg 1-9
- Målrettet test av `display_order`, rekkefolge-API/datastruktur og at `interview_guidance` ikke kommer i case packet
- `unzip -t` pa ferdig ZIP

`python3 smoke_test.py` ble forsokt, men timet ut i dette miljoet etter innledende app-/kart-/regelverkskall.
