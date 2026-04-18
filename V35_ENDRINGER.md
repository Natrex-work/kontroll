# V35 endringer

## Admin / tilgangsstyring
- Admin-bruker er nå begrenset til to adminmoduler:
  - brukerstyring
  - slette/gjenopprette kontroller
- Admin har ikke lenger tilgang til vanlig kontrollflyt, kartside eller regelverksside som standard.
- Innlogging sender brukeren til første modul vedkommende faktisk har tilgang til.
- Navigasjonen bygges nå dynamisk ut fra tildelte moduler.

## Brukerstyring
- Admin kan opprette og oppdatere brukere med følgende informasjon:
  - e-postadresse
  - fullt navn
  - adresse
  - telefonnummer
  - fartøystilhørighet
  - anmeldelsesnummer/prefix (f.eks. LBHN)
  - standard anmelder
  - standard vitne
- For vanlige brukere kan admin velge modultilgang per bruker:
  - KV Kontroll
  - Kart og Område
  - Regelverk Fiskeri
- Admin-rolle får faste adminrettigheter og ingen andre moduler.
- Egen knapp for å fjerne bruker fra aktiv bruk er lagt inn.
- Passord kan fortsatt nullstilles fra admin.

## Kontroller - slett / gjenopprett
- Sletting av kontroll er gjort om til myk sletting.
- Slettede kontroller kan gjenopprettes fra ny adminside for kontroller.
- Vanlige brukere ser ikke lenger sletteknapp i kontrollsaken.
- Slettede saker skjules i vanlig kontrollhistorikk og i oppslag i appen.

## Teknisk
- Ny datamodell for brukerrettigheter (`permissions_json`).
- Nye brukerfelt i databasen:
  - address
  - phone
  - vessel_affiliation
- Nye saksfelt i databasen for myk sletting:
  - deleted_at
  - deleted_by
- Migrering legges inn automatisk ved oppstart.
- PWA/cache-versjon og appversjon er løftet til v35.
- Manifest starter nå på `/` slik at brukere sendes til riktig modul etter tilgang.

## Verifisering
- Python-kompilering bestått
- Smoke test bestått
- Testet at:
  - admin lander på brukerstyring
  - admin får tilgang til admin-kontroller
  - admin ikke får tilgang til dashboard/kart uten egne brukerrettigheter
  - ny bruker med modulstyrt tilgang kan opprettes
  - kontrollør kan fortsatt gjennomføre normal kontrollflyt
  - admin kan slette og gjenopprette kontroll
