# Minfiskerikontroll V1.5

Denne pakken fortsetter utbedringene etter V1.4 med fokus på punkter som fortsatt kunne svikte i faktisk runtime.

## Hovedendringer

- Versjon/cache/service worker er bumpet til V1.5.
- Standardtekster bruker nå primært verdien fra Nærmeste sted. Gamle klienter som sender sted + område + koordinat til tekstpolering blir renset på server.
- Kart og Område har kollapsbart Temakart og kollapsbar liste for aktuelle temalag/områder.
- Rene kystnære fiskeridata, åpne områder og sjø-/dybdedata filtreres bort fra lov-/forskriftskart.
- Punktkontroll mot live kart tar nå med alle treffende objekter fra hvert kartlag, ikke bare første feature.
- Alle relevante områdetreff får anbefalt avvik per treff når regelmotoren kan gi dette.
- OCR-klient filtrerer 1881/Gulesider/Vis nummer/personer/kart/resultat før adresse og poststed fylles.
- OCR-server bruker litt større bildegrunnlag, flere varianter og lengre timeout.
- Mobil CSS for temalag er strammet inn for å unngå horisontal zoom.

## Må fortsatt testes live

- Faktisk Fiskeridirektoratet-kart i Render/iPhone Safari.
- GPS-posisjon i overlappende verneområder.
- OCR på dårlige reelle bilder med Tesseract/Pillow/OpenCV tilgjengelig.
- PDF/illustrasjonsrapport med bilder fra avvik/beslag.
