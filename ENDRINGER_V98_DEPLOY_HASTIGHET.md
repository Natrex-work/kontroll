# Endringer v98 - deploy, hastighet og byggrydding

## Render-/Docker-bygg

- Satt `DEBIAN_FRONTEND=noninteractive` i Dockerfile for å fjerne debconf-varslene som kom under apt-install.
- Satt `PIP_DISABLE_PIP_VERSION_CHECK=1`, `PIP_NO_CACHE_DIR=1` og `PIP_ROOT_USER_ACTION=ignore` for roligere og litt raskere bygg.
- Oppdatert Dockerfile-versjon til `v98`.
- Beholder Tesseract norsk/engelsk som standard OCR-motor i Docker-bildet.

## Lettere standardinstallasjon

- Fjernet `numpy` og `opencv-python-headless` fra standard `requirements.txt`.
- Lagt disse i `requirements-ocr-advanced.txt` som valgfri pakke.
- Appen bruker ikke OpenCV/numpy ved standard OCR fordi `KV_OCR_ENABLE_DESKEW=0` er standard.
- Hvis avansert deskew senere trengs, installer `requirements-ocr-advanced.txt` og sett `KV_OCR_ENABLE_DESKEW=1`.

## Cache/versjon

- Oppdatert statisk cache, service worker og script-/CSS-versjoner til `v98`.
- Oppdatert Render-miljøverdi for `KV_APP_VERSION_LABEL` til `v98`.

## Vurdering av loggen

Loggen med `debconf: unable to initialize frontend` var ikke en kritisk feil. Bygget fortsatte og apt/pip fullførte. v98 gjør loggen ryddigere og reduserer standard Python-avhengigheter.
