# V101 cache/sted/forbudsområder

- Hard cache-bust til v101 i alle JS/CSS/SW-referanser.
- Nærmeste sted/kommune fylles fra `/api/zones/check` også når saken åpnes med eksisterende koordinater.
- Patruljeformål bruker nærmeste sted/kommune eller UTM, ikke generisk «aktuelt kontrollområde».
- Forbudsområder filtreres strengere mot valgt art/redskap og lovregulert område.
- `/api/zones/check` fjernes fra service-worker API-cache slik at nærmeste sted/forbudsområder ikke blir hengende fra gammel posisjon.
- `currentCoordText` eksponeres trygt som helper for kontrollpunkter.
