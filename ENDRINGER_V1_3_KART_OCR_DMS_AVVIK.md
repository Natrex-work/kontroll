# Endringer V1.5 - kart, OCR, DMS og avvik

## Versjonering og cache
- Appversjon er oppdatert til `1.5.0` / `V1.5`.
- Service worker, cache-navn og statiske JS/CSS-parametre er bumpet til V1.5.

## Kart og område
- Steget er tydeligere rettet mot `Kart og område`.
- Koordinatvisning i klient og PDF bruker DMS-format i stedet for UTM.
- Kartlag for kystnære fiskeridata/fiskeriområder filtreres bort fra verneområde-/temakartvisningen.
- Kartkatalogen prioriterer og viser bare restriktive lov-/forskrifts-/J-meldingslag, for eksempel fredning, forbud, stengte felt, reguleringer og totalforbud.
- Temalag og områder er beholdt kollapsbare og justert responsivt slik at lange temalag ikke tvinger zoom på mobil.
- Alle relevante regulerings-/verneområder for valgt kontrolltype, fiskeri/art og redskap kan vises under kart/område.

## Standardtekster
- Standardtekst-polering erstatter `ved kontrollposisjonen` og `i aktuelt kontrollområde` med samme stedsinformasjon som brukes for nærmeste sted når dette finnes.
- Når sted mangler, brukes nøytral fallback til oppgitt posisjon, ikke gammel kontrollområde-tekst.

## OCR/person/fartøy
- Automatisk OCR-flyt leser kun data fra opplastet bilde.
- Automatisk oppslag mot eksterne katalogkilder etter OCR er deaktivert, slik at 1881/Gulesider ikke overstyrer bildebaserte felt.
- OCR-parseren avviser logo-/søketekster som `1881`, `Gulesider`, `Vis nummer`, `Vis telefon`, `personer`, `bedrifter`, `kart` og lignende ved navn/adresse/poststed.
- Felt fylles mer forsiktig slik at eksisterende bilde- eller brukerdata ikke overskrives uten eksplisitt handling.

## Kontrollpunkter, avvik og beslag
- Avvik som registreres manuelt eller automatisk får redskap-/beslagsseksjon med korttekst, merknad og bilde/kamera.
- Beslagsnummer følger formatet `LBHN26-[saksnr]-[løpenummer]` i klientlogikken.
- Samme beslag kan velges og gjenbrukes på flere avvik.
- Dersom områdesjekken gir flere relevante verne-/reguleringsområder, opprettes separate automatiske avvik for hvert relevant område.
- Avvik støtter flere lenker per avvik, vist som separate `Lenke 1`, `Lenke 2`, `Lenke 3` osv.

## Teststatus
- Python-kompilering av `app` er OK.
- JS-syntakskontroll av sentrale scripts er OK.
- ZIP-test er OK.
- Smoke-testene krever FastAPI i miljøet og ble derfor ikke kjørt ferdig i dette lokale testmiljøet.
