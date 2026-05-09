# Dokumentmaler v88

Originalmalene som er lastet opp av bruker er lagret her som kildegrunnlag:

- Politiskjema - Dokumentliste.dot
- Politiskjema - Avhør av vitne.dot
- Politiskjema - Avhør av siktede.dot
- Politiskjema - Ransaking-beslag.dot
- Anmeldelse_Mal.xlsx

Runtime-generering skjer fortsatt direkte til PDF med ReportLab, men nå med politiskjema-bakgrunnene i `app/pdf_templates/page-01.png` osv. Det gir mer stabil serverdrift enn å åpne gamle `.dot`-maler med LibreOffice for hver eksport. Feltplassering og dokumentrekkefølge er bundet i `app/pdf_export.py`.

Dokumentrekkefølge:

1. Dokumentliste
2. Anmeldelse / hoveddokument
3. Egenrapport
4. Avhør / forklaring
5. Rapport om ransaking / beslag
6. Illustrasjonsrapport
