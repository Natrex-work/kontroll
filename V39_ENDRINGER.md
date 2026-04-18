# V39 endringer

## Patruljeformål / begrunnelse
- Starten på standardtekstene under **Patruljeformål / begrunnelse** er endret slik at de nå starter med:
  - **"Det ble fra Kystvakten lettbåt gjennomført ..."** når standard Kystvakt-intro brukes.
  - **"Det ble fra lettbåt fra [fartøynavn] gjennomført ..."** når bruker har lagt inn eget fartøynavn/patruljenavn.
- Endringen er lagt inn for alle standardtekster som settes inn med **Sett inn standardtekst**.
- **Formulering**-knappen sender nå også med patruljenavn/fartøynavn, slik at teksten beholder riktig start når den blir språkvasket.
- Serverlogikken som lager automatisk kontrollgrunnlag bruker samme nye startformulering som frontend.

## Tekniske justeringer
- `TextPolishRequest` støtter nå `source_name`.
- Standard opprettet sak bruker nå `Kystvakten lettbåt` som standard patruljenavn.
- Appversjon og service worker-cache er løftet til **v39**.

## Verifisering
- Python-kompilering bestått.
- JavaScript-syntakssjekk bestått.
- Smoke test bestått med egen testdatabase.
