# Endringer 1.8.16 – kart/områder og lengdemålt avvik

## Hovedendringer

- Appversjon bumpet til `1.8.16`.
- Service worker/cache-navn og statiske JS/CSS-versjonsparametre bumpet til `1.8.16`.
- Kontrollkartet er lagt om til Fiskeridirektoratets `Yggdrasil/Fiskerireguleringer` MapServer som primær kartkilde for regulerings-/verneområder.
- Kartprofilene for valgt kontrolltype, art/fiskeri og redskap er flyttet fra eldre `fiskeridirWMS_fiskeri`-IDer til faktiske `Fiskerireguleringer`-lag:
  - Hummer: Høstingsforskriften, Hummer fredningsområder, Hummer maksimalmålområde, Korallrev, Verneområder bunnhabitat, Raet og Oslofjorden/nullfiske.
  - Torsk: Kysttorsk-forbud, stengte gytefelt, torsk gyte-/oppvekstområder, Borgundfjorden, Breivikfjorden, Oslofjorden/nullfiske og verne-/korallag.
  - Flatøsters, leppefisk og steinbit har egne relevante lagprofiler.
  - Kommersielle profiler har trål-, J-melding-, Svalbard-, torsk/hyse/sei- og øvrige relevante reguleringslag.
- `tapt redskap` er ikke lagt inn i kontrollkartprofilene.
- Kartet henter flere relevante visuelle detaljlag for valgt profil (`14` i stedet for `8`) og er satt opp til å vise områdene direkte i kartet via ArcGIS-rasterlag og detaljlag når zoom/posisjon tillater det.
- Render/Docker-defaults er oppdatert med:
  - `KV_PORTAL_MAPSERVER=https://gis.fiskeridir.no/server/rest/services/Yggdrasil/Fiskerireguleringer/MapServer`
  - `KV_PORTAL_LAYER_SCHEMA_VERSION=v86`
  - `KV_ZONE_CHECK_MAX_LIVE_LAYERS=14`
  - `KV_MAP_BUNDLE_MAX_LAYERS=14`

## Lengdemålt avvik

- Frontend gjenkjenner nå `hummer_lengdekrav` som kontrollpunkt med måling. Dette punktet har både minstemål og maksimumsmål.
- Når et målepunkt settes til `Avvik`, opprettes det automatisk synlig målerad under kontrollpunktet.
- Måleraden har felt for:
  - måling/beslagsreferanse
  - eventuell kobling til tidligere beslag/redskap
  - `Lengdemålt (cm)`
  - gjeldende minstemål
  - gjeldende maksimumsmål
  - posisjon
  - merknad
- Måling vurderes med 0,1 cm presisjon, altså 1 mm.
- Hvis målt verdi er under minstemål, viser appen automatisk avvikstekst med hvor mange cm/mm under minstemålet målingen ligger.
- Hvis målt verdi er på eller over maksimumsmål, viser appen automatisk avvikstekst med hvor mange cm/mm over maksimumsmålet målingen ligger. Lik maksimumsgrensen regnes som avvik der regelteksten sier under maksimumsmål.
- Dersom en lengdemåling gir under minstemål eller på/over maksimumsmål, settes kontrollpunktstatus automatisk til `Avvik`, slik at `Legg til redskap/beslag` vises og bilde/beslag kan knyttes videre.
- For arter med variable minstemål kan kontrollør skrive inn gjeldende minstemål/maksimumsmål i samme rad før automatisk vurdering.

## Kontroller utført

- `python3 -m compileall -q app`
- `node --check` for alle relevante JS-filer
- `python3 render_smoke_test.py`
- Målrettet Python-test av kartprofiler, hummer-lengdekrav og at `tapt redskap` ikke er med i kontrollkartprofilene
- Målrettet statisk JS-test av målefelt/automatisk avvik

## Begrensninger

- `smoke_test.py` ble forsøkt, men timet ut i dette miljøet slik den også tidligere har gjort i tyngre/OCR-relaterte deler.
- Live kartgeometri fra ekstern ArcGIS-tjeneste må sluttverifiseres på Render/iPhone/iPad etter deploy, siden nettverkskall til kartbundle kan være tregt i container.
