# Endringer 1.8.7 - Bugfix kart, OCR og kontrollpunkter

## Feil rettet

### Kart
- **Feil område-notater sendt til kontrollpunkt-API**: `loadRules()` brukte feil variabel (`zoneResult` som er et DOM-element) for å hente tekstnotater om verneområder. Disse ble nå hentet direkte fra `latestZoneResult`-datastrukturen (navn, notater og treff fra posisjonssjekken), slik at riktig kontekst faktisk når regelverkslogikken.
- **Lavere rasteropasitet ved treff**: Kartlagene vises nå med 75% opasitet (mot 90%) når et verneområde er truffet, slik at underliggende OSM-kart er lettere å lese.

### OCR
- **Konfidensformel normalisert**: Den tidligere divisoren (2.4) ga vilkårlige verdier over 100% som ble klippt. Formelen bruker nå et realistisk intervall (60–260) med en todelt lineær skala: 0–45% for svake resultater, 45–100% for sterke. Verdiene stemmer bedre med faktisk lesekvalitet.
- **+47-prefiks renses automatisk**: OCR-tekst som inneholder `+47 12345678` eller `0047 12345678` ble ikke alltid normalisert til 8-sifret norsk nummer. Nå strippes landprefikset automatisk fra selvstendige telefonnumre.
- **Usikre felt fremheves i skjemaet**: Felt som serveren markerer som usikre (lav OCR-score) får nå gul ramme direkte i skjemaet i 30 sekunder. Varselteksten viser hvilke feltnavn som er usikre i stedet for generell melding.

## Forbedringer
- Kontroller manuelt-varselet lister nå opp spesifikke usikre feltnavn (f.eks. «særlig: navn, telefon»).
