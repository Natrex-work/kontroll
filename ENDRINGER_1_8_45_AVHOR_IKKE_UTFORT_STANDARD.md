# Endringer 1.8.47 — Avhør "ikke utført" som standard for nye saker

## Hva er endret

Nye saker har nå **«Avhør ikke gjennomført»** automatisk avkrysset, og
avhørsdetaljene er **kollapset**. Dette var meningen i v1.8.41, men var
brutt på grunn av to bug-er.

---

## Bug-analyse

### Bug 1 — Database-default
```sql
-- v1.8.44 og før:
interview_not_conducted INTEGER NOT NULL DEFAULT 0  -- 0 = avhør gjennomført
```

Standard ved opprettelse av ny sak var `0` (gjennomført), motsatt av hva
brukeren forventet. Skulle vært `1` (ikke gjennomført).

### Bug 2 — Hardkodet 0 i `create_case`
```python
# app/db.py — INSERT-statement i create_case()
'[]', '[]', '[]', '[]', '[]',
0,  # ← interview_not_conducted hardkodet til 0
None, None, ...
```

Selv om DDL-defaulten var blitt fikset, ville `INSERT` med eksplisitt `0`
overstyre det. Begge må endres.

### Bug 3 — Template-logikk for kompleks
```jinja
{# v1.8.41-44: tre-tilstandslogikk som var skjør #}
{% if case.interview_not_conducted is sameas none or case.interview_not_conducted %}checked{% endif %}
{% if case.interview_not_conducted is not sameas none and not case.interview_not_conducted %}open{% endif %}
```

Med to bugs i underliggende data, måtte template "redde" det med en
kompleks tre-tilstandslogikk (NULL/0/1). Når bug 1+2 er fikset, kan
template forenklet til vanlig truthy/falsy-sjekk.

---

## Løsning

### 1. Database-default endret
```sql
interview_not_conducted INTEGER NOT NULL DEFAULT 1
```

Påvirker kun **nye** rader. Eksisterende saker beholder sin lagrede verdi.

### 2. `create_case` setter eksplisitt 1
```python
# app/db.py — create_case()
# 1.8.47: Default to interview_not_conducted=1 (ikke gjennomført).
# Brukere må eksplisitt huke av at avhør ER gjennomført.
1,  # interview_not_conducted = 1 = ikke gjennomført
```

### 3. Template forenklet
```jinja
{# Checkbox krysset hvis interview_not_conducted er truthy (1) #}
<input ... {% if case.interview_not_conducted %}checked{% endif %} />

{# Details åpen kun hvis interview_not_conducted er falsy (0 = avhør gjennomført) #}
<details ...{% if not case.interview_not_conducted %} open{% endif %}>
```

### 4. JavaScript auto-toggler details
```javascript
// app/static/js/case-app.js — syncInterviewDisabledState()
// Når brukeren krysser av "Avhør ikke gjennomført", lukk details.
// Når de fjerner avkrysningen (avhør ER gjennomført), åpne details.
var details = document.getElementById('interview-details');
if (details) {
  details.open = !disabled;
}
```

---

## Verifiserte scenarier (4/4)

| Scenario | DB-verdi | Checkbox | Details |
|---|---|---|---|
| **Ny sak** (DB-default 1) | `1` | ✓ checked | collapsed |
| Eksisterende: avhør gjennomført | `0` | ☐ unchecked | open |
| Eksisterende: avhør ikke gjennomført | `1` | ✓ checked | collapsed |
| Legacy NULL (gamle rader) | `None` | ☐ unchecked | open |

Den siste raden viser at databaser med eldre data (NULL) viser feltene
som tilgjengelige slik at brukeren kan fylle dem ut hvis de ønsker.
Migrasjon i `_ensure_column` setter NULL → 0 for gamle rader, så denne
edge-casen oppstår ikke i praksis.

---

## Filer endret

```
MOD:
  app/db.py                       — DDL DEFAULT 0→1, create_case INSERT 0→1
  app/templates/case_form.html    — forenklet checkbox/details-logikk
  app/static/js/case-app.js       — auto-toggle details i syncInterviewDisabledState
  app/static/sw.js                — cache-bump
  app/config.py                   — versjon 1.8.47
  alle templates                  — ?v=1.8.47
```

## Filer bevisst IKKE endret

- `app/services/case_service.py` — form-handleren håndterer fortsatt
  truthy/falsy-mapping korrekt (ingen endring nødvendig)
- Eksisterende sakers verdier — bevart, ingen migrasjon
- Sikkerhets-, kart- og kontrollpunkt-logikk

---

## Versjon

`1.8.44` → `1.8.47`. Alle `?v=1.8.47`. SW-cache `kv-kontroll-1-8-47-static`.
