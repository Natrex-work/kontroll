# Endringer v79

- `Ny kontroll` oppretter ny sak og lander alltid på steg 1 via `?new_case=1&step=1`.
- Steg 3 sender nå også adresse og poststed til registeroppslag, slik at 1881/Gulesider brukes mer presist når OCR bare finner deler av merkingen.
- Etter treff i katalog prøver systemet nå automatisk et nytt hummerregister-oppslag med navnet som ble funnet, slik at deltakernummer og siste registrerte sesong kan fylles ut selv om disse ikke stod tydelig på bildet.
- Tekstene i steg 3 er oppdatert slik at det er tydelig at 1881/Gulesider inngår i automatisk oppslag.
- Smoke-testen er utvidet med test for ny-sak-redirect og automatisk katalog- og hummerberikelse via `/api/registry/lookup`.
