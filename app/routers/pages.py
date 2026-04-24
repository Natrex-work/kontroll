from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from starlette.status import HTTP_303_SEE_OTHER

from .. import catalog, db, live_sources
from ..dependencies import first_allowed_path, require_permission, require_user
from ..ui import render_template

router = APIRouter()


@router.get('/dashboard', response_class=HTMLResponse)
def dashboard(request: Request, status_filter: str = 'all'):
    user = require_permission(request, 'kv_kontroll', detail='Brukeren har ikke tilgang til KV Kontroll.')
    cases = db.list_cases(user, status_filter=status_filter)
    counts = db.case_counts(user)
    return render_template(request, 'dashboard.html', cases=cases, counts=counts, status_filter=status_filter)


@router.get('/kart', response_class=HTMLResponse)
def map_overview(request: Request):
    require_permission(request, 'kart', detail='Brukeren har ikke tilgang til Kart og Område.')
    return render_template(request, 'map_overview.html', portal_layers=live_sources.portal_layer_catalog_page_payload())


@router.get('/regelverk', response_class=HTMLResponse)
def rules_overview(request: Request):
    require_permission(request, 'regelverk', detail='Brukeren har ikke tilgang til Regelverk Fiskeri.')
    return render_template(request, 'rules_overview.html', law_browser=catalog.law_browser_data(), control_types=catalog.control_labels())


@router.get('/kontroller', response_class=HTMLResponse)
def controls_overview(request: Request, status_filter: str = 'all'):
    user = require_permission(request, 'kv_kontroll', detail='Brukeren har ikke tilgang til KV Kontroll.')
    cases = db.list_cases(user, status_filter=status_filter)
    counts = db.case_counts(user)
    return render_template(request, 'controls_overview.html', cases=cases, counts=counts, status_filter=status_filter)


@router.get('/go')
def go_to_default(request: Request):
    user = require_user(request)
    return RedirectResponse(first_allowed_path(user) or '/login', status_code=HTTP_303_SEE_OTHER)
