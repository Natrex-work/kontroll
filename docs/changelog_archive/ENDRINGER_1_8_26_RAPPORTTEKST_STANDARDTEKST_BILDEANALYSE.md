# Endringer 1.8.26 – rapporttekster, standardtekster og bildeanalyse

## Hovedmål
Versjon 1.8.26 viderefører arbeidet med å tilpasse autogenererte tekster til Kystvaktens skriveform og føringer i vedlagte straffesaksdokumenter/IKV-eksempler.

## 1. Roller / grunnlag
- Skrevet om autogenerert tekst for `Patruljeformål / begrunnelse`.
- Fjernet klønete formuleringer som `kontrollere fiskerikontroll` og generiske plassholdere.
- Ny standardtekst bruker mer formelle formuleringer:
  - `Formålet var å føre kontroll med ...`
  - `avklare om ... var i samsvar med gjeldende regelverk`
- Hummer, faststående redskap, garn/lenke og sanke-/samleteine har mer sakstilpassede standardtekster.
- Tips-grunnlag skiller tydelig mellom tipsopplysningene og patruljens egne observasjoner/dokumentasjon.

## 3. Person / fartøy
- Bildeanalyseprompten er skjerpet for å lese navn, adresse, postnummer, poststed, mobilnummer og deltakernummer/merking fra fiskeredskap bedre.
- Standard bildeoppløsning for OpenAI/ChatGPT vision er økt:
  - `KV_OPENAI_VISION_MAX_SIDE=4200`
  - `KV_OPENAI_VISION_MIN_LONG_SIDE=2600`
  - `KV_OPENAI_VISION_JPEG_QUALITY=96`
- Prompten forklarer nå tydeligere typiske norske merkestrukturer, deltakernummer og postnummer/poststed.

## Anmeldelse / rapport
- `Anmeldt forhold` viser alle registrerte avvik som egne linjer og gir saksfeltet dynamisk høyde for å unngå klipping.
- Kompakte saksfelt på egenrapport/beslagsrapport/illustrasjonsrapport får også dynamisk høyde.
- `Beskrivelse av det anmeldte forhold` er omskrevet i mer IKV-/Kystvakt-stil:
  - hvem/hva/hvor/når/hvordan
  - kort faktumbeskrivelse
  - kort avviksrelevant hjemmelsgrunnlag
  - tydelig henvisning til egenrapport, beslagsrapport, illustrasjonsmappe/fotomappe og eventuelt avhørsrapport
- `Aktuelle lovhjemler` hentes fra avvik med faktisk status `Avvik`, inkludert både blokkbaserte hjemler og hjemler lagret direkte på kontrollpunktet.
- Lange områdekataloger, koordinatlister og gytefelt-/karttekster trekkes ikke inn i hjemmelsteksten.

## Egenrapport
- Egenrapporten er justert til en mer formell og nøktern patruljenarrativ stil.
- Den gjentar ikke hele anmeldelsen eller full beslags-/posisjonstekst.
- Posisjon skal primært fremgå av beslagsrapporten, ikke gjentas i hver fritekstlinje.
- Kontrollørs fritekstmerknader renses for gamle genererte rapportrester, beslagslister og posisjonsgjentakelser.

## Avhør
- Avhørsrapport holdes fortsatt tom når avhør ikke er merket gjennomført.
- Når avhør er gjennomført, er teksten justert til mer formell rapportstil og inkluderer kort rettighets-/saksorientering.

## Illustrasjonsrapport
- Bildetekster er kortet ned og renset for posisjonsgjentakelser.
- Karttekster beholdes korte og forklarende.

## Cache og deploy
- Versjon bumpet til 1.8.26.
- Service worker/cache-bust oppdatert til 1.8.26.
- JS/CSS lastes med `?v=1.8.26`.
