# Endringer v96 – stabilitet, synk og flerbruker

Fokus i v96 er grunnmur for feltbruk: trygg lokal lagring, serverbackup, konflikthåndtering og kortere brukerstatus.

## Lokal lagring per bruker

- Lokale sakskladder får `owner_user_id`.
- Lokale bilder/lydfiler får `owner_user_id`.
- Lokale filer får `device_id`.
- Lokale kladder/media filtreres på innlogget bruker.
- Ny knapp: `Logg ut og slett lokalt`.

Dette reduserer risikoen for at to brukere på samme mobil/iPad får opp hverandres lokale kladder eller vedlegg.

## Serverbackup av originalfiler

- Vedlegg lastes opp som originalfil til server.
- OCR-/PDF-arbeidskopier holdes adskilt fra originalfil der klienten bruker komprimert bilde.
- Server lagrer metadata:
  - filstørrelse
  - SHA-256
  - device_id
  - local_media_id
  - sync_state
  - server_received_at

Lokale originaler slettes ikke automatisk etter vellykket synk. De markeres som `synced`.

## Konfliktsikker sakslagring

- Saker har nå `version`.
- Autosave og manuell lagring sender forventet versjon.
- Hvis samme sak er endret et annet sted, returneres `409 case_conflict`.
- Klient viser kort status: `Konflikt`.
- Samme `client_mutation_id` kan håndteres idempotent ved retry.

## Atomisk saksnummer

- Ny tabell `case_counters`.
- Saksnummer reserveres i `BEGIN IMMEDIATE`-transaksjon.
- Dette reduserer risiko for duplikat ved samtidig opprettelse.

## Personvern og cache

- Service worker cacher ikke lenger saks-HTML, forhåndsvisning eller dashboard-sider.
- Statikk og kart-/regeldata kan fortsatt caches.
- Ferdige PDF-er og persondata skal ikke caches i service worker.

## UI

- Kortere statuser i lokal synk.
- Mindre hjelpetekst i meny/skjema.
- Knapp for å slette lokale data ved utlogging.

## Verifisert

- Python compileall: OK
- JavaScript node --check: OK
- Fokusert FastAPI-flyt: login, ny sak, edit, autosave, konflikt, evidence upload, preview: OK
- Database-test: atomisk teller, versjonskonflikt og evidence metadata: OK

## Ikke fullverifisert her

- iPhone/Safari
- Render med persistent disk
- ekte GPS/kamera/OCR i felt
- store lydfiler
- SMTP/e-post
- flere samtidige brukere i faktisk drift
