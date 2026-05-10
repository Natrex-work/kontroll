# v100 - sted, forbudsområder, OCR og kontrollpunkt-cache

## Endret
- Patruljeformål bruker nå nærmeste sted/kommune eller UTM-posisjon i stedet for teksten «i aktuelt kontrollområde».
- Områdesjekk prøver reverse geocoding når lokal stedsreserve er for grov, slik at nærmeste kommune/stedsnavn fylles bedre.
- «Aktuelle områder og mulig forbud» er endret til «Forbudsområder».
- Forbudsområder filtreres strengere etter valgt art/redskap og lov-/forskriftsrelevans. Irrelevante områder som Svalbard skjules utenfor relevant geografisk/regelverkssammenheng.
- Rettet JavaScript-feilen `currentCoordText` ved kontrollpunkter ved å gjøre UTM/posisjonsfunksjonen tilgjengelig for kontrollpunktlogikken.
- OCR-filter er strammet inn mot 1881/Gulesider-tekster som «Vis nummer» og «Vis telefon».
- Rettet server-side OCR-registry-feil i `_norm`, `_line_has_gear_marker` og `_strip_gear_marker_text`.
- Lagt inn daglig bakgrunnsoppdatering av kontrollpunkt-/regelcache kl. 23:30 Europe/Oslo.

## Ny/oppdatert fil
- `app/services/rules_updater.py`

## Miljøvariabler
- `KV_RULE_UPDATE_ENABLED=1` aktiverer daglig oppdatering.
- `KV_RULE_UPDATE_TIME=23:30` styrer tidspunkt.
- `KV_RULE_UPDATE_TZ=Europe/Oslo` styrer tidssone.
