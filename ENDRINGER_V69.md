# Endringer i v69

- Forbedret OCR for merkeskilt, blåser og vak ved automatisk etikettbeskjæring og perspektivretting.
- OCR prioriterer etikett-kutt når et lyst skilt oppdages i bildet.
- OCR returnerer også strukturerte hint (navn, adresse, poststed, telefon, fiskerimerke, hummerdeltakernummer) som brukes direkte i autofyll.
- Generiske mønstre som `KAR-NOR-114` behandles nå som fiskerimerke som standard, ikke som hummerdeltakernummer.
- Offentlige katalogoppslag prøver nå flere søkestrategier automatisk: telefon, navn+adresse, navn alene og adresse alene.
- OCR-tekst er flyttet bak et kollapsfelt for å gi ryddigere Person / fartøy-visning.
- Cache- og appversjon løftet til v69.
