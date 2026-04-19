# Endringer i v49

- Fikset kartvisning slik at kun relevante lag for valgt kontrolltype/fiskeri/redskap hentes og vises.
- Lagt inn sterkere lokal fallback og sammenslåing av reserveflater slik at fredningsområder og stengte områder fortsatt tegnes i kartet når live-kilde er treg eller utilgjengelig.
- Fikset manuell posisjon: når manuell kontrollposisjon er valgt skjules blå GPS-markør og bare rød kontrollnål vises.
- Fikset OCR-flyten:
  - OCR-bilder komprimeres/konverteres ved behov før opplasting.
  - Server-OCR har timeout og faller automatisk tilbake til lokal OCR i nettleseren.
  - OCR-bildet lagres også som illustrasjon i saken.
- Fikset sertifikatkjede mot Fiskeridirektoratets karttjeneste i Docker-bildet ved å installere CA-sertifikater og bruke certifi.
- Oppdatert service worker til v49 med network-first for statiske filer, slik at nye JS/CSS-versjoner tas i bruk raskere etter deploy.
- Ryddet klar for full testing på Render.
