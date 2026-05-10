# Endringer 1.8.34 — iPhone-topbar fiks + tilbakerulling av admin-flyt

## Mål
1. **Fikse iPhone-toppen som kolliderer**: tittel, synk-badge og historikk-knapper overlappet hverandre.
2. **Stabilisere brukeropprettelsen**: rulle tilbake admin-flyten til den fungerende v1.8.30-baselinen.

---

## 1. Brukeropprettelse — tilbake til fungerende baseline

### Hva som er gjort
Min v1.8.33 omskrev admin-skjemaet med segmentert rolle-velger, passordgenerator,
SMS-invitasjon og success-modal. Endringene var omfattende (431 linjer i HTML,
296 linjer i JS, ny SMS-funksjon i backend) og introduserte regresjonsrisiko.

For å sikre at brukeropprettelse bare *fungerer*, har jeg satt følgende
filer eksakt tilbake til v1.8.30:

| Fil | Status |
|---|---|
| `app/templates/admin_users.html` | Identisk med v1.8.30 (kun `?v=1.8.34` på script-tag) |
| `app/static/js/admin-users.js` | Identisk med v1.8.30 |
| `app/routers/admin.py` | Identisk med v1.8.30 |

### Hva som er bevart
- Alle ENDRINGER_*-filene fra v1.8.31, 1.8.32, 1.8.33 dokumenterer hva som
  ble gjort. Den polerte CSS-en applies fremdeles til admin-skjemaet
  via eksisterende klassenavn.
- `send_user_invitation()` i `app/services/sms_service.py` ligger igjen,
  men kalles ikke fra noen kode. Den kan brukes senere, eller fjernes.

### Hva som er i v1.8.34 men IKKE påvirker brukeropprettelse
- Bildekomprimering (`image-prep.js`)
- Synk-orkestrator
- Synk-inspektor `/synk`
- All login/dashboard-polish

Disse moduler er isolerte og påvirker ikke admin-flyten.

---

## 2. iPhone-topbar fiks (definitiv)

### Problem (i bildet brukeren sendte)
- "MINFISKERIKONTROLL"-tittelen i caps med stort fontstørrelse
- Tittelen overlappet synk-badgen (sirkelikon)
- Synk-badgen overlappet historikk-knappene (`<` `>`)
- Alt presset sammen i en uleslig blokk

### Rotårsak
På `@media (max-width: 960px)` ble `.brand-home-link .brand-org-name`
satt til `font-size: 1.18rem` mens den arvet `text-transform: uppercase`
og `letter-spacing: 0.08em` fra basis-stilen. "MINFISKERIKONTROLL" =
17 tegn × stor font × ekstra spacing = bredere enn iPhone-skjermen.

### Løsningen (`@media max-width: 480px`)

**Brand-tittel**
- `brand-org-name` → 0.62rem, ellipsis hvis for lang
- `brand-app-name` → 0.96rem, fet, kort
- Begge `white-space: nowrap; overflow: hidden; text-overflow: ellipsis`
- `brand-version` og `sidebar-subtitle` skjult helt
- "Meny"-tekst i logo-trigger skjult (kun ikon)
- Logo komprimert til 36×36 px

**Synk-badge** (mobil)
- 36×36 px sirkel — kun ikon, ingen tekst
- Tellverdi som "notification dot" øverst til høyre (16×16 px sirkel
  med tall, mørk border for å skille fra topbar)

**Historikk-knapper**
- 36×36 px med 10 px radius
- 16×16 px ikoner

**Topbar-layout**
- `display: flex; justify-content: space-between; gap: 8px;`
- `overflow: hidden` på containeren — ingenting kan flyte ut
- `min-width: 0` og `flex: 1 1 auto` på brand-gruppen — krymper riktig

### Ekstra liten skjerm (≤ 380 px – iPhone SE 1.gen)
- `brand-org-name` skjult helt
- Kun appnavn ("Kontroll") + logo + actions vises
- `topbar-actions gap: 4px` for ekstra plass

### Mellomstørrelse (481–960 px – iPhone Plus / mellomstor iPad)
- Mindre styles enn standard mobile
- `brand-org-name`: 0.74rem
- `brand-app-name`: 1.05rem

---

## 3. Hva har ikke endret seg

- Server-kode (Python) er uendret unntatt admin.py som er rullet tilbake
- Ingen DB-endringer
- Login og 2FA-flyt uendret
- Synk-orkestrator og bildekomprimering virker som før
- All polish-CSS fra 1.8.31 er bevart
- Sync-inspektor `/synk` virker som før

---

## 4. Filer endret

```
TILBAKESTILT (til v1.8.30 baseline):
  app/templates/admin_users.html
  app/static/js/admin-users.js
  app/routers/admin.py

OPPDATERT:
  app/static/styles.css                 (+115 linjer for iPhone-topbar)
  app/static/sw.js                      (cache-navn 1-8-34)
  app/config.py                         (versjon 1.8.34)
  Alle templates                        (?v=1.8.34)

URØRT:
  app/static/js/image-prep.js
  app/static/js/sync-orchestrator.js
  app/templates/sync_inspector.html
  Alle login-templates
  Alle øvrige Python-filer
```

---

## 5. Test-sjekkliste

For å verifisere at alt fungerer:

1. **Brukeropprettelse**: Logg inn som admin → /admin/users → fyll inn
   navn + e-post + telefon + passord → klikk "Opprett bruker". Skal
   omdirigere tilbake med "Brukeren er opprettet".

2. **iPhone-topbar**: Åpne `/dashboard` på iPhone. Logo + appnavn vises
   i venstre side, synk-badge (sirkel) + back/forward i høyre side. Ingen
   overlapp. Ingen tekst som flyter ut over kanten.

3. **Synk-status**: Klikk på synk-badgen → `/synk` skal åpne med oversikt
   over lokale vedlegg.

4. **Bildekomprimering**: Ta et bilde i en kontroll → bildet skal lagres
   lokalt og synkes i bakgrunnen, og være ~80% mindre enn original.
