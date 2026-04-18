# Fiskerikontroll

Fiskerikontroll er en FastAPI-basert kontrollapp for kyst- og fiskerioppsyn. Denne pakken er gjort om fra demo til en **brukbar installasjonsklar web-app/PWA** med fokus på:

- sikker innlogging og modultilganger
- kryptering av sensitive felt i databasen
- beskyttet tilgang til vedlegg og eksporterte dokumenter
- iPhone- og iPad-vennlig brukerflate
- enkel administrasjon av brukere og kontroller

## Hva som er endret i produksjonspakken

Denne versjonen skiller seg fra demoen ved at den:

- **ikke** oppretter demo-brukere eller demo-saker som standard
- bruker **feltkryptering** for sensitive personopplysninger i databasen
- beskytter vedlegg og dokumentforhåndsvisninger bak innlogging
- legger på **CSRF-beskyttelse**, strammere cookies og sikkerhets-headere
- rydder bort eksporterte PDF/ZIP-filer etter nedlasting
- er tilpasset bruk på **iPhone og iPad** som installert hjemskjerm-app

## Krav

- Python 3.11+
- HTTPS i faktisk produksjon
- Egen `.env` med hemmeligheter

## Hurtigstart

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

Rediger deretter `.env` og sett minst:

- `SESSION_SECRET`
- `KV_DATA_ENCRYPTION_KEY`
- `KV_ALLOWED_HOSTS`
- eventuelt `KV_BOOTSTRAP_ADMIN_*`

Start appen:

```bash
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

## Opprett første administrator

Anbefalt metode:

```bash
python manage.py create-admin \
  --email admin@domene.no \
  --name "Fullt Navn" \
  --password "SterktPassord123!"
```

Alternativt kan første admin opprettes automatisk ved første oppstart ved å sette:

- `KV_BOOTSTRAP_ADMIN_EMAIL`
- `KV_BOOTSTRAP_ADMIN_NAME`
- `KV_BOOTSTRAP_ADMIN_PASSWORD`


## Native iOS-app for intern distribusjon

Pakken inneholder også en egen mappe `ios_native/` med et **native iOS-prosjekt** for iPhone og iPad. Prosjektet er laget for intern distribusjon og kobler seg til den sikre HTTPS-instansen av Fiskerikontroll.

Se:

- `ios_native/README_IOS_NATIVE.md`
- `ios_native/KontrollOgOppsynNative.xcodeproj`
- `ios_native/export/`

Den native iOS-appen legger til blant annet biometrisk gjenlåsing, domenesperre i webvisningen, dokumentnedlasting til deling/lagring og bedre iPhone/iPad-innpakning rundt samme sikre løsning.

## Bruk på iPhone og iPad

1. Åpne appen i Safari.
2. Velg **Del**.
3. Velg **Legg til på Hjem-skjerm**.
4. Start appen fra ikonet på hjemskjermen.

Pakken inneholder manifest, Apple-meta-tags og mobiltilpasset layout slik at appen åpnes mer som en vanlig app på iPhone og iPad.

## Sikkerhetsoppsett

For faktisk bruk bør du kjøre med:

- `KV_PRODUCTION_MODE=1`
- `KV_SESSION_HTTPS_ONLY=1`
- sterk `SESSION_SECRET`
- egen `KV_DATA_ENCRYPTION_KEY`
- HTTPS via reverse proxy eller plattform

### Hva som er kryptert

Sensitive felt i bruker- og saksdata lagres kryptert i databasen, blant annet navn, adresse, telefon, patrulje-/forklaringstekster, mistenktopplysninger og andre tekstfelt som kan inneholde personopplysninger.

### Hva som er tilgangsbeskyttet

- vedlegg
- lydfiler
- kartforhåndsvisning i dokumentpakke
- eksporterte PDF- og ZIP-dokumenter

## Admin-funksjoner

Admin er begrenset til:

- slette og gjenopprette kontroller
- legge til og deaktivere brukere
- styre hvilke moduler hver bruker har tilgang til
- registrere e-post, fullt navn, adresse, telefon, fartøystilhørighet, saksnummerprefix, standard anmelder og standard vitne

## Demo-data

Hvis du fortsatt ønsker demooppsett i et testmiljø, kan du sette:

```env
KV_BOOTSTRAP_DEMO_USERS=1
KV_BOOTSTRAP_DEMO_CASES=1
```

Dette bør ikke brukes i produksjon.

## Viktig anbefaling før produksjonssetting

Denne pakken er betydelig mer robust enn demoen, men ved reell drift anbefales også:

- drift bak HTTPS-reverse-proxy
- sikkerhetskopi av database og opplastinger
- kryptert disk på server/enhet
- logging og tilgangskontroll på driftsmiljøet
- egen sikkerhetstest før ordinær bruk
