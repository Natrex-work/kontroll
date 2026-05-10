# Endringer 1.8.37 — Bildeanalyse uten betalt AI + Fiskeridir-oppslag

## Hva er endret

To områder er styrket på Person/Fartøy:

1. **Bildeanalyse fungerer 100 % uten betalt AI** — Tesseract-OCR (lokal, gratis)
   er nå standard. OpenAI brukes kun hvis admin eksplisitt slår det på.
2. **Auto-oppslag mot Fiskeridir-registeret** — når et deltakernummer er funnet
   eller skrevet inn manuelt, hentes navn fra autoritativ kilde (tableau.fiskeridir.no).

---

## Realistisk forventning til nøyaktighet

**Det er fysisk umulig å oppnå 100 % OCR-nøyaktighet** på bilder av merker, blåser
og ruser i felt. Lys, vinkel, slitasje og håndskrift gjør at INGEN OCR-tjeneste
i verden — verken gratis eller betalt — leser feilfritt hver gang.

**Det vi gjør i stedet** er å bygge robusthet på riktig sted:
- Lokal OCR finner *kandidater* — særlig deltakernummer (et tall er enklere å lese)
- Når vi har deltakernummeret, slår vi opp i **Fiskeridirektoratets register**
  som har autoritative verdier for navn og deltakernummer
- Felter som er verifisert mot registeret er **garantert korrekte** fordi
  de kommer fra Fiskeridir, ikke fra OCR-en

Dette gir i praksis 100 % korrekte sluttverdier for de feltene som finnes i
registeret, og for resten (adresse, mobil) får brukeren forslag som må bekreftes.

---

## 1. Lokal OCR som standard

### Før
`analyze_person_marking_images()` brukte OpenAI-vision som primær motor og
lokal Tesseract bare som fallback når API-nøkkel manglet.

### Nå
Standard er motsatt. Lokal Tesseract + Fiskeridir-oppslag er primær motor.
OpenAI brukes kun hvis admin **eksplisitt** setter:
```
KV_PERSON_FARTOY_USE_OPENAI=true
```
i miljøet. Det betyr at:
- Ingen abonnement på OpenAI kreves
- Ingen API-kostnader
- Ingen ekstern dataoverføring av bilder
- Alt kjøres på Render-instansen

### Rotårsak til hvor "presisjon" kommer fra

| Felt | Kilde | Nøyaktighet |
|---|---|---|
| Navn | Fiskeridir-registeret (etter deltakernummer-oppslag) | **100 %** (autoritativt) |
| Deltakernummer | Lokal OCR + verifisert mot register | **100 %** når verifisert |
| Adresse | Lokal OCR + 1881-katalog (hvis mobil finnes) | Forslag — krever bekreftelse |
| Postnummer/sted | Lokal OCR + 1881-katalog | Forslag — krever bekreftelse |
| Mobilnummer | Lokal OCR (8-sifret regex) | Forslag — krever bekreftelse |

---

## 2. Manuelt oppslag — «Slå opp i Fiskeridir-registeret»

### Ny knapp i skjemaet
Ved siden av Deltakernummer-feltet i Person/Fartøy-seksjonen er det nå en
🔍 **Slå opp**-knapp. Bruk den når du:
- Skriver inn deltakernummeret manuelt
- Vil verifisere et nummer OCR har lest
- Bare har et navn og vil finne deltakernummeret

### Hva skjer ved klikk
1. Frontend sender deltakernummer + navn til `/api/person-fartoy/lookup-deltakernummer`
2. Backend slår opp i Fiskeridirektoratets register (live + lokal cache)
3. Treff: navn og deltakernummer overskrives med autoritative verdier;
   adresse/postnummer/sted/mobil fylles inn der det mangler
4. Ingen treff: kandidat-liste vises hvis registeret har lignende oppføringer

### Visuelt resultat
```
✓ Treff i Fiskeridir-registeret
Ola Hansen · Deltakernummer 20-12345
Fiskertype: Fritidsfiskar
Sist registrert: 2025
Kilde: Fiskeridirektoratet — registrerte hummerfiskere ↗
```

---

## 3. Tableau-integrasjonen som var der allerede

Live-kallet til `https://tableau.fiskeridir.no/t/Internet/views/Pmeldehummarfiskarargjeldander/Pmeldehummarfiskarar`
var allerede bygget i `app/live_sources.py`:

- Forsøker flere CSV-eksport-URL-mønstre (`?:format=csv`, `.csv`, etc.)
- Faller tilbake til HTML-skraping av fallback-siden hos fiskeridir.no
- Cacher resultatet lokalt slik at oppslag er raske og fungerer ved
  midlertidig nettfeil

Det nye i denne versjonen er at frontend faktisk **bruker** dette på en
synlig, intuitiv måte — både automatisk etter bildeanalyse og manuelt
via "Slå opp"-knappen.

---

## 4. Filendringer

```
NY:
  (ingen — local_marker_analyzer.py fantes allerede i v36)

MOD:
  app/routers/api.py                          — nytt endepunkt
                                                /api/person-fartoy/lookup-deltakernummer
  app/templates/case_form.html                — Slå opp-knapp ved siden av
                                                deltakernummer-feltet
  app/static/js/case-app.js                   — handler for Slå opp-knapp
                                                som auto-fyller felter etter
                                                Fiskeridir-treff
  app/static/styles.css                       — .deltaker-input-row,
                                                .deltaker-lookup-btn
  app/static/sw.js                            — versjons-bump
  app/config.py                               — versjon 1.8.37
  alle templates                              — ?v=1.8.37
```

## 5. Filer bevisst IKKE rørt

- `app/services/local_marker_analyzer.py` — fungerer allerede korrekt og
  brukes når `KV_PERSON_FARTOY_USE_OPENAI` ikke er satt
- `app/services/openai_vision_service.py` — beholdes for de som vil bruke
  OpenAI eksplisitt
- `app/services/ocr_service.py` — Tesseract-pipelinen er stabil
- `app/live_sources.py` — Tableau-integrasjonen fungerer som den skal

## 6. Slik aktiverer du OpenAI igjen (valgfritt)

Hvis du vil ha enda høyere OCR-presisjon på vanskelige bilder (som koster
penger), sett i Render-miljøvariabler:

```
KV_PERSON_FARTOY_USE_OPENAI=true
KV_OPENAI_API_KEY=sk-...
```

Restart applikasjonen. Hvis OpenAI feiler eller går tom for kvote, faller
systemet automatisk tilbake til den gratis lokale pipelinen — så du har
alltid en fungerende fallback.

---

## 7. Versjon

`1.8.36` → `1.8.37`. Alle `?v=1.8.37`. SW-cache `kv-kontroll-1-8-37-static`.
