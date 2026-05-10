# Endringer 1.8.47 - områdetreff og sorterte kontrollpunkter

## Kontrollpunkter

- Område-/fredningspunkter legges ikke lenger inn i kontrollpunktlisten bare fordi valgt art/redskap kan ha områderegler.
- Fredningsområde, stengt område, nullfiskeområde, regulert område og maksimalmålområde blir kontrollpunkt kun når kontrollposisjon faktisk er sjekket og ligger i relevant område.
- Gamle/manuelle `area_status`-verdier uten gyldig lat/lng lager ikke lenger generiske områdepunkter.
- Flere relevante områdetreff fra kart-/områdesjekk gir flere egne automatiske kontrollpunkter, ett per treffområde.
- Treff filtreres mot valgt kontrolltype, art/fiskeri og redskap før de blir kontrollpunkt.

## Sortering

Kontrollpunktene sorteres nå mer faglig:

1. redskap/vak/blåse/merking og tekniske redskapskrav først
2. øvrige ordinære kontrolltema
3. område-/frednings-/forbudspunkter etter redskapspunktene
4. lengdemåling/minstemål/maksimalmål til slutt

Dette gjelder både servergenererte regelpakker og lokal/fallback-visning på iPhone/iPad.

## Kart/områdepanel

- Områdesjekken viser nå en tydelig liste over relevante områdetreff dersom flere områder treffer kontrollposisjonen.
- Listen viser navn, status og kort kartgrunnlag for hvert relevant område.

## Cache

- Appversjon og cache er bumpet til 1.8.47.
- Service worker-cache og kartpreferanser har ny nøkkel for å unngå blanding med eldre PWA-cache.
