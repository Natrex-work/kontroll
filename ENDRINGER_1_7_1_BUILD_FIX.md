# Endringer 1.7.1 - Render build-fiks

## Rettet

- Rettet Docker/Render build-feil der `pip install -r requirements.txt` stoppet på `pillow_heif==1.5.0`.
- `pillow_heif==1.5.0` er erstattet med `pillow-heif==1.3.0`, som finnes som ferdig Linux-hjul for Python 3.11.
- Versjon/cache er oppdatert fra `1.7.0` til `1.7.1` for å sikre at ny pakke og nye statiske filer tas i bruk etter deploy.

## Hvorfor

Render-feilen viste at PyPI/byggeindeksen ikke hadde `pillow_heif==1.5.0`, og at høyeste tilgjengelige versjon i loggen var `1.3.0`. Koden importerer pakken som `pillow_heif`, men pip-pakken kan trygt angis med kanonisk navn `pillow-heif`.

## Testet

- Python-kompilering av `app/`
- JS-syntakskontroll
- `smoke_test.py`
- `render_smoke_test.py`
- ZIP-integritet
