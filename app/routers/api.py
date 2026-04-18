from __future__ import annotations

from fastapi import APIRouter, Query, Request
from fastapi.responses import JSONResponse

from .. import live_sources
from ..dependencies import require_any_permission, require_permission
from ..security import enforce_csrf
from ..pdf_export import build_text_drafts
from ..schemas import SummarySuggestRequest, TextPolishRequest
from ..services.registry_service import gear_summary, lookup_registry
from ..services.rules_service import check_zone_status, get_rule_bundle_with_live_sources

router = APIRouter()


def _basis_opening_phrase(case_basis: str, source_name: str = '') -> str:
    raw_source = str(source_name or '').strip()
    normalized = raw_source.lower()
    default_sources = {
        '',
        'kystvaktpatrulje',
        'kv patrulje',
        'kystvakten lettbåt',
        'kystvaktens lettbåt',
    }
    if case_basis not in {'tips', 'anmeldelse'} and normalized not in default_sources:
        return f'Det ble fra lettbåt fra {raw_source} gjennomført'
    return 'Det ble fra Kystvakten lettbåt gjennomført'


@router.post('/api/text/polish')
def api_text_polish(request: Request, payload: TextPolishRequest):
    require_permission(request, 'kv_kontroll', detail='Brukeren har ikke tilgang til KV Kontroll.')
    enforce_csrf(request)
    mode = str(payload.mode or 'generic').strip()
    text_in = str(payload.text or '').strip()
    case_basis = str(payload.case_basis or '').strip() or 'patruljeobservasjon'
    source_name = str(payload.source_name or '').strip()
    subject = str(payload.subject or '').strip()
    location = str(payload.location or '').strip()
    if not text_in:
        return JSONResponse({'text': ''})
    cleaned = ' '.join(text_in.replace('\r', '\n').split())
    cleaned = cleaned.replace(' ,', ',').replace(' .', '.').replace(' :', ':')
    if cleaned and cleaned[0].islower():
        cleaned = cleaned[0].upper() + cleaned[1:]
    if mode == 'basis':
        opening = _basis_opening_phrase(case_basis, source_name)
        sentence_starters = (
            opening.lower(),
            'det ble fra kystvakten lettbåt gjennomført',
            'det ble fra lettbåt fra',
            'den ',
            'kontrollen ',
            'patrulje ',
            'bakgrunnen ',
            'formålet ',
        )
        if not cleaned.lower().startswith(sentence_starters):
            cleaned = f"{opening} {cleaned.rstrip('.')}".strip()
        if location and location.lower() not in cleaned.lower():
            cleaned = cleaned.rstrip('.') + f' ved {location}.'
        else:
            cleaned = cleaned.rstrip('.') + '.'
    elif mode == 'interview_summary':
        subject_text = subject or 'Avhørte'
        cleaned = f"{subject_text} forklarte i hovedsak følgende: {cleaned.rstrip('.')} .".replace(' .', '.')
    else:
        cleaned = cleaned.rstrip('.') + '.'
    return JSONResponse({'text': cleaned})


@router.get('/api/rules')
def api_rules(request: Request, control_type: str = '', species: str = '', gear_type: str = '', area_status: str = '', control_date: str = '', lat: float | None = Query(default=None, ge=-90, le=90), lng: float | None = Query(default=None, ge=-180, le=180)):
    require_any_permission(request, ['regelverk', 'kv_kontroll'], detail='Brukeren har ikke tilgang til regelverksoppslag.')
    bundle = get_rule_bundle_with_live_sources(control_type=control_type, species=species, gear_type=gear_type, area_status=area_status, control_date=control_date, area_name=request.query_params.get('area_name', ''), area_notes=request.query_params.get('area_notes', ''), lat=lat, lng=lng)
    return JSONResponse(bundle)


@router.get('/api/zones/check')
def api_zones_check(request: Request, lat: float = Query(..., ge=-90, le=90), lng: float = Query(..., ge=-180, le=180), species: str = '', gear_type: str = ''):
    require_any_permission(request, ['kart', 'kv_kontroll'], detail='Brukeren har ikke tilgang til kart- og omradekontroll.')
    return JSONResponse(check_zone_status(lat, lng, species=species, gear_type=gear_type))


@router.get('/api/map/catalog')
def api_map_catalog(request: Request):
    require_any_permission(request, ['kart', 'kv_kontroll'], detail='Brukeren har ikke tilgang til kart- og omradekontroll.')
    return JSONResponse({'portal_url': live_sources.MAP_PORTAL_URL, 'layers': live_sources.portal_layer_catalog()})


@router.get('/api/map/features')
def api_map_features(request: Request, layer_id: int = Query(..., ge=0), bbox: str = ''):
    require_any_permission(request, ['kart', 'kv_kontroll'], detail='Brukeren har ikke tilgang til kart- og omradekontroll.')
    parsed_bbox = None
    if bbox:
        try:
            parts = [float(part) for part in str(bbox).split(',')]
            if len(parts) == 4:
                min_lng, min_lat, max_lng, max_lat = parts
                parsed_bbox = (min_lng, min_lat, max_lng, max_lat)
        except Exception:
            parsed_bbox = None
    try:
        data = live_sources.fetch_portal_geojson(layer_id, bbox=parsed_bbox)
        return JSONResponse(data)
    except Exception as exc:
        return JSONResponse({'type': 'FeatureCollection', 'features': [], 'error': str(exc)}, status_code=200)


@router.get('/api/registry/lookup')
def api_registry_lookup(request: Request, phone: str = '', vessel_reg: str = '', radio_call_sign: str = '', name: str = '', tag_text: str = '', hummer_participant_no: str = ''):
    require_permission(request, 'kv_kontroll', detail='Brukeren har ikke tilgang til KV Kontroll.')
    return JSONResponse(lookup_registry(phone=phone, vessel_reg=vessel_reg, radio_call_sign=radio_call_sign, name=name, tag_text=tag_text, hummer_participant_no=hummer_participant_no))


@router.get('/api/gear/summary')
def api_gear_summary(request: Request, phone: str = '', name: str = '', address: str = '', species: str = '', gear_type: str = '', area_name: str = '', control_type: str = '', area_status: str = '', vessel_reg: str = '', radio_call_sign: str = '', hummer_participant_no: str = '', case_id: int | None = None):
    require_permission(request, 'kv_kontroll', detail='Brukeren har ikke tilgang til KV Kontroll.')
    return JSONResponse(gear_summary(phone=phone, name=name, address=address, species=species, gear_type=gear_type, area_name=area_name, control_type=control_type, area_status=area_status, vessel_reg=vessel_reg, radio_call_sign=radio_call_sign, hummer_participant_no=hummer_participant_no, case_id=case_id))


@router.post('/api/summary/suggest')
def api_summary_suggest(request: Request, payload: SummarySuggestRequest):
    require_permission(request, 'kv_kontroll', detail='Brukeren har ikke tilgang til KV Kontroll.')
    enforce_csrf(request)
    case_row = {'summary': '', 'case_basis': payload.case_basis or 'patruljeobservasjon', 'control_type': payload.control_type or '', 'species': payload.species or '', 'fishery_type': payload.fishery_type or payload.species or '', 'gear_type': payload.gear_type or '', 'location_name': payload.location_name or '', 'area_name': payload.area_name or '', 'area_status': payload.area_status or '', 'suspect_name': payload.suspect_name or '', 'basis_details': payload.basis_details or '', 'start_time': payload.start_time or '', 'latitude': payload.latitude, 'longitude': payload.longitude}
    drafts = build_text_drafts(case_row, payload.findings)
    return JSONResponse(drafts)
