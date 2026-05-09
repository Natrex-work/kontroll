# V1.1 - Render startup og versjonskonsistens

- Rettet Render-krasj ved oppstart: `rules_updater.py` brukte `settings.data_dir`, men feltet manglet i `Settings`.
- Innført `KV_DATA_DIR` / `settings.data_dir` og oppretter runtime-mappene `data` og `data/cache` ved oppstart.
- Regelcache lagres nå på persistent runtime-lagring under `/var/data/fiskerikontroll/data/cache` på Render.
- Bumped versjon fra `V1.0` til `V1.1` og cache-navn/cache-bust-parametre fra `v1-0` til `v1-1`.
- Oppdatert `render.yaml` og `Dockerfile`, slik at miljøvariabler ikke overstyrer synlig versjon tilbake til gamle `v97/v94`.
- Oppdatert gjenværende admin-script cache-bust og User-Agent fra eldre versjonsnavn.
