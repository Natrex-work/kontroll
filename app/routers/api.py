from __future__ import annotations

from fastapi import APIRouter, File, HTTPException, Query, Request, UploadFile
from pathlib import Path
from collections import OrderedDict
import hashlib
import os
import time
from fastapi.responses import JSONResponse
from starlette.concurrency import run_in_threadpool

from .. import live_sources
from ..dependencies import require_any_permission, require_permission
from ..security import enforce_csrf
from ..pdf_export import build_text_drafts
from ..schemas import SummarySuggestRequest, TextPolishRequest
from ..services.ocr_service import extract_text_from_image
OCR_MAX_UPLOAD_MB = max(2, min(20, int(os.getenv('KV_OCR_MAX_IMAGE_MB', '12') or '12')))
MAP_BUNDLE_MAX_LAYERS = max(4, min(20, int(os.getenv('KV_MAP_BUNDLE_MAX_LAYERS', '8') or '10')))
OCR_CACHE_TTL_SECONDS = max(60, min(3600, int(os.getenv('KV_OCR_CACHE_TTL_SECONDS', '600') or '600')))
OCR_CACHE_MAX_ENTRIES = max(8, min(128, int(os.getenv('KV_OCR_CACHE_MAX_ENTRIES', '32') or '32')))
_OCR_RESULT_CACHE: OrderedDict[str, tuple[float, dict]] = OrderedDict()

from ..services.registry_service import gear_summary, lookup_registry
from .. import registry
from ..services.rules_service import check_zone_status, get_rule_bundle_with_live_sources
from ..validation import sanitize_original_filename, validate_saved_file_size

router = APIRouter()


def _get_ocr_cache(key: str) -> dict | None:
    now = time.monotonic()
    expired: list[str] = []
    for cache_key, (created, _payload) in list(_OCR_RESULT_CACHE.items()):
        if now - created > OCR_CACHE_TTL_SECONDS:
            expired.append(cache_key)
    for cache_key in expired:
        _OCR_RESULT_CACHE.pop(cache_key, None)
    row = _OCR_RESULT_CACHE.get(key)
    if not row:
        return None
    created, payload = row
    if now - created > OCR_CACHE_TTL_SECONDS:
        _OCR_RESULT_CACHE.pop(key, None)
        return None
    _OCR_RESULT_CACHE.move_to_end(key)
    out = dict(payload)
    out['cached'] = True
    return out


def _put_ocr_cache(key: str, payload: dict) -> None:
    if not payload or not str(payload.get('text') or '').strip():
        return
    _OCR_RESULT_CACHE[key] = (time.monotonic(), dict(payload))
    _OCR_RESULT_CACHE.move_to_end(key)
    while len(_OCR_RESULT_CACHE) > OCR_CACHE_MAX_ENTRIES:
        _OCR_RESULT_CACHE.popitem(last=False)



def _parse_optional_float_query(value: str | float | int | None, *, field_name: str, min_value: float, max_value: float) -> float | None:
    raw = str(value or '').strip().replace(',', '.')
    if not raw:
        return None
    try:
        parsed = float(raw)
    except (TypeError, ValueError) as exc:
        raise HTTPException(status_code=422, detail=f'Ugyldig verdi for {field_name}.') from exc
    if parsed < min_value or parsed > max_value:
        raise HTTPException(status_code=422, detail=f'Ugyldig verdi for {field_name}.')
    return parsed


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
    require_permission(request, 'kv_kontroll', detail='Brukeren har ikke tilgang til Minfiskerikontroll.')
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
def api_rules(request: Request, control_type: str = '', species: str = '', gear_type: str = '', area_status: str = '', control_date: str = '', lat: str = '', lng: str = ''):
    require_any_permission(request, ['regelverk', 'kv_kontroll'], detail='Brukeren har ikke tilgang til regelverksoppslag.')
    parsed_lat = _parse_optional_float_query(lat, field_name='lat', min_value=-90, max_value=90)
    parsed_lng = _parse_optional_float_query(lng, field_name='lng', min_value=-180, max_value=180)
    bundle = get_rule_bundle_with_live_sources(control_type=control_type, species=species, gear_type=gear_type, area_status=area_status, control_date=control_date, area_name=request.query_params.get('area_name', ''), area_notes=request.query_params.get('area_notes', ''), lat=parsed_lat, lng=parsed_lng)
    return JSONResponse(bundle)


@router.get('/api/zones/check')
def api_zones_check(request: Request, lat: float = Query(..., ge=-90, le=90), lng: float = Query(..., ge=-180, le=180), species: str = '', gear_type: str = '', control_type: str = ''):
    require_any_permission(request, ['kart', 'kv_kontroll'], detail='Brukeren har ikke tilgang til kart- og omradekontroll.')
    return JSONResponse(check_zone_status(lat, lng, species=species, gear_type=gear_type, control_type=control_type))


@router.get('/api/map/catalog')
def api_map_catalog(request: Request, fishery: str = '', control_type: str = '', gear_type: str = '', fresh: bool = False):
    require_any_permission(request, ['kart', 'kv_kontroll'], detail='Brukeren har ikke tilgang til kart- og omradekontroll.')
    layers = live_sources.portal_layer_catalog(fishery=fishery, control_type=control_type, gear_type=gear_type) if fresh else live_sources.portal_layer_catalog_page_payload(fishery=fishery, control_type=control_type, gear_type=gear_type)
    return JSONResponse({'portal_url': live_sources.MAP_PORTAL_URL, 'layers': layers})




@router.get('/api/map/identify')
def api_map_identify(request: Request, lat: float = Query(..., ge=-90, le=90), lng: float = Query(..., ge=-180, le=180), layer_ids: str = ''):
    require_any_permission(request, ['kart', 'kv_kontroll'], detail='Brukeren har ikke tilgang til kart- og omradekontroll.')
    parsed_ids = []
    if layer_ids:
        for part in str(layer_ids).split(','):
            part = part.strip()
            if not part:
                continue
            try:
                parsed_ids.append(int(part))
            except Exception:
                continue
    return JSONResponse(live_sources.identify_portal_point(lat, lng, layer_ids=parsed_ids))

def _expand_bbox(bbox: tuple[float, float, float, float], factor: float = 1.6) -> tuple[float, float, float, float]:
    min_lng, min_lat, max_lng, max_lat = bbox
    width = max(0.01, max_lng - min_lng)
    height = max(0.01, max_lat - min_lat)
    cx = min_lng + (width / 2.0)
    cy = min_lat + (height / 2.0)
    half_w = max(0.08, width * factor / 2.0)
    half_h = max(0.08, height * factor / 2.0)
    return (cx - half_w, cy - half_h, cx + half_w, cy + half_h)


@router.get('/api/map/bundle')
def api_map_bundle(request: Request, bbox: str = '', layer_ids: str = ''):
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
    parsed_ids = []
    if layer_ids:
        for part in str(layer_ids).split(','):
            part = part.strip()
            if not part:
                continue
            try:
                parsed_ids.append(int(part))
            except Exception:
                continue
    truncated_layer_ids = False
    if len(parsed_ids) > MAP_BUNDLE_MAX_LAYERS:
        parsed_ids = parsed_ids[:MAP_BUNDLE_MAX_LAYERS]
        truncated_layer_ids = True
    try:
        data = live_sources.fetch_portal_bundle(layer_ids=parsed_ids or None, bbox=parsed_bbox)
        if isinstance(data, dict):
            data.setdefault('ok', True)
            data.setdefault('requested_layer_ids', parsed_ids)
            data.setdefault('truncated_layer_ids', truncated_layer_ids)
        return JSONResponse(data)
    except Exception as exc:
        return JSONResponse({'ok': False, 'type': 'FeatureCollection', 'features': [], 'layers': [], 'error': str(exc), 'bbox': list(parsed_bbox) if parsed_bbox else None, 'requested_layer_ids': parsed_ids, 'truncated_layer_ids': truncated_layer_ids}, status_code=200)




@router.get('/api/map/offline-package')
def api_map_offline_package(request: Request, bbox: str = '', layer_ids: str = '', expand: float = Query(default=1.6, ge=1.0, le=3.0)):
    require_any_permission(request, ['kart', 'kv_kontroll'], detail='Brukeren har ikke tilgang til kart- og omradekontroll.')
    parsed_bbox = None
    if bbox:
        try:
            parts = [float(part) for part in str(bbox).split(',')]
            if len(parts) == 4:
                parsed_bbox = (parts[0], parts[1], parts[2], parts[3])
        except Exception:
            parsed_bbox = None
    parsed_ids = []
    if layer_ids:
        for part in str(layer_ids).split(','):
            part = part.strip()
            if not part:
                continue
            try:
                parsed_ids.append(int(part))
            except Exception:
                continue
    truncated_layer_ids = False
    if len(parsed_ids) > MAP_BUNDLE_MAX_LAYERS:
        parsed_ids = parsed_ids[:MAP_BUNDLE_MAX_LAYERS]
        truncated_layer_ids = True
    if not parsed_bbox:
        return JSONResponse({'ok': False, 'message': 'Mangler kartutsnitt.', 'bundle': {'type': 'FeatureCollection', 'features': [], 'layers': []}}, status_code=400)
    offline_bbox = _expand_bbox(parsed_bbox, factor=float(expand or 1.6))
    try:
        bundle = live_sources.fetch_portal_bundle(layer_ids=parsed_ids or None, bbox=offline_bbox, max_age_seconds=24 * 3600)
        return JSONResponse({'ok': True, 'bundle': bundle, 'requested_bbox': list(parsed_bbox), 'offline_bbox': list(offline_bbox), 'layer_ids': parsed_ids, 'truncated_layer_ids': truncated_layer_ids})
    except Exception as exc:
        return JSONResponse({'ok': False, 'message': str(exc), 'bundle': {'type': 'FeatureCollection', 'features': [], 'layers': []}, 'requested_bbox': list(parsed_bbox), 'offline_bbox': list(offline_bbox), 'layer_ids': parsed_ids, 'truncated_layer_ids': truncated_layer_ids}, status_code=200)

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
def api_registry_lookup(request: Request, phone: str = '', vessel_reg: str = '', radio_call_sign: str = '', name: str = '', address: str = '', post_place: str = '', tag_text: str = '', hummer_participant_no: str = ''):
    require_permission(request, 'kv_kontroll', detail='Brukeren har ikke tilgang til Minfiskerikontroll.')
    return JSONResponse(lookup_registry(phone=phone, vessel_reg=vessel_reg, radio_call_sign=radio_call_sign, name=name, address=address, post_place=post_place, tag_text=tag_text, hummer_participant_no=hummer_participant_no))


@router.get('/api/gear/summary')
def api_gear_summary(request: Request, phone: str = '', name: str = '', address: str = '', species: str = '', gear_type: str = '', area_name: str = '', control_type: str = '', area_status: str = '', vessel_reg: str = '', radio_call_sign: str = '', hummer_participant_no: str = '', case_id: int | None = None):
    require_permission(request, 'kv_kontroll', detail='Brukeren har ikke tilgang til Minfiskerikontroll.')
    return JSONResponse(gear_summary(phone=phone, name=name, address=address, species=species, gear_type=gear_type, area_name=area_name, control_type=control_type, area_status=area_status, vessel_reg=vessel_reg, radio_call_sign=radio_call_sign, hummer_participant_no=hummer_participant_no, case_id=case_id))


@router.post('/api/ocr/extract')
async def api_ocr_extract(request: Request, file: UploadFile = File(...)):
    require_permission(request, 'kv_kontroll', detail='Brukeren har ikke tilgang til Minfiskerikontroll.')
    enforce_csrf(request)
    filename = sanitize_original_filename(file.filename or 'ocr-bilde.jpg')
    content_type = str(file.content_type or '').strip().lower()
    suffix = Path(filename).suffix.lower()
    allowed_suffixes = {'.png', '.jpg', '.jpeg', '.webp', '.heic', '.heif'}
    if content_type and content_type not in {'application/octet-stream', 'binary/octet-stream'} and not content_type.startswith('image/'):
        raise HTTPException(status_code=400, detail='OCR støtter bare bildefiler.')
    if suffix not in allowed_suffixes:
        raise HTTPException(status_code=400, detail='OCR støtter bare bildefiler.')
    content = await file.read()
    size_bytes = len(content or b"")
    validate_saved_file_size(size_bytes)
    ocr_max_bytes = OCR_MAX_UPLOAD_MB * 1024 * 1024
    if size_bytes > ocr_max_bytes:
        return JSONResponse({
            'ok': False,
            'message': f'Bildet er for stort for OCR ({OCR_MAX_UPLOAD_MB} MB maks). Bruk kamerabildet/optimalisert bilde eller velg et mindre utsnitt.',
            'text': '',
        }, status_code=413)
    cache_key = hashlib.sha256(content or b'').hexdigest()
    cached = _get_ocr_cache(cache_key)
    if cached is not None:
        cached.setdefault('ok', True)
        cached.setdefault('elapsed_ms', 0)
        return JSONResponse(cached)
    started = time.monotonic()
    try:
        result = await run_in_threadpool(extract_text_from_image, content or b"", filename=filename, timeout_seconds=16)
    except ValueError as exc:
        return JSONResponse({'ok': False, 'message': str(exc), 'text': ''}, status_code=422)
    except RuntimeError as exc:
        return JSONResponse({'ok': False, 'message': str(exc), 'text': ''}, status_code=503)
    elapsed_ms = int((time.monotonic() - started) * 1000)
    payload = {'ok': True, **result, 'hints': result.get('hints') or registry.extract_tag_hints(result.get('text') or ''), 'elapsed_ms': elapsed_ms, 'cached': False}
    _put_ocr_cache(cache_key, payload)
    return JSONResponse(payload)


@router.post('/api/summary/suggest')
def api_summary_suggest(request: Request, payload: SummarySuggestRequest):
    require_permission(request, 'kv_kontroll', detail='Brukeren har ikke tilgang til Minfiskerikontroll.')
    enforce_csrf(request)
    case_row = {'summary': '', 'case_basis': payload.case_basis or 'patruljeobservasjon', 'control_type': payload.control_type or '', 'species': payload.species or '', 'fishery_type': payload.fishery_type or payload.species or '', 'gear_type': payload.gear_type or '', 'location_name': payload.location_name or '', 'area_name': payload.area_name or '', 'area_status': payload.area_status or '', 'suspect_name': payload.suspect_name or '', 'basis_details': payload.basis_details or '', 'start_time': payload.start_time or '', 'latitude': payload.latitude, 'longitude': payload.longitude}
    drafts = build_text_drafts(case_row, payload.findings)
    return JSONResponse(drafts)
