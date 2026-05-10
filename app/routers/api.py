from __future__ import annotations

from fastapi import APIRouter, File, HTTPException, Query, Request, UploadFile
from pathlib import Path
from collections import OrderedDict
import json
import hashlib
import os
import re
import time
from fastapi.responses import JSONResponse
from starlette.concurrency import run_in_threadpool

from .. import live_sources
from .. import area
from ..dependencies import require_any_permission, require_permission
from ..security import enforce_csrf
from ..pdf_export import build_text_drafts
from ..schemas import SummarySuggestRequest, TextPolishRequest
from ..services.ocr_service import extract_text_from_image
from ..services.openai_vision_service import VisionConfigError, analyze_person_marking_images
OCR_MAX_UPLOAD_MB = max(2, min(20, int(os.getenv('KV_OCR_MAX_IMAGE_MB', '12') or '12')))
VISION_MAX_UPLOAD_MB = max(2, min(30, int(os.getenv('KV_OPENAI_VISION_MAX_IMAGE_MB', '16') or '16')))
VISION_MAX_IMAGES = max(1, min(8, int(os.getenv('KV_OPENAI_VISION_MAX_IMAGES', '4') or '4')))
MAP_BUNDLE_MAX_LAYERS = max(4, min(20, int(os.getenv('KV_MAP_BUNDLE_MAX_LAYERS', '14') or '14')))
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


def _sanitize_polish_location(value: str) -> str:
    text = re.sub(r'\s+', ' ', str(value or '')).strip()
    if not text:
        return ''
    # Older clients sometimes sent "sted - område - DMS/UTM". Standardtekster skal bruke nærmeste sted.
    text = re.split(r'\s+-\s+', text, maxsplit=1)[0].strip()
    if re.search(r'\b(?:utm|\d{1,2}\s*[°]|[NSØE]\s*\d)', text, flags=re.IGNORECASE):
        return ''
    return text


def _normalize_case_basis_for_text(case_basis: str) -> str:
    return 'tips' if str(case_basis or '').strip().lower() == 'tips' else 'patruljeobservasjon'


def _basis_opening_phrase(case_basis: str, source_name: str = '') -> str:
    basis = _normalize_case_basis_for_text(case_basis)
    raw_source = str(source_name or '').strip()
    if basis == 'tips' and raw_source:
        return f'Kontrollen ble gjennomført på bakgrunn av tips/opplysninger fra {raw_source}'
    if basis == 'tips':
        return 'Kontrollen ble gjennomført på bakgrunn av tips/opplysninger'
    return 'Patruljen gjennomførte fiskerioppsyn som ledd i planlagt kontrollvirksomhet'


@router.post('/api/text/polish')
def api_text_polish(request: Request, payload: TextPolishRequest):
    require_permission(request, 'kv_kontroll', detail='Brukeren har ikke tilgang til Minfiskerikontroll.')
    enforce_csrf(request)
    mode = str(payload.mode or 'generic').strip()
    text_in = str(payload.text or '').strip()
    case_basis = _normalize_case_basis_for_text(str(payload.case_basis or '').strip() or 'patruljeobservasjon')
    source_name = str(payload.source_name or '').strip()
    subject = str(payload.subject or '').strip()
    location = _sanitize_polish_location(str(payload.location or '').strip())
    if not text_in:
        return JSONResponse({'text': ''})
    cleaned = ' '.join(text_in.replace('\r', '\n').split())
    if location:
        cleaned = re.sub(r'\bi aktuelt kontrollområde\b', 'ved ' + location, cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r'\bved registrert kontrollposisjon\b', 'ved ' + location, cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r'\bved kontrollposisjonen\b', 'ved ' + location, cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r'\bved kontrollposisjon\b', 'ved ' + location, cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r'\baktuelt kontrollområde\b', location, cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r'\bkontrollposisjonen\b', location, cleaned, flags=re.IGNORECASE)
    else:
        cleaned = re.sub(r'\bi aktuelt kontrollområde\b', 'ved kontrollstedet', cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r'\bved registrert kontrollposisjon\b', 'ved kontrollstedet', cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r'\bved kontrollposisjonen\b', 'ved kontrollstedet', cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r'\bved kontrollposisjon\b', 'ved kontrollstedet', cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r'\baktuelt kontrollområde\b', 'kontrollstedet', cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r'\bkontrollposisjonen\b', 'kontrollstedet', cleaned, flags=re.IGNORECASE)
    cleaned = cleaned.replace(' ,', ',').replace(' .', '.').replace(' :', ':')
    unwanted_phrases = (
        'samt å dokumentere faktiske ' + 'forhold i en ' + 'anmeldelsesegnet form',
        'Kontrollen ble også sett i sammenheng med tidligere registrerte ' + 'opplysninger i saken',
        'Det ble fra ' + 'Kyst' + 'vakten lettbåt gjennomført',
        'Det ble fra ' + 'kyst' + 'vakten lettbåt gjennomført',
        'invol' + 'verte personer/fartøy',
        'invol' + 'verte personer eller fartøy',
    )
    for unwanted in unwanted_phrases:
        cleaned = re.sub(re.escape(unwanted), '', cleaned, flags=re.IGNORECASE).strip()
    cleaned = re.sub(r'\s*,\s*og\s+relevante område-', ', med relevante område-', cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r'\s*,\s*og\s+øvrige kontrollpunkter', ' og øvrige kontrollpunkter', cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r'\bkontrollere\s*,', 'kontrollere', cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r'kontrollere\s+fiskerikontroll\s*', 'føre kontroll med ', cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r'Patruljeformålet var å kontrollere', 'Formålet var å føre kontroll med', cleaned, flags=re.IGNORECASE)
    cleaned = cleaned.replace('aktuelt fiskeri / redskap', 'aktuelt fiskeri og redskap')
    cleaned = re.sub(r'\s{2,}', ' ', cleaned).strip(' ,;')
    if cleaned and cleaned[0].islower():
        cleaned = cleaned[0].upper() + cleaned[1:]
    if mode == 'basis':
        opening = _basis_opening_phrase(case_basis, source_name)
        sentence_starters = (
            opening.lower(),
            'det ble gjennomført stedlig fiskerikontroll',
            'på bakgrunn av tips',
            'på bakgrunn av opplysninger',
            'den ',
            'kontrollen ',
            'patrulje ',
            'bakgrunnen ',
            'formålet ',
        )
        if not cleaned.lower().startswith(sentence_starters):
            cleaned = f"{opening}. {cleaned.rstrip('.')}".strip()
        cleaned = re.sub(r'Formålet var å føre kontroll med føre kontroll med', 'Formålet var å føre kontroll med', cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r'avklare om redskap, merking, fangst/oppbevaring og relevante områdebestemmelser', 'avklare om redskap, merking, fangst/oppbevaring, posisjon og relevante områdebestemmelser', cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r'kontrollere\s+fiskerikontroll\s*', 'føre kontroll med ', cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r'Patruljeformålet var å kontrollere', 'Formålet var å føre kontroll med', cleaned, flags=re.IGNORECASE)
        if location and location.lower() not in cleaned.lower():
            cleaned = cleaned.rstrip('.') + f' ved {location}.'
        else:
            cleaned = cleaned.rstrip('.') + '.'
    elif mode == 'interview_summary':
        subject_text = subject or 'Avhørte'
        cleaned = f"{subject_text} forklarte i hovedsak at {cleaned.rstrip('.')} .".replace(' .', '.')
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
    return JSONResponse(check_zone_status(lat, lng, species=species, gear_type=gear_type, control_type=control_type), headers={'Cache-Control': 'no-store, max-age=0'})




@router.get('/api/geo/reverse')
def api_geo_reverse(request: Request, lat: float = Query(..., ge=-90, le=90), lng: float = Query(..., ge=-180, le=180)):
    require_any_permission(request, ['kart', 'kv_kontroll'], detail='Brukeren har ikke tilgang til stedsoppslag.')
    local_place = area.nearest_place(lat, lng) or {}
    payload: dict = {
        'found': False,
        'nearest_place': str(local_place.get('name') or '').strip(),
        'distance_to_place_km': local_place.get('distance_km'),
        'location_name': str(local_place.get('name') or '').strip(),
        'source': 'Lokal reserve'
    }
    try:
        reverse = live_sources.reverse_geocode_live(lat, lng)
        municipality = str(reverse.get('municipality') or '').strip()
        locality = str(reverse.get('locality') or reverse.get('name') or payload.get('nearest_place') or '').strip()
        parts = []
        for value in [locality, municipality]:
            value = str(value or '').strip()
            if value and value not in parts:
                parts.append(value)
        label = ', '.join(parts) or str(reverse.get('location_label') or '').strip() or payload.get('location_name') or ''
        payload.update({
            'found': bool(reverse.get('found') or label),
            'nearest_place': locality or payload.get('nearest_place') or '',
            'locality': locality,
            'municipality': municipality,
            'county': reverse.get('county') or '',
            'road': reverse.get('road') or '',
            'postcode': reverse.get('postcode') or '',
            'location_name': label,
            'location_label': label,
            'reverse_geocode': reverse,
            'source': reverse.get('source') or 'OpenStreetMap Nominatim'
        })
    except Exception as exc:
        payload['reverse_geocode'] = {'found': False, 'error': str(exc)}
    return JSONResponse(payload, headers={'Cache-Control': 'no-store, max-age=0'})

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
def api_registry_lookup(request: Request, phone: str = '', vessel_reg: str = '', radio_call_sign: str = '', name: str = '', address: str = '', post_place: str = '', tag_text: str = '', hummer_participant_no: str = '', lookup_mode: str = ''):
    require_permission(request, 'kv_kontroll', detail='Brukeren har ikke tilgang til Minfiskerikontroll.')
    return JSONResponse(lookup_registry(phone=phone, vessel_reg=vessel_reg, radio_call_sign=radio_call_sign, name=name, address=address, post_place=post_place, tag_text=tag_text, hummer_participant_no=hummer_participant_no, lookup_mode=lookup_mode))


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
        result = await run_in_threadpool(extract_text_from_image, content or b"", filename=filename, timeout_seconds=50)
    except ValueError as exc:
        return JSONResponse({'ok': False, 'message': str(exc), 'text': ''}, status_code=422)
    except RuntimeError as exc:
        return JSONResponse({'ok': False, 'message': str(exc), 'text': ''}, status_code=503)
    elapsed_ms = int((time.monotonic() - started) * 1000)
    payload = {'ok': True, **result, 'hints': result.get('hints') or registry.extract_tag_hints(result.get('text') or ''), 'elapsed_ms': elapsed_ms, 'cached': False}
    _put_ocr_cache(cache_key, payload)
    return JSONResponse(payload)


@router.get('/api/person-fartoy/analyzer-status')
def api_person_fartoy_analyzer_status(request: Request):
    """Diagnose hvilken bildeanalyse-pipeline som vil brukes.

    Returnerer hvilken kilde (OpenAI Vision eller lokal Tesseract) som er
    aktiv, slik at felt-bruker ser status før analysen starter."""
    require_permission(request, 'kv_kontroll', detail='Brukeren har ikke tilgang til Minfiskerikontroll.')
    import os as _os
    from ..services.openai_vision_service import _first_configured_api_key, VISION_MODEL_DEFAULT

    api_key, key_source = _first_configured_api_key()
    raw_flag = str(_os.getenv('KV_PERSON_FARTOY_USE_OPENAI') or '').strip().lower()
    explicitly_disabled = raw_flag in {'0', 'false', 'no', 'off'}
    openai_active = bool(api_key) and not explicitly_disabled

    if openai_active:
        primary = 'openai'
        primary_label = 'OpenAI Vision'
        primary_detail = f'Avansert AI-analyse (modell: {_os.getenv("KV_OPENAI_VISION_MODEL") or _os.getenv("OPENAI_VISION_MODEL") or VISION_MODEL_DEFAULT})'
    else:
        primary = 'local'
        primary_label = 'Lokal Tesseract OCR'
        if api_key and explicitly_disabled:
            primary_detail = 'OpenAI-nøkkel er konfigurert, men er deaktivert via KV_PERSON_FARTOY_USE_OPENAI=0.'
        elif not api_key:
            primary_detail = 'Sett miljøvariabel KV_OPENAI_API_KEY for å aktivere OpenAI Vision.'
        else:
            primary_detail = 'Lokal OCR-pipeline.'

    return JSONResponse({
        'primary': primary,
        'primary_label': primary_label,
        'primary_detail': primary_detail,
        'openai_active': openai_active,
        'openai_key_source': key_source if openai_active else '',
        'fallback': 'local' if openai_active else None,
        'registry_lookup_active': True,
        'registry_source': 'Fiskeridirektoratet — registrerte hummerfiskere',
    })


@router.post('/api/person-fartoy/analyze-image')
async def api_person_fartoy_analyze_image(request: Request, files: list[UploadFile] = File(...)):
    require_permission(request, 'kv_kontroll', detail='Brukeren har ikke tilgang til Minfiskerikontroll.')
    enforce_csrf(request)
    if not files:
        raise HTTPException(status_code=400, detail='Legg ved minst ett bilde.')
    if len(files) > VISION_MAX_IMAGES:
        raise HTTPException(status_code=400, detail=f'Maks {VISION_MAX_IMAGES} bilder kan analyseres samtidig.')
    allowed_suffixes = {'.png', '.jpg', '.jpeg', '.webp', '.heic', '.heif'}
    image_payloads: list[dict] = []
    total_size = 0
    for upload in files:
        filename = sanitize_original_filename(upload.filename or 'merking.jpg')
        content_type = str(upload.content_type or '').strip().lower()
        suffix = Path(filename).suffix.lower()
        if content_type and content_type not in {'application/octet-stream', 'binary/octet-stream'} and not content_type.startswith('image/'):
            raise HTTPException(status_code=400, detail='Bildeanalyse støtter bare bildefiler.')
        if suffix not in allowed_suffixes:
            raise HTTPException(status_code=400, detail='Bildeanalyse støtter JPG, PNG, WEBP, HEIC og HEIF.')
        content = await upload.read()
        size_bytes = len(content or b'')
        validate_saved_file_size(size_bytes)
        total_size += size_bytes
        max_bytes = VISION_MAX_UPLOAD_MB * 1024 * 1024
        if size_bytes > max_bytes:
            return JSONResponse({'detail': f'Bildet {filename} er for stort for bildeanalyse ({VISION_MAX_UPLOAD_MB} MB maks).'}, status_code=413)
        image_payloads.append({'filename': filename, 'content': content or b''})
    if total_size > VISION_MAX_UPLOAD_MB * 1024 * 1024 * max(1, VISION_MAX_IMAGES):
        return JSONResponse({'detail': 'Samlet bildestørrelse er for stor for bildeanalyse. Prøv færre bilder.'}, status_code=413)
    try:
        result = await run_in_threadpool(analyze_person_marking_images, image_payloads)
    except VisionConfigError as exc:
        return JSONResponse({'detail': str(exc)}, status_code=503)
    except ValueError as exc:
        return JSONResponse({'detail': str(exc)}, status_code=422)
    except RuntimeError as exc:
        return JSONResponse({'detail': str(exc)}, status_code=502)
    return JSONResponse(result, headers={'Cache-Control': 'no-store, max-age=0'})


@router.get('/api/person-fartoy/lookup-deltakernummer')
def api_person_fartoy_lookup_deltakernummer(request: Request, deltakernummer: str = '', navn: str = ''):
    """Manuelt oppslag av deltakernummer mot Fiskeridirektoratets register
    over hummerfiskere (live fra tableau.fiskeridir.no, med lokal cache).

    Returnerer alle felt (navn, deltakernummer, eventuelt adresse fra
    katalogoppslag) slik at klienten kan auto-fylle Person/Fartøy-skjemaet.
    """
    require_permission(request, 'kv_kontroll', detail='Brukeren har ikke tilgang til Minfiskerikontroll.')
    deltaker = str(deltakernummer or '').strip()
    name = str(navn or '').strip()
    if not deltaker and not name:
        raise HTTPException(status_code=400, detail='Oppgi deltakernummer eller navn.')

    from .. import live_sources, registry as registry_mod

    # Live lookup against the Tableau register (with local cache fallback)
    try:
        result = live_sources.lookup_hummer_participant_live(participant_no=deltaker, name=name)
    except Exception as exc:
        return JSONResponse({
            'found': False,
            'detail': f'Kunne ikke nå Fiskeridir-registeret akkurat nå ({exc}). Lokal cache er sjekket uten treff.',
            'candidates': [],
        })

    if not result.get('found'):
        return JSONResponse({
            'found': False,
            'detail': result.get('message') or 'Fant ingen registrert hummerfisker med dette deltakernummeret.',
            'candidates': [
                {
                    'name': c.get('name', ''),
                    'deltakernummer': registry_mod._normalize_hummer_no(c.get('participant_no') or c.get('hummer_participant_no') or ''),
                    'fisher_type': c.get('fisher_type', ''),
                    'last_registered': c.get('last_registered_display') or c.get('last_registered_year') or '',
                }
                for c in (result.get('candidates') or [])[:10]
            ],
        })

    person = dict(result.get('person') or {})
    payload = {
        'found': True,
        'navn': registry_mod.normalize_person_name(person.get('name') or ''),
        'deltakernummer': registry_mod._normalize_hummer_no(
            person.get('participant_no') or person.get('hummer_participant_no') or deltaker
        ),
        'fisher_type': str(person.get('fisher_type') or '').strip(),
        'last_registered': str(person.get('last_registered_display') or person.get('last_registered_year') or '').strip(),
        'source': str(person.get('source') or 'Fiskeridirektoratet — registrerte hummerfiskere'),
        'source_url': str(person.get('source_url') or 'https://tableau.fiskeridir.no/t/Internet/views/Pmeldehummarfiskarargjeldander/Pmeldehummarfiskarar'),
    }

    # If person also has address from cache, include it
    if person.get('address'):
        payload['adresse'] = str(person.get('address'))
    if person.get('post_place'):
        payload['post_place'] = str(person.get('post_place'))
    if person.get('phone'):
        payload['mobil'] = str(person.get('phone'))

    return JSONResponse(payload, headers={'Cache-Control': 'no-store, max-age=0'})


@router.post('/api/summary/suggest')
def api_summary_suggest(request: Request, payload: SummarySuggestRequest):
    require_permission(request, 'kv_kontroll', detail='Brukeren har ikke tilgang til Minfiskerikontroll.')
    enforce_csrf(request)
    case_row = {'summary': '', 'case_basis': payload.case_basis or 'patruljeobservasjon', 'control_type': payload.control_type or '', 'species': payload.species or '', 'fishery_type': payload.fishery_type or payload.species or '', 'gear_type': payload.gear_type or '', 'location_name': payload.location_name or '', 'area_name': payload.area_name or '', 'area_status': payload.area_status or '', 'suspect_name': payload.suspect_name or '', 'vessel_name': payload.vessel_name or '', 'investigator_name': payload.investigator_name or '', 'basis_source_name': payload.basis_source_name or '', 'basis_details': payload.basis_details or '', 'start_time': payload.start_time or '', 'latitude': payload.latitude, 'longitude': payload.longitude, 'persons_json': json.dumps(payload.persons or [], ensure_ascii=False), 'seizure_reports_json': json.dumps(payload.seizure_reports or [], ensure_ascii=False)}
    drafts = build_text_drafts(case_row, payload.findings)
    return JSONResponse(drafts)


@router.post('/api/cases/{case_id}/interview-report-draft')
async def api_interview_report_draft(case_id: int, request: Request):
    """Generer en avhørsrapport-utkast lokalt fra diktering + saksinformasjon.

    Bruker ikke betalt AI — kun smart sammenstilling av diktering, avvik fra
    kontrollpunkter og standardformuleringer. Klienten har et lokalt utkast
    fra start; dette endepunktet kan polere/tilrettelegge teksten.
    """
    require_permission(request, 'kv_kontroll', detail='Brukeren har ikke tilgang til Minfiskerikontroll.')
    enforce_csrf(request)
    form = await request.form()
    dictation = str(form.get('dictation') or '').strip()
    case_summary_raw = str(form.get('case_summary') or '').strip()
    try:
        sum_payload = json.loads(case_summary_raw) if case_summary_raw else {}
    except Exception:
        sum_payload = {}

    findings = sum_payload.get('findings') or []
    avvik_items = [f for f in findings if isinstance(f, dict) and str(f.get('status') or '').lower() == 'avvik']

    lines = []
    lines.append('AVHØRSRAPPORT')
    lines.append('')
    suspect_name = str(sum_payload.get('suspect_name') or '').strip()
    if suspect_name:
        lines.append(f'Avhørt person: {suspect_name}')
        lines.append('')
    location_name = str(sum_payload.get('location_name') or '').strip()
    if location_name:
        lines.append(f'Avhør sted: {location_name}')
    start_time = str(sum_payload.get('start_time') or '').strip()
    if start_time:
        lines.append(f'Tidspunkt: {start_time}')
    lines.append('')

    if avvik_items:
        lines.append('Forelagte avvik:')
        for i, a in enumerate(avvik_items, 1):
            label = str(a.get('label') or a.get('key') or 'Punkt').strip()
            notes = str(a.get('notes') or '').strip()
            if notes:
                lines.append(f'{i}. {label} — {notes}')
            else:
                lines.append(f'{i}. {label}')
        lines.append('')

    if dictation:
        # Light polish: capitalize sentence starts, fix double spaces
        polished = re.sub(r'\s+', ' ', dictation).strip()
        polished = re.sub(r'(?<=[.!?])\s+([a-zæøå])',
                          lambda m: ' ' + m.group(1).upper(), polished)
        if polished and polished[0].islower():
            polished = polished[0].upper() + polished[1:]
        lines.append('Forklaring fra avhørt:')
        lines.append(polished)
        lines.append('')
    else:
        lines.append('Forklaring: Avhørte ble forelagt funnene og fikk anledning til å uttale seg.')
        lines.append('(Ingen diktering registrert — fyll inn manuelt.)')
        lines.append('')

    # Short summary for anmeldelse
    lines.append('Kort oppsummering for anmeldelse:')
    if avvik_items:
        avvik_count = len(avvik_items)
        avvik_text = 'avvik' if avvik_count == 1 else 'avvik'
        first_avvik = str(avvik_items[0].get('label') or '').strip()
        if avvik_count == 1:
            summary_line = f'Det ble registrert ett {avvik_text} ved kontrollen: {first_avvik}.'
        else:
            summary_line = f'Det ble registrert {avvik_count} {avvik_text} ved kontrollen, herunder {first_avvik}.'
        lines.append(summary_line + ' Avhørte ble forelagt funnene og fikk anledning til å uttale seg.')
    else:
        lines.append('Det ble ikke registrert avvik ved kontrollen som danner grunnlag for anmeldelse.')

    return JSONResponse({'report': '\n'.join(lines)}, headers={'Cache-Control': 'no-store, max-age=0'})
