# Endringer v85

- Fikset JavaScript-feilen `secureFetchOptions` som stoppet OCR på mobil.
- Server-OCR blir nå faktisk startet fra steg 3 uten at Safari stopper før opplasting.
- Eksponerte `secureFetchOptions` globalt som bakoverkompatibel fallback.
- Lagt inn cache-busting (`?v=v85`) på CSS/JS for å tvinge iPhone/Safari til å laste ny klientkode.
- Oppdatert service worker-cache-navn til v85.
- Nullstilt temalagpanel-preferanser til v85 slik at gammelt åpent panel ikke dekker kartet videre.
- Kontrollkartet tegner nå opp tydelig overlay for område-/sone-treff direkte fra `/api/zones/check`.
- Gjort temalagpanelet mindre og mer mobilvennlig med lukket standard og begrenset høyde.
