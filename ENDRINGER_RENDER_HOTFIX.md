# Endringer i Render-hotfixen

- rettet `uvicorn==0.45.0` til `uvicorn==0.43.0` i `requirements.txt`
- appen auto-godkjenner nå `RENDER_EXTERNAL_HOSTNAME` / `RENDER_EXTERNAL_URL`
- `KV_ALLOWED_HOSTS` normaliseres nå bedre, også når full URL legges inn
- foreldremappen til `KV_DB_PATH` opprettes automatisk ved oppstart
- lagt ved `RENDER_DEPLOY_GUIDE.md`
- lagt ved `render_smoke_test.py`
