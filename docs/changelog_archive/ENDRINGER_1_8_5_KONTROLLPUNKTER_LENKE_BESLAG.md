# Endringer 1.8.5 - Kontrollpunkter lenke og beslag

Avgrenset feilretting/tilpasning av steg 4 Kontrollpunkter.

## Endret

- Lagt til global lenkestyring øverst i Kontrollpunkter:
  - avkrysning `Lenke`
  - faner `Lenke 1`, `Lenke 2`, `Lenke 3` osv.
  - `Legg til lenke` oppretter ny lenkeside og gjør den aktiv.
- Fjernet synlig funksjonstekst `Avvik + beslag`.
- `Legg til redskap/beslag` vises først når status er satt til `avvik`.
- Når avvik velges opprettes avviks-/beslagsrad automatisk dersom ingen finnes.
- Nye redskap/beslag legges på aktiv lenke.
- Under redskap/beslag er det lagt til autogenerert tekst til beslagsrapport.
- Manuell merknad, kamera og bildeopplasting beholdes per beslag/avviksrad.
- Flere redskap/beslag kan registreres separat innen samme avvik.
- Samme beslagsnummer kan fortsatt velges/gjenbrukes på flere avvik via tidligere beslag/redskap.
- Mobilvisning for lenkefaner og beslagsrapporttekst er tilpasset smal skjerm.

## Ikke endret

- Øvrig struktur i skjemaet er beholdt.
- Ingen databaseskjemaendring.
- Ingen endring i PDF-motor utover at eksisterende datafelter fortsatt brukes.
