# 1.8.14 - Kontrollpunkter: synlig og fungerende Legg til redskap/beslag

Dette er en avgrenset feilretting for steg 4 Kontrollpunkter.

Endret:
- `Legg til redskap/beslag` vises i kontrollpunktet når status er `avvik`.
- Knappen ligger øverst i redskap-/beslagsseksjonen før listen med registrerte beslag.
- Ved klikk opprettes en synlig beslaglinje under kontrollpunktet.
- Linjen har feltene Beslagsnummer, Tidligere beslag, Type beslag, Antall, Posisjon, Avvik, Merknad, Beslagsrapporttekst, Bilde, Kamera og Legg til bilde.
- Beslagsnummer genereres med format som `LBHN 26001-001`.
- Status `avvik` oppretter ikke lenger skjulte beslag automatisk; bruker trykker knappen for å legge til beslag.
- Klikkhåndteringen bruker også `data-action="add-deviation"` for å være mer robust på iPhone/Safari.

Ikke endret:
- Databaseskjema.
- Kart, OCR og PDF-motor utover versjonsnummer/cache-bust.
