# Endringer 1.8.21 - kontrollpunkter, kart og person/fartoy bildeanalyse

## Kontrollpunkter / redskap-beslag

- Fjernet den frittstaaende knappen "Bilde" under redskap/beslag. Kamera og "Legg til bilde" beholdes som faktiske bildehandlinger.
- Endret statusvisning slik at bildeantall vises som tekst, ikke som egen knapp.
- Lengdemaalingsbeslag isoleres fra ordinare avvik:
  - Ordinare avvik viser ikke lengdemaalingsbeslag i "Tidligere beslag".
  - Lengdemaalingskontrollpunkt viser bare lengdemaalingsbeslag.
  - Avvik under lengdemaalingskontrollpunkt merkes som measurement-related og deles ikke ut til andre avvikstyper.

## Posisjon / kart

- Rettet karttjenestevalg for rasterlag: Yggdrasil/Fiskerireguleringer-lag sendes ikke lenger til Fiskeridir_vern bare fordi de har gamle legacy-ID-er.
- Reduserte blinking ved zoom ved aa unngaa unodvendig redraw av ArcGIS export-raster nar lagutvalget ikke er endret.
- Beholder forrige detaljoverlay ved tomt eller feilet feature-svar, slik at kart ikke blir blankt ved tregt nett.
- Detalj-/vektorhenting brukes bare ved konkrete omradetreff eller eksplisitt detaljforesporsel; rasterlaget holder visuell omradevisning stabilt.
- Temalag-preferanser er bumpet til ny versjon slik at gamle skjulte lag fra 1.8.18 ikke skjuler nye lag i 1.8.21.

## Person / fartoy bildeanalyse

- Serveren leser naa API-nokkel fra OPENAI_API_KEY, KV_OPENAI_API_KEY eller filbaserte *_FILE-varianter.
- render.yaml inneholder baade OPENAI_API_KEY og KV_OPENAI_API_KEY som secret/sync:false.
- Feilmelding er gjort tydeligere: nokkelen maa legges inn i Render Environment og appen maa deployes paa nytt.

## Cache / versjon

- Appversjon bumpet til 1.8.21.
- Service worker-cache bumpet til kv-kontroll-1-8-21-static og kv-kontroll-1-8-21-map-tiles.
- JS/CSS lastes med ?v=1.8.21.
