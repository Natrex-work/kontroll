# Endringer V1.5

## Versjonering
- Oppdatert appversjon til `1.5.0` / `V1.5`.
- Oppdatert cache-bust for CSS, JS, service worker og kartcache til V1.5.

## Roller / grunnlag
- Fjernet lange hjelpetekster i steg 1.
- Standardtekst bruker nærmeste sted/stedsnavn fra posisjonen når det finnes.
- Fallbacken `ved registrert kontrollposisjon` er fjernet fra genererte standardtekster.
- Tekstpolering på server erstatter ikke lenger `i aktuelt kontrollområde` med gammel generisk tekst.

## Posisjon / kontrolltype
- Fjernet synlig områdestatus-/GPS-forklaring fra posisjonssiden.
- Fjernet synlig `Art (kan skrives manuelt)`-felt fra saken.
- Endret knapper og tekster fra områdestatus til verneområder.
- Kortet er ryddet opp til `Verneområder`, `Verneområdekart` og `Temalag`.
- Kartet fikk fokusmodus for mobil/iPad via `Åpne kart` og trykk i kartflaten.
- Manuell posisjon med rød nål er beholdt.
- Kart og lister bruker valgt kontrolltype, art/fiskeri og redskap for relevansfiltrering.
- Verneområde-listen inkluderer nå relevante temalag fra kartkatalogen, ikke bare treff i selve posisjonssjekken.

## Person / fartøy / OCR
- Fjernet lang OCR-hjelpetekst.
- Strammet inn OCR/autofyll ved å avvise katalog-/søketekster som navn, blant annet `Vis nummer`, `Vis telefon`, `1881`, `Gulesider`, `personer`, `kart`, `resultat` og liknende.
- 1881/Gulesider brukes bare sekundært ved mobilnummeroppslag i serverlogikken.
- Katalogoppslag får ikke lenger navn/adresse-søk fra OCR som primærkilde.

## Kontrollpunkter / beslag
- Ved avvik vises `Legg til redskap/beslag` automatisk.
- Beslagsnummer normaliseres til mønster som `LBHN26-003-001` fra saksnummeret.
- Avviksrader har korttekst avvik, merknad, kamera og legg til bilde.
- Eksisterende beslag kan velges på nye avvik slik at samme beslag kan ha flere avvik.
- Bildekobling er kortet ned og knyttes direkte til valgt beslag/avvik.

## Illustrasjonsrapport
- Fjernet lang forklaring fra steg 5.
- Valgt funn-kortet viser nå bare kort koblingsstatus for bilde/beslag.
