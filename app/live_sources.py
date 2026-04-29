from __future__ import annotations

import csv
from concurrent.futures import ThreadPoolExecutor, as_completed, TimeoutError as FuturesTimeoutError
from datetime import datetime
import io
import json
import os
import re
import tarfile
import time
import unicodedata
import threading
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional
from urllib.parse import urljoin, quote_plus, quote

import certifi
import requests
from requests.adapters import HTTPAdapter
from bs4 import BeautifulSoup
try:
    from urllib3.util.retry import Retry
except Exception:  # pragma: no cover
    Retry = None

from . import area, map_relevance, registry

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / 'data'
CACHE_DIR = DATA_DIR / 'cache'
CACHE_DIR.mkdir(parents=True, exist_ok=True)

LIVE_ENABLED = os.getenv('KV_LIVE_SOURCES', '1') not in {'0', 'false', 'False'}
REQUEST_TIMEOUT = float(os.getenv('KV_HTTP_TIMEOUT', '20'))
PORTAL_REQUEST_TIMEOUT = float(os.getenv('KV_PORTAL_HTTP_TIMEOUT', '5'))
FDIR_TAR_URL = os.getenv('KV_FDIR_TAR_URL', 'https://register.fiskeridir.no/fartoyreg/last/frtyweb.tar')
JM_URL = os.getenv('KV_JM_URL', 'https://www.fiskeridir.no/yrkesfiske/j-meldinger')
YGG_BASE = os.getenv('KV_YGG_BASE', os.getenv('KV_PORTAL_MAPSERVER', 'https://gis.fiskeridir.no/server/rest/services/Fiskeridir_vern/MapServer'))
LOVDATA_TOPICS_PATH = DATA_DIR / 'lovdata_topics.json'
FDIR_CACHE_JSON = CACHE_DIR / 'fdir_registry_cache.json'
FDIR_CACHE_META = CACHE_DIR / 'fdir_registry_meta.json'
UA = 'Minfiskerikontroll-1.8.0/1.8.0 (+field trial app)'
HUMMER_REGISTER_URL = 'https://tableau.fiskeridir.no/t/Internet/views/Pmeldehummarfiskarargjeldander/Pmeldehummarfiskarar?:showVizHome=no'
HUMMER_REGISTER_FALLBACK_URL = 'https://www.fiskeridir.no/statistikk-tall-og-analyse/data-og-statistikk-om-turist--og-fritidsfiske/registrerte-hummarfiskarar'
HUMMER_CACHE_JSON = CACHE_DIR / 'hummer_registry_cache.json'
HUMMER_CACHE_META = CACHE_DIR / 'hummer_registry_meta.json'
FISHER_REGISTER_URL = 'https://tableau.fiskeridir.no/t/Internet/views/Fiskerregister/Fiskerregisteret?:showVizHome=no'

PHONE_RE = re.compile(r'(?<!\d)(?:47)?(\d{8})(?!\d)')
VESSEL_RE = re.compile(r'\b([A-Z]{1,3}[\- ]?\d{1,4}[\- ]?[A-Z]?)\b')
RADIOSIGNAL_RE = re.compile(r'\b([A-Z]{2,5}\d{0,3})\b')

LAYER_STENGT = 0
LAYER_HUMMER_FREDNING = 9
LAYER_HUMMER_MAX = 10

HTTP_POOL_CONNECTIONS = max(16, int(os.getenv('KV_HTTP_POOL_CONNECTIONS', '32') or '32'))
HTTP_POOL_MAXSIZE = max(16, int(os.getenv('KV_HTTP_POOL_MAXSIZE', str(max(16, HTTP_POOL_CONNECTIONS))) or str(max(16, HTTP_POOL_CONNECTIONS))))
PORTAL_BBOX_CACHE_TTL = max(60.0, float(os.getenv('KV_PORTAL_BBOX_CACHE_TTL', '600') or '600'))

_SESSION = requests.Session()
_SESSION.headers.update({'User-Agent': UA, 'Accept-Language': 'nb-NO,nb;q=0.9,no;q=0.8,en;q=0.4'})
_SESSION.verify = os.getenv('REQUESTS_CA_BUNDLE') or os.getenv('SSL_CERT_FILE') or certifi.where()
if Retry is not None:
    try:
        _retry = Retry(total=2, connect=2, read=1, status=2, backoff_factor=0.2, status_forcelist=[429, 500, 502, 503, 504], allowed_methods=frozenset({'GET', 'HEAD', 'OPTIONS'}), raise_on_status=False)
    except TypeError:  # pragma: no cover
        _retry = Retry(total=2, connect=2, read=1, backoff_factor=0.2, status_forcelist=[429, 500, 502, 503, 504], method_whitelist=frozenset({'GET', 'HEAD', 'OPTIONS'}), raise_on_status=False)
else:
    _retry = None
_adapter = HTTPAdapter(pool_connections=HTTP_POOL_CONNECTIONS, pool_maxsize=HTTP_POOL_MAXSIZE, max_retries=_retry, pool_block=True)
_SESSION.mount('https://', _adapter)
_SESSION.mount('http://', _adapter)
_BBOX_CACHE: dict[str, tuple[float, dict[str, Any]]] = {}
_BBOX_CACHE_LOCK = threading.Lock()
_PORTAL_POINT_CACHE: dict[str, tuple[float, list[dict[str, Any]]]] = {}
_PORTAL_POINT_CACHE_LOCK = threading.Lock()
PORTAL_POINT_CACHE_TTL = max(20.0, float(os.getenv('KV_PORTAL_POINT_CACHE_TTL', '180') or '180'))
PORTAL_BUNDLE_CACHE_TTL = max(120.0, float(os.getenv('KV_PORTAL_BUNDLE_CACHE_TTL', '900') or '900'))
_PORTAL_BUNDLE_CACHE: dict[str, tuple[float, dict[str, Any]]] = {}
_PORTAL_BUNDLE_CACHE_LOCK = threading.Lock()
ZONE_CHECK_MAX_LIVE_LAYERS = max(3, min(18, int(os.getenv('KV_ZONE_CHECK_MAX_LIVE_LAYERS', '6') or '6')))
ZONE_POINT_QUERY_TIMEOUT = max(0.8, min(3.5, float(os.getenv('KV_ZONE_POINT_QUERY_TIMEOUT', '1.8') or '1.8')))
ZONE_CHECK_WORKERS = max(2, min(8, int(os.getenv('KV_ZONE_CHECK_WORKERS', '6') or '6')))
ZONE_CHECK_TOTAL_TIMEOUT = max(1.5, min(8.0, float(os.getenv('KV_ZONE_CHECK_TOTAL_TIMEOUT', '3.0') or '3.0')))
REVERSE_GEOCODE_CACHE_TTL = max(60.0, float(os.getenv('KV_REVERSE_GEOCODE_CACHE_TTL', '900') or '900'))
_REVERSE_GEOCODE_CACHE: dict[str, tuple[float, dict[str, Any]]] = {}
_REVERSE_GEOCODE_CACHE_LOCK = threading.Lock()


class LiveSourceError(RuntimeError):
    pass


def _norm(text: str | None) -> str:
    return ' '.join(str(text or '').strip().lower().replace('_', ' ').split())


def _norm_compact(text: str | None) -> str:
    return re.sub(r'\s+', '', str(text or '').upper())


def _safe_get(url: str, *, params: dict[str, Any] | None = None, stream: bool = False, timeout: float | tuple[float, float] | None = None) -> requests.Response:
    if not LIVE_ENABLED:
        raise LiveSourceError('Live kilder er deaktivert i miljøvariabel KV_LIVE_SOURCES.')
    try:
        resp = _SESSION.get(url, params=params, timeout=timeout or REQUEST_TIMEOUT, stream=stream)
        resp.raise_for_status()
        return resp
    except Exception as exc:  # pragma: no cover - network dependent
        raise LiveSourceError(str(exc)) from exc


def _load_lovdata_topics() -> dict[str, list[dict[str, str]]]:
    try:
        raw = json.loads(LOVDATA_TOPICS_PATH.read_text(encoding='utf-8'))
    except Exception:
        raw = {}
    return raw if isinstance(raw, dict) else {}


def _extract_lookup_tokens(phone: str = '', vessel_reg: str = '', name: str = '', tag_text: str = '') -> dict[str, str]:
    merged_text = ' '.join([phone, vessel_reg, name, tag_text]).strip()
    vessel_match = VESSEL_RE.search(merged_text.upper())
    phone_match = PHONE_RE.search(merged_text.replace(' ', ''))
    radio_match = RADIOSIGNAL_RE.search(merged_text.upper())
    return {
        'phone': (phone or (phone_match.group(1) if phone_match else '')).strip(),
        'vessel_reg': _norm_compact(vessel_reg or (vessel_match.group(1) if vessel_match else '')),
        'radio_call_sign': _norm_compact(radio_match.group(1) if radio_match else ''),
        'name': _norm(name),
        'tag_text': str(tag_text or '').strip(),
    }


# -------------------------
# FDIR registry live cache
# -------------------------


def _cache_is_fresh(meta_path: Path, max_age_seconds: int) -> bool:
    if not meta_path.exists():
        return False
    try:
        meta = json.loads(meta_path.read_text(encoding='utf-8'))
        ts = float(meta.get('refreshed_at_unix') or 0)
    except Exception:
        return False
    return (time.time() - ts) < max_age_seconds


def _parse_semicolon_csv(fileobj: io.TextIOBase) -> Iterable[dict[str, str]]:
    reader = csv.DictReader(fileobj, delimiter=';')
    for row in reader:
        yield {str(k or '').strip(): str(v or '').strip() for k, v in row.items()}


def refresh_fdir_cache(force: bool = False, max_age_seconds: int = 24 * 3600) -> dict[str, Any]:
    if not force and FDIR_CACHE_JSON.exists() and _cache_is_fresh(FDIR_CACHE_META, max_age_seconds):
        return json.loads(FDIR_CACHE_JSON.read_text(encoding='utf-8'))

    resp = _safe_get(FDIR_TAR_URL)
    buf = io.BytesIO(resp.content)
    vessels: dict[str, dict[str, str]] = {}
    entities: dict[str, dict[str, str]] = {}
    owners_by_vessel: dict[str, list[dict[str, str]]] = {}

    with tarfile.open(fileobj=buf, mode='r:*') as tar:
        names = {m.name.split('/')[-1]: m for m in tar.getmembers() if m.isfile()}
        required = ['fartoy.csv', 'juridisk_enhet.csv', 'fartoy_eier.csv']
        missing = [n for n in required if n not in names]
        if missing:
            raise LiveSourceError(f'Mangler filer i Fartøyregister-uttrekket: {", ".join(missing)}')

        with tar.extractfile(names['fartoy.csv']) as fh:
            assert fh is not None
            text = io.TextIOWrapper(fh, encoding='utf-8-sig', newline='')
            for row in _parse_semicolon_csv(text):
                vessels[row.get('FARTØY_ID') or ''] = row

        with tar.extractfile(names['juridisk_enhet.csv']) as fh:
            assert fh is not None
            text = io.TextIOWrapper(fh, encoding='utf-8-sig', newline='')
            for row in _parse_semicolon_csv(text):
                entities[row.get('IDNR') or ''] = row

        with tar.extractfile(names['fartoy_eier.csv']) as fh:
            assert fh is not None
            text = io.TextIOWrapper(fh, encoding='utf-8-sig', newline='')
            for row in _parse_semicolon_csv(text):
                if row.get('EIET_ENTITET') != 'FARTØY':
                    continue
                vessel_id = row.get('EIET_IDNR') or ''
                owner_id = row.get('EIER_IDNR') or ''
                entity = entities.get(owner_id)
                if not vessel_id or not entity:
                    continue
                owners_by_vessel.setdefault(vessel_id, []).append(entity)

    records: list[dict[str, Any]] = []
    for vessel_id, vessel in vessels.items():
        owner_entities = owners_by_vessel.get(vessel_id, [])
        owner_names = [e.get('NAVN', '') for e in owner_entities if e.get('NAVN')]
        owner_places = [
            ' '.join([e.get('POSTSNUMMER', '').strip(), e.get('POSTSTED', '').strip()]).strip()
            for e in owner_entities
            if e.get('POSTSNUMMER') or e.get('POSTSTED')
        ]
        row = {
            'source': 'Fiskeridirektoratet Fartøyregisteret',
            'vessel_id': vessel_id,
            'vessel_name': vessel.get('NAVN', ''),
            'vessel_reg': vessel.get('REGISTRERINGSMERKE', ''),
            'radio_call_sign': vessel.get('RADIOKALLESIGNAL', ''),
            'owner_name': ', '.join(owner_names[:3]),
            'owner_names': owner_names[:6],
            'owner_places': owner_places[:6],
            'municipality_number': vessel.get('KOMMUNENUMMER', ''),
            'length': vessel.get('STØRSTE_LENGDE', ''),
            'built_year': vessel.get('BYGGET_ÅR', ''),
            'engine_power': vessel.get('MOTORKRAFT', ''),
            'post_place': owner_places[0] if owner_places else '',
        }
        searchable = ' | '.join(
            [
                row['vessel_name'],
                row['vessel_reg'],
                row['radio_call_sign'],
                row['owner_name'],
                ' '.join(owner_names),
                ' '.join(owner_places),
            ]
        )
        row['search_text'] = _norm(searchable)
        records.append(row)

    payload = {
        'source': 'Fiskeridirektoratet Fartøyregisteret',
        'source_url': FDIR_TAR_URL,
        'refreshed_at_unix': time.time(),
        'records': records,
    }
    FDIR_CACHE_JSON.write_text(json.dumps(payload, ensure_ascii=False), encoding='utf-8')
    FDIR_CACHE_META.write_text(json.dumps({'refreshed_at_unix': payload['refreshed_at_unix']}, ensure_ascii=False), encoding='utf-8')
    return payload


def _score_registry_record(row: dict[str, Any], tokens: dict[str, str]) -> int:
    score = 0
    vessel_reg = _norm_compact(row.get('vessel_reg'))
    radio = _norm_compact(row.get('radio_call_sign'))
    vessel_name = _norm(row.get('vessel_name'))
    owner_names = [_norm(x) for x in row.get('owner_names') or []]
    search_text = row.get('search_text', '')

    if tokens['vessel_reg'] and vessel_reg == tokens['vessel_reg']:
        score += 100
    if tokens['radio_call_sign'] and radio == tokens['radio_call_sign']:
        score += 60
    if tokens['name']:
        if tokens['name'] == vessel_name:
            score += 55
        if any(tokens['name'] == owner for owner in owner_names):
            score += 50
        if tokens['name'] in vessel_name:
            score += 25
        if any(tokens['name'] in owner for owner in owner_names):
            score += 20
    tag = _norm(tokens['tag_text'])
    if tag and tag in search_text:
        score += 10
    return score


def lookup_registry_live(phone: str = '', vessel_reg: str = '', name: str = '', tag_text: str = '') -> dict[str, Any]:
    tokens = _extract_lookup_tokens(phone=phone, vessel_reg=vessel_reg, name=name, tag_text=tag_text)
    if not any(tokens.values()):
        return {'found': False, 'message': 'Ingen søkeverdier oppgitt.'}

    cache = refresh_fdir_cache(force=False)
    records = cache.get('records') or []
    scored: list[tuple[int, dict[str, Any]]] = []
    for row in records:
        score = _score_registry_record(row, tokens)
        if score > 0:
            scored.append((score, row))
    scored.sort(key=lambda item: (-item[0], item[1].get('vessel_name') or ''))
    if not scored:
        return {'found': False, 'message': 'Ingen treff i live Fartøyregisteret.'}

    best = dict(scored[0][1])
    match_reason = []
    if tokens['vessel_reg'] and _norm_compact(best.get('vessel_reg')) == tokens['vessel_reg']:
        match_reason.append('registreringsmerke')
    if tokens['radio_call_sign'] and _norm_compact(best.get('radio_call_sign')) == tokens['radio_call_sign']:
        match_reason.append('radiokallesignal')
    if tokens['name'] and tokens['name'] in _norm(' '.join(best.get('owner_names') or [best.get('vessel_name') or ''])):
        match_reason.append('navn')

    person = {
        'name': best.get('owner_name') or best.get('vessel_name') or '',
        'birthdate': '',
        'address': best.get('post_place') or '',
        'phone': '',
        'vessel_name': best.get('vessel_name') or '',
        'vessel_reg': best.get('vessel_reg') or '',
        'radio_call_sign': best.get('radio_call_sign') or '',
        'owner_names': best.get('owner_names') or [],
        'match_reason': ', '.join(match_reason) or 'live oppslag',
        'source': 'Fiskeridirektoratet Fartøyregisteret',
        'source_url': FDIR_TAR_URL,
    }
    candidates = [
        {
            'name': row.get('owner_name') or row.get('vessel_name') or '',
            'address': row.get('post_place') or '',
            'vessel_name': row.get('vessel_name') or '',
            'vessel_reg': row.get('vessel_reg') or '',
            'radio_call_sign': row.get('radio_call_sign') or '',
        }
        for _, row in scored[:5]
    ]
    return {
        'found': True,
        'person': person,
        'candidates': candidates,
        'refreshed_at_unix': cache.get('refreshed_at_unix'),
        'source': 'Fiskeridirektoratet Fartøyregisteret',
    }


# -------------------------
# J-meldinger live search
# -------------------------


def search_jmeldinger(species: str = '', gear_type: str = '', area_status: str = '', limit: int = 8) -> list[dict[str, str]]:
    resp = _safe_get(JM_URL)
    soup = BeautifulSoup(resp.text, 'html.parser')
    keywords = [kw for kw in {_norm(species), _norm(gear_type), _norm(area_status)} if kw and kw not in {'normalt område', 'annet'}]
    rows: list[dict[str, str]] = []
    seen: set[str] = set()
    pattern = re.compile(r'\bJ-\d+-\d{4}\b')

    for anchor in soup.find_all('a', href=True):
        text = ' '.join(anchor.stripped_strings)
        if not pattern.search(text):
            continue
        jm_id_match = pattern.search(text)
        if not jm_id_match:
            continue
        jm_id = jm_id_match.group(0)
        if jm_id in seen:
            continue
        seen.add(jm_id)
        status = 'Gjeldende' if 'Gjeldende' in text else ('Kommende' if 'Kommende' in text else ('Utgått' if 'Utgått' in text else ''))
        title = text
        title = title.replace(jm_id, '', 1).strip()
        for marker in ['Gyldig fra', 'Kommende', 'Gjeldende', 'Utgått']:
            pos = title.find(marker)
            if pos > 0:
                title = title[:pos].strip()
                break
        href = urljoin(JM_URL, anchor.get('href'))
        blob = _norm(' '.join([jm_id, title, status]))
        score = 0
        if status == 'Gjeldende':
            score += 40
        for kw in keywords:
            if kw in blob:
                score += 10
        rows.append({'id': jm_id, 'title': title or jm_id, 'status': status or '', 'url': href, 'score': str(score)})

    rows.sort(key=lambda item: (-int(item.get('score') or '0'), item.get('id') or ''))
    return rows[:limit]


# -------------------------
# Yggdrasil live geometry queries
# -------------------------


def _ygg_query_point(layer_id: int, lat: float, lng: float) -> list[dict[str, Any]]:
    url = f'{YGG_BASE}/{layer_id}/query'
    params = {
        'f': 'geojson',
        'geometry': f'{lng},{lat}',
        'geometryType': 'esriGeometryPoint',
        'inSR': '4326',
        'spatialRel': 'esriSpatialRelIntersects',
        'returnGeometry': 'true',
        'outFields': '*',
    }
    data = _safe_get(url, params=params).json()
    return list(data.get('features') or [])


def classify_position_live(lat: float, lng: float, species: str = '', gear_type: str = '', control_type: str = '') -> dict[str, Any]:
    hits: list[dict[str, Any]] = []
    status = 'normalt område'
    name = 'Ingen live-treff i Yggdrasil'
    notes = 'Fant ingen treff i de live kartlagene som er koblet til løsningen.'

    stengt = _ygg_query_point(LAYER_STENGT, lat, lng)
    if stengt:
        attrs = stengt[0].get('attributes') or {}
        status = 'stengt område'
        name = attrs.get('navn') or attrs.get('kat_ordning_text') or 'J-melding stengt fiskefelt'
        notes = attrs.get('beskrivelse') or attrs.get('stengt_text') or 'Treff i Yggdrasil-laget for J-melding stengte fiskefelt.'
        hits.append({
            'layer': 'J-melding stengte fiskefelt',
            'status': 'stengt område',
            'name': name,
            'notes': notes,
            'url': attrs.get('url') or '',
            'source': 'Fiskeridirektoratet Yggdrasil',
        })

    if 'hummer' in _norm(species):
        fredning = _ygg_query_point(LAYER_HUMMER_FREDNING, lat, lng)
        if fredning:
            attrs = fredning[0].get('attributes') or {}
            if status != 'stengt område':
                status = 'fredningsområde'
                name = attrs.get('navn') or 'Hummer - fredningsområder'
                notes = attrs.get('beskrivelse') or 'Treff i Yggdrasil-laget for hummerfredningsområder.'
            hits.append({
                'layer': 'Hummer - fredningsområder',
                'status': 'fredningsområde',
                'name': attrs.get('navn') or 'Hummer - fredningsområder',
                'notes': attrs.get('beskrivelse') or 'Treff i hummerfredningsområde.',
                'url': attrs.get('url') or '',
                'source': 'Fiskeridirektoratet Yggdrasil',
            })

        hummer_max = _ygg_query_point(LAYER_HUMMER_MAX, lat, lng)
        if hummer_max:
            attrs = hummer_max[0].get('attributes') or {}
            hits.append({
                'layer': 'Hummer - maksimalmål område',
                'status': 'maksimalmål område',
                'name': attrs.get('område') or attrs.get('navn') or 'Hummer - maksimalmål område',
                'notes': attrs.get('informasjon') or attrs.get('beskrivelse') or 'Treff i område med maksimalmål for hummer.',
                'url': attrs.get('lenke') or attrs.get('url') or '',
                'source': 'Fiskeridirektoratet Yggdrasil',
            })

    return {
        'match': bool(hits),
        'status': status,
        'name': name,
        'source': 'Fiskeridirektoratet Yggdrasil',
        'notes': notes,
        'hits': hits,
        'lat': lat,
        'lng': lng,
    }


# -------------------------
# Lovdata reference cards
# -------------------------


def get_lovdata_refs(species: str = '', gear_type: str = '', control_type: str = '') -> list[dict[str, str]]:
    mapping = _load_lovdata_topics()
    refs: list[dict[str, str]] = []
    topics = ['generic']
    species_key = _norm(species).replace(' ', '_')
    gear_key = _norm(gear_type).replace(' ', '_')
    control_key = _norm(control_type).replace(' ', '_')
    for key in [species_key, gear_key, control_key]:
        if key and key in mapping and key not in topics:
            topics.append(key)

    seen: set[str] = set()
    for topic in topics:
        for item in mapping.get(topic, []):
            url = str(item.get('url') or '').strip()
            title = str(item.get('title') or '').strip()
            if not url or url in seen:
                continue
            seen.add(url)
            refs.append({'name': 'Lovdata', 'ref': title or url, 'url': url, 'topic': topic})
    return refs


# -------------------------
# Bundle composer
# -------------------------


def compose_live_sources(control_type: str = '', species: str = '', gear_type: str = '', lat: float | None = None, lng: float | None = None, area_status: str = '') -> dict[str, Any]:
    sources: list[dict[str, str]] = []
    dynamic_items: list[dict[str, str]] = []
    diagnostics: list[str] = []

    def add_source(name: str, ref: str, url: str = '') -> None:
        key = (name.strip(), ref.strip(), url.strip())
        if not ref.strip():
            return
        if key in seen:
            return
        seen.add(key)
        payload = {'name': name.strip(), 'ref': ref.strip()}
        if url.strip():
            payload['url'] = url.strip()
        sources.append(payload)

    seen: set[tuple[str, str, str]] = set()

    # Lovdata topic refs
    for ref in get_lovdata_refs(species=species, gear_type=gear_type, control_type=control_type):
        add_source(ref['name'], ref['ref'], ref.get('url', ''))

    # J-meldinger
    try:
        for row in search_jmeldinger(species=species, gear_type=gear_type, area_status=area_status):
            title = row.get('title') or row.get('id') or 'J-melding'
            status = row.get('status') or ''
            add_source('Fiskeridirektoratet J-meldinger', f"{row.get('id', '')} {title} {status}".strip(), row.get('url', ''))
    except Exception as exc:  # pragma: no cover - network dependent
        diagnostics.append(f'J-meldinger utilgjengelig: {exc}')

    # Yggdrasil
    if lat is not None and lng is not None:
        try:
            zone = classify_position_live(lat, lng, species=species, gear_type=gear_type)
            for hit in zone.get('hits') or []:
                add_source(hit.get('source', 'Fiskeridirektoratet Yggdrasil'), hit.get('name', 'Live karttreff'), hit.get('url', ''))
                dynamic_items.append({
                    'key': f"live_{_norm(hit.get('layer')).replace(' ', '_')}_{len(dynamic_items)+1}",
                    'label': f"Live karttreff - {hit.get('layer')}",
                    'source_name': hit.get('source', 'Fiskeridirektoratet Yggdrasil'),
                    'source_ref': hit.get('name', ''),
                    'status': 'avvik' if hit.get('status') in {'stengt område', 'fredningsområde'} else 'ikke kontrollert',
                    'notes': hit.get('notes', ''),
                })
        except Exception as exc:  # pragma: no cover - network dependent
            diagnostics.append(f'Yggdrasil utilgjengelig: {exc}')

    return {'sources': sources, 'items': dynamic_items, 'diagnostics': diagnostics}



def reverse_geocode_live(lat: float, lng: float) -> dict[str, Any]:
    cache_key = f'{round(float(lat), 4)}:{round(float(lng), 4)}'
    now = time.time()
    with _REVERSE_GEOCODE_CACHE_LOCK:
        cached = _REVERSE_GEOCODE_CACHE.get(cache_key)
        if cached and (now - cached[0]) <= REVERSE_GEOCODE_CACHE_TTL:
            return dict(cached[1])
    url = 'https://nominatim.openstreetmap.org/reverse'
    resp = _safe_get(url, params={'lat': lat, 'lon': lng, 'format': 'jsonv2', 'zoom': 14, 'addressdetails': 1}, timeout=min(REQUEST_TIMEOUT, 2.5))
    data = resp.json()
    address = data.get('address') or {}
    locality = address.get('hamlet') or address.get('suburb') or address.get('neighbourhood') or address.get('village') or address.get('town') or address.get('city') or address.get('municipality') or ''
    municipality = address.get('municipality') or address.get('city') or address.get('town') or address.get('county') or ''
    county = address.get('county') or ''
    road = ' '.join(part for part in [address.get('road') or '', address.get('house_number') or ''] if part).strip()
    postcode = address.get('postcode') or ''
    parts = []
    for value in [road, locality, municipality, county]:
        value = str(value or '').strip()
        if value and value not in parts:
            parts.append(value)
    location_label = ', '.join(parts)
    payload = {
        'found': bool(data),
        'display_name': data.get('display_name') or '',
        'name': locality or municipality or county or '',
        'locality': locality,
        'municipality': municipality,
        'county': county,
        'road': road,
        'postcode': postcode,
        'location_label': location_label,
        'source': 'OpenStreetMap Nominatim',
        'source_url': 'https://nominatim.openstreetmap.org/'
    }
    with _REVERSE_GEOCODE_CACHE_LOCK:
        _REVERSE_GEOCODE_CACHE[cache_key] = (time.time(), dict(payload))
        if len(_REVERSE_GEOCODE_CACHE) > 256:
            for key, _ in sorted(_REVERSE_GEOCODE_CACHE.items(), key=lambda item: item[1][0])[:64]:
                _REVERSE_GEOCODE_CACHE.pop(key, None)
    return payload


def _ascii_header(text: str | None) -> str:
    normalized = unicodedata.normalize('NFKD', str(text or ''))
    normalized = ''.join(ch for ch in normalized if not unicodedata.combining(ch))
    return ' '.join(normalized.strip().lower().split())


def _tableau_csv_candidate_urls(view_url: str) -> list[str]:
    base = str(view_url or '').split('?')[0].rstrip('/')
    raw = str(view_url or '').strip()
    candidates = [
        raw + ('&' if '?' in raw else '?') + ':format=csv',
        raw + ('&' if '?' in raw else '?') + ':showVizHome=no&:format=csv',
        base + '.csv',
        base + '.csv?:showVizHome=no',
    ]
    out: list[str] = []
    seen: set[str] = set()
    for item in candidates:
        if item and item not in seen:
            seen.add(item)
            out.append(item)
    return out


def _guess_hummer_csv_dialect(text: str):
    sample = '\n'.join(str(text or '').splitlines()[:20])
    try:
        return csv.Sniffer().sniff(sample, delimiters=';,\t|')
    except Exception:
        class _FallbackDialect(csv.Dialect):
            delimiter = ';'
            quotechar = '"'
            doublequote = True
            skipinitialspace = True
            lineterminator = '\n'
            quoting = csv.QUOTE_MINIMAL
        return _FallbackDialect


HUMMER_FISHER_TYPES = {
    'fritidsfiskar',
    'hovudyrkefiskar',
    'biyrkefiskar',
    'fritidsfisker',
    'hovedyrkesfisker',
    'biyrkesfisker',
}


HUMMER_PARTICIPANT_RE = re.compile(
    r'(?:H[- ]?\d{4}[- ]?\d{3}|20\d{5}|[A-ZÆØÅ]{2,5}[- ]?[A-ZÆØÅ]{2,5}[- ]?\d{3,4}|[A-ZÆØÅ]{3,5}[- ]?\d{2}[- ]?\d{3,4})',
    re.IGNORECASE,
)


def _normalize_hummer_candidate_row(row: dict[str, Any], *, source_url: str = '') -> dict[str, str] | None:
    raw_name = str(row.get('name') or '').strip()
    raw_participant = str(row.get('participant_no') or row.get('hummer_participant_no') or '').strip()
    raw_fisher_type = ' '.join(str(row.get('fisher_type') or '').split()).strip()
    raw_season = str(row.get('last_registered_year') or row.get('last_registered') or row.get('season') or '').strip()

    participant = registry._normalize_hummer_no(raw_participant)
    name = registry.normalize_person_name(raw_name)
    fisher_type = raw_fisher_type

    norm_name = _norm(name)
    norm_fisher = _norm(fisher_type)

    if norm_name in HUMMER_FISHER_TYPES and not norm_fisher:
        fisher_type = name
        name = ''
        norm_name = ''
        norm_fisher = _norm(fisher_type)
    if norm_fisher in HUMMER_FISHER_TYPES and not fisher_type:
        fisher_type = raw_fisher_type
    if not participant and registry._normalize_hummer_no(fisher_type):
        participant = registry._normalize_hummer_no(fisher_type)
        fisher_type = ''
        norm_fisher = ''
    if name and participant and registry._compact(name) == registry._compact(participant):
        name = ''
        norm_name = ''
    if not name or norm_name in HUMMER_FISHER_TYPES or not participant:
        return None

    last_registered = registry.infer_last_registered(participant, raw_season)
    return {
        'name': name,
        'participant_no': participant,
        'fisher_type': fisher_type,
        'last_registered': last_registered,
        'last_registered_year': last_registered,
        'last_registered_display': registry.format_last_registered(last_registered),
        'registered_date_display': registry.format_last_registered(last_registered),
        'source': 'Fiskeridirektoratet - registrerte hummarfiskarar',
        'source_url': source_url or HUMMER_REGISTER_FALLBACK_URL,
    }


def _parse_hummer_csv(text: str, source_url: str = '') -> list[dict[str, str]]:
    dialect = _guess_hummer_csv_dialect(text)
    reader = csv.DictReader(io.StringIO(text), dialect=dialect)
    if not reader.fieldnames:
        return []
    header_lookup = {_ascii_header(name): name for name in reader.fieldnames if name}

    def pick(row: dict[str, Any], *keys: str) -> str:
        for key in keys:
            needle = _ascii_header(key)
            for normalized, original in header_lookup.items():
                if normalized == needle or normalized.startswith(needle) or needle in normalized:
                    value = row.get(original)
                    if str(value or '').strip():
                        return str(value).strip()
        return ''

    rows: list[dict[str, str]] = []
    seen: set[tuple[str, str]] = set()
    for raw in reader:
        name = pick(raw, 'navn', 'namn', 'fullt navn', 'fullt namn', 'name')
        if not name:
            for value in raw.values():
                candidate = str(value or '').strip()
                if ',' in candidate and not registry._normalize_hummer_no(candidate) and _norm(candidate) not in HUMMER_FISHER_TYPES:
                    name = candidate
                    break
        participant = pick(raw, 'deltakarnummer', 'deltakernummer', 'deltakarnr', 'deltakernr', 'participant_no')
        fisher_type = pick(raw, 'type fiskar', 'type fisker', 'fiskartype', 'fisher_type', 'fiskertype', 'type')
        season = pick(raw, 'sesong', 'sesongen', 'aar', 'år', 'year')
        item = _normalize_hummer_candidate_row({
            'name': name,
            'participant_no': participant,
            'fisher_type': fisher_type,
            'last_registered_year': season,
        }, source_url=source_url)
        if not item:
            continue
        key = (registry._compact(item.get('participant_no')), _norm(item.get('name')))
        if key in seen:
            continue
        seen.add(key)
        rows.append(item)
    return rows


def refresh_hummer_registry_cache(force: bool = False, max_age_seconds: int = 12 * 3600) -> list[dict[str, str]]:
    try:
        if HUMMER_CACHE_JSON.exists() and HUMMER_CACHE_META.exists() and not force:
            meta = json.loads(HUMMER_CACHE_META.read_text(encoding='utf-8'))
            fetched_at = float(meta.get('fetched_at') or 0)
            if fetched_at and (time.time() - fetched_at) < max_age_seconds:
                cached = json.loads(HUMMER_CACHE_JSON.read_text(encoding='utf-8'))
                if isinstance(cached, list) and cached:
                    return cached
    except Exception:
        pass

    candidate_urls: list[str] = []
    seen: set[str] = set()

    def add_url(url: str) -> None:
        url = str(url or '').strip()
        if not url or url in seen:
            return
        seen.add(url)
        candidate_urls.append(url)

    for url in _tableau_csv_candidate_urls(HUMMER_REGISTER_URL):
        add_url(url)

    fallback_extracted: list[dict[str, str]] = []
    try:
        fallback_resp = _safe_get(HUMMER_REGISTER_FALLBACK_URL)
        fallback_html = fallback_resp.text
        soup = BeautifulSoup(fallback_html, 'html.parser')
        for link in soup.find_all('a', href=True):
            href = str(link.get('href') or '').strip()
            if '.csv' in href.lower() or 'download' in href.lower():
                add_url(urljoin(HUMMER_REGISTER_FALLBACK_URL, href))
        for match in re.findall(r'https?://[^"\'\s>]+\.csv[^"\'\s<]*', fallback_html, re.IGNORECASE):
            add_url(match)
        fallback_extracted = _extract_hummer_candidates_from_html(fallback_html)
    except Exception:
        fallback_extracted = []

    for url in candidate_urls:
        try:
            resp = _safe_get(url)
            payload = resp.text
        except Exception:
            continue
        rows = _parse_hummer_csv(payload, source_url=url)
        if rows:
            HUMMER_CACHE_JSON.parent.mkdir(parents=True, exist_ok=True)
            HUMMER_CACHE_JSON.write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding='utf-8')
            HUMMER_CACHE_META.write_text(json.dumps({'fetched_at': time.time(), 'source_url': url, 'count': len(rows)}, ensure_ascii=False, indent=2), encoding='utf-8')
            return rows

    if fallback_extracted:
        HUMMER_CACHE_JSON.parent.mkdir(parents=True, exist_ok=True)
        HUMMER_CACHE_JSON.write_text(json.dumps(fallback_extracted, ensure_ascii=False, indent=2), encoding='utf-8')
        HUMMER_CACHE_META.write_text(json.dumps({'fetched_at': time.time(), 'source_url': HUMMER_REGISTER_FALLBACK_URL, 'count': len(fallback_extracted)}, ensure_ascii=False, indent=2), encoding='utf-8')
        return fallback_extracted

    if HUMMER_CACHE_JSON.exists():
        try:
            cached = json.loads(HUMMER_CACHE_JSON.read_text(encoding='utf-8'))
            if isinstance(cached, list):
                return cached
        except Exception:
            pass
    return []


def _extract_hummer_candidates_from_html(html: str) -> list[dict[str, str]]:
    soup = BeautifulSoup(html, 'html.parser')
    rows: list[dict[str, str]] = []
    seen: set[tuple[str, str]] = set()

    def add_candidate(candidate: dict[str, Any]) -> None:
        item = _normalize_hummer_candidate_row(candidate)
        if not item:
            return
        key = (registry._compact(item.get('participant_no')), _norm(item.get('name')))
        if key in seen:
            return
        seen.add(key)
        rows.append(item)

    # Prefer explicit table rows when present.
    for tr in soup.find_all('tr'):
        cells = [' '.join(cell.get_text(' ', strip=True).split()) for cell in tr.find_all(['th', 'td'])]
        cells = [cell for cell in cells if cell]
        if len(cells) < 2:
            continue
        participant = ''
        fisher_type = ''
        name_candidates: list[str] = []
        for cell in cells:
            normalized = _norm(cell)
            if not participant:
                match = HUMMER_PARTICIPANT_RE.search(cell)
                if match:
                    participant = registry._normalize_hummer_no(match.group(0) or '')
                    continue
            if normalized in HUMMER_FISHER_TYPES:
                fisher_type = cell
                continue
            if cell and not HUMMER_PARTICIPANT_RE.search(cell):
                name_candidates.append(cell)
        if participant and name_candidates:
            add_candidate({
                'name': name_candidates[0],
                'participant_no': participant,
                'fisher_type': fisher_type,
            })

    if rows:
        return rows

    participant_pat = HUMMER_PARTICIPANT_RE.pattern
    patterns = [
        re.compile(rf'(?P<name>[A-ZÆØÅ][A-Za-zÆØÅæøå\-]+,\s*[A-ZÆØÅ][A-Za-zÆØÅæøå\-]+(?:\s+[A-ZÆØÅ][A-Za-zÆØÅæøå\-]+){{0,3}}).{{0,120}}?(?P<participant>{participant_pat}).{{0,120}}?(?P<kind>hovudyrkefiskar|fritidsfiskar|biyrkefiskar|hovedyrkesfisker|fritidsfisker|biyrkesfisker)?', re.IGNORECASE),
        re.compile(rf'(?P<participant>{participant_pat}).{{0,120}}?(?P<name>[A-ZÆØÅ][A-Za-zÆØÅæøå\-]+,\s*[A-ZÆØÅ][A-Za-zÆØÅæøå\-]+(?:\s+[A-ZÆØÅ][A-Za-zÆØÅæøå\-]+){{0,3}}).{{0,120}}?(?P<kind>hovudyrkefiskar|fritidsfiskar|biyrkefiskar|hovedyrkesfisker|fritidsfisker|biyrkesfisker)?', re.IGNORECASE),
        re.compile(rf'(?P<name>[A-ZÆØÅ][A-Za-zÆØÅæøå\-]+(?:\s+[A-ZÆØÅ][A-Za-zÆØÅæøå\-]+){{1,3}}).{{0,120}}?(?P<participant>{participant_pat}).{{0,120}}?(?P<kind>hovudyrkefiskar|fritidsfiskar|biyrkefiskar|hovedyrkesfisker|fritidsfisker|biyrkesfisker)?', re.IGNORECASE),
        re.compile(rf'(?P<participant>{participant_pat}).{{0,120}}?(?P<name>[A-ZÆØÅ][A-Za-zÆØÅæøå\-]+(?:\s+[A-ZÆØÅ][A-Za-zÆØÅæøå\-]+){{1,3}}).{{0,120}}?(?P<kind>hovudyrkefiskar|fritidsfiskar|biyrkefiskar|hovedyrkesfisker|fritidsfisker|biyrkesfisker)?', re.IGNORECASE),
    ]
    text_blocks: list[str] = []
    for tag in soup.find_all(['script', 'table', 'tbody', 'tr', 'li', 'div', 'section', 'span', 'p']):
        raw = tag.get_text(' ', strip=True)
        lower = raw.lower() if raw else ''
        if raw and (HUMMER_PARTICIPANT_RE.search(raw) or any(kind in lower for kind in HUMMER_FISHER_TYPES)):
            text_blocks.append(raw)
    if not text_blocks:
        text_blocks = [soup.get_text('\n', strip=True)]

    for block in text_blocks:
        normalized_block = ' '.join(block.split())
        for pattern in patterns:
            for match in pattern.finditer(normalized_block):
                add_candidate({
                    'name': match.group('name') or '',
                    'participant_no': match.group('participant') or '',
                    'fisher_type': ' '.join(str(match.group('kind') or '').split()),
                })
    return rows


def lookup_hummer_participant_live(participant_no: str = '', name: str = '') -> dict[str, Any]:
    participant_no = registry._normalize_hummer_no(participant_no)
    name = registry.normalize_person_name(name or '')
    current_year = str(datetime.utcnow().year)

    try:
        cached_rows = refresh_hummer_registry_cache()
    except Exception:
        cached_rows = []

    cache_matches = registry.search_hummer_participants(participant_no=participant_no, name=name, limit=25)
    compact_participant = registry._compact(participant_no)
    normalized_name = registry._normalize_person_name(name)
    normalized_raw_name = _norm(name)

    for row in cache_matches:
        participant_match = bool(compact_participant and registry._compact(row.get('participant_no')) == compact_participant)
        row_name = registry._normalize_person_name(row.get('name'))
        row_raw_name = _norm(row.get('name'))
        name_match = bool(normalized_name and (row_name == normalized_name or row_raw_name == normalized_raw_name))
        if participant_match or name_match:
            person = dict(row)
            person['source'] = person.get('source') or 'Fiskeridirektoratet - registrerte hummarfiskarar'
            person['source_url'] = person.get('source_url') or HUMMER_REGISTER_FALLBACK_URL
            if not person.get('last_registered_display'):
                inferred = registry.infer_last_registered(person.get('participant_no'), current_year)
                person['last_registered'] = inferred
                person['last_registered_display'] = registry.format_last_registered(inferred)
                person['registered_date_display'] = person['last_registered_display']
            person['verified_at'] = datetime.utcnow().isoformat(timespec='seconds') + 'Z'
            return {
                'found': True,
                'person': person,
                'candidates': cache_matches[:10],
                'message': 'Treff i offentlig hummerregister.',
            }

    if cache_matches:
        return {
            'found': False,
            'message': 'Mulige treff i offentlig hummerregister. Velg kandidat fra listen.',
            'candidates': cache_matches[:10],
        }

    html = ''
    url = HUMMER_REGISTER_URL
    last_exc = None
    for candidate_url in (HUMMER_REGISTER_URL, HUMMER_REGISTER_FALLBACK_URL):
        try:
            resp = _safe_get(candidate_url)
            html = resp.text
            url = candidate_url
            if html:
                break
        except Exception as exc:
            last_exc = exc
            continue
    if not html:
        raise LiveSourceError(str(last_exc or 'Kunne ikke hente hummerregisteret'))

    text = BeautifulSoup(html, 'html.parser').get_text(' ', strip=True)
    hay = text.lower()

    extracted = _extract_hummer_candidates_from_html(html)
    matches: list[dict[str, str]] = []
    norm_name = _norm(registry.normalize_person_name(name))
    for row in extracted:
        score = 0
        if compact_participant and registry._compact(row.get('participant_no')) == compact_participant:
            score += 100
        row_name = _norm(row.get('name'))
        if norm_name and row_name == norm_name:
            score += 80
        elif norm_name and norm_name in row_name:
            score += 25
        if score:
            item = dict(row)
            item['_score'] = score
            matches.append(item)
    matches.sort(key=lambda item: (-int(item['_score']), item.get('name') or ''))

    if matches:
        best = matches[0]
        inferred_last = registry.infer_last_registered(best.get('participant_no'), current_year)
        person = {
            'participant_no': best.get('participant_no') or participant_no,
            'name': _clean_directory_name(best.get('name') or '') or ('' if registry.is_bad_person_name(name) else name),
            'fisher_type': best.get('fisher_type') or '',
            'source': 'Fiskeridirektoratet - registrerte hummarfiskarar',
            'source_url': url,
            'last_registered': inferred_last,
            'last_registered_display': registry.format_last_registered(inferred_last),
            'registered_date_display': registry.format_last_registered(inferred_last),
            'verified_at': datetime.utcnow().isoformat(timespec='seconds') + 'Z',
        }
        return {
            'found': True,
            'person': person,
            'candidates': [{k: v for k, v in row.items() if not k.startswith('_')} for row in matches[:10]],
            'message': 'Treff i offentlig hummerregister.'
        }

    person = {
        'participant_no': participant_no,
        'name': name,
        'source': 'Fiskeridirektoratet - registrerte hummarfiskarar',
        'source_url': url,
        'last_registered': registry.infer_last_registered(participant_no, current_year),
        'last_registered_display': registry.format_last_registered(registry.infer_last_registered(participant_no, current_year)),
        'registered_date_display': registry.format_last_registered(registry.infer_last_registered(participant_no, current_year)),
        'verified_at': datetime.utcnow().isoformat(timespec='seconds') + 'Z',
    }
    if participant_no and registry._compact(participant_no).lower() in registry._compact(hay).lower():
        return {'found': True, 'person': person, 'message': 'Treff på deltakarnummer i offentlig hummerregister (teksttreff).'}
    normalized_name = registry.normalize_person_name(name)
    alt_name = ''
    if normalized_name and ' ' in normalized_name:
        parts = normalized_name.split()
        alt_name = f"{parts[-1]}, {' '.join(parts[:-1])}".lower()
    if normalized_name and (normalized_name.lower() in hay or (alt_name and alt_name in hay)):
        return {'found': True, 'person': person, 'message': 'Mulig navnetreff i offentlig hummerregister (teksttreff).'}
    return {'found': False, 'message': 'Ingen tydelig treff i offentlig hummerregister.'}

# -------------------------
# v9 portal map integration
# -------------------------

MAP_PORTAL_URL = os.getenv('KV_PORTAL_MAP_URL', 'https://portal.fiskeridir.no/portal/apps/webappviewer/index.html?id=ea6c536f760548fe9f56e6edcc4825d8')
YGG_BASE = os.getenv('KV_PORTAL_MAPSERVER', 'https://gis.fiskeridir.no/server/rest/services/Fiskeridir_vern/MapServer')

LAYER_FLATOSTERS = 0
LAYER_HUMMER_FREDNING = 1
LAYER_KYSTTORSK_STENGT = 2
LAYER_KYSTTORSK_FORBUD = 3
LAYER_KORALLREV = 6
LAYER_HUMMER_MAX = 23
LAYER_STEINBIT = 34
LAYER_OSLOFJORD_FRITID = 35
LAYER_NULLFISKE = 37

PORTAL_LAYER_DEFS = [
    {'id': LAYER_FLATOSTERS, 'name': 'Flatøsters - forbudsområde', 'status': 'stengt område', 'color': '#e76f51', 'description': 'Forbud mot høsting av flatøsters i regulerte områder.'},
    {'id': LAYER_HUMMER_FREDNING, 'name': 'Hummer - fredningsområder', 'status': 'fredningsområde', 'color': '#f4a261', 'description': 'I hummerfredningsområdene er andre redskaper enn håndsnøre, fiskestang, juksa, dorg eller snurpenot ikke tillatt.'},
    {'id': LAYER_KYSTTORSK_STENGT, 'name': 'Kysttorsk - stengte områder', 'status': 'stengt område', 'color': '#e63946', 'description': 'Gytefelt der alt fiske er forbudt fra 1. januar til og med 30. april.'},
    {'id': LAYER_KYSTTORSK_FORBUD, 'name': 'Kysttorsk - forbudsområde', 'status': 'stengt område', 'color': '#d62828', 'description': 'Telemark til svenskegrensen: fiske etter torsk er forbudt hele året, med bare snevre unntak for uunngåelig ikke-levedyktig bifangst.'},
    {'id': LAYER_KORALLREV, 'name': 'Korallrev - forbudsområde', 'status': 'stengt område', 'color': '#6d597a', 'description': 'Område med forbud mot fiske nær korallrev.'},
    {'id': LAYER_HUMMER_MAX, 'name': 'Hummer - maksimalmål område', 'status': 'maksimalmål område', 'color': '#bc4749', 'description': 'Område på Skagerrakkysten med maksimalmål 32 cm for hummer.'},
    {'id': LAYER_STEINBIT, 'name': 'Saltstraumen - forbud steinbit', 'status': 'stengt område', 'color': '#577590', 'description': 'Område med forbud eller særregulering for steinbit.'},
    {'id': LAYER_OSLOFJORD_FRITID, 'name': 'Oslofjorden - fritidsfiskeregler', 'status': 'regulert område', 'color': '#457b9d', 'description': 'Oslofjorden: bare håndholdte redskaper for fisk, maks 10 teiner for skalldyr, maks 5 hummerteiner, forbud mot reketeiner og forbud mot fiske etter torsk.'},
    {'id': LAYER_NULLFISKE, 'name': 'Oslofjorden - nullfiskeområder', 'status': 'stengt område', 'color': '#1d3557', 'description': 'Nullfiskeområde der alt fiske er forbudt, med bare særskilte unntak.'},
]

PORTAL_LAYER_CACHE_DIR = CACHE_DIR / 'portal_layers'
PORTAL_LAYER_CACHE_DIR.mkdir(parents=True, exist_ok=True)


def portal_layer_catalog() -> list[dict[str, Any]]:
    rows = []
    for item in PORTAL_LAYER_DEFS:
        rows.append({
            'id': item['id'],
            'name': item['name'],
            'status': item['status'],
            'color': item['color'],
            'description': item.get('description', ''),
            'service_url': f'{YGG_BASE}/{item["id"]}',
        })
    return rows


def _portal_layer_def(layer_id: int) -> dict[str, Any] | None:
    for item in PORTAL_LAYER_DEFS:
        item_id = item.get('id')
        if item_id is None:
            continue
        if int(item_id) == int(layer_id):
            return item
    return None


def _local_zone_matches_layer(zone: dict[str, Any], layer_id: int, layer_def: dict[str, Any]) -> bool:
    raw_ids = zone.get('layer_ids') or zone.get('portal_layer_ids') or zone.get('layer_id') or zone.get('portal_layer_id')
    zone_layer_name = str(zone.get('layer_name') or '').strip()
    layer_name_candidates = _layer_name_candidates(layer_def)
    normalized_ids: set[int] = set()
    id_matched = False
    if raw_ids is not None and raw_ids != '':
        if not isinstance(raw_ids, (list, tuple, set)):
            raw_ids = [raw_ids]
        for value in raw_ids:
            try:
                normalized_ids.add(int(value))
            except Exception:
                continue
        id_matched = bool(normalized_ids and (normalized_ids & _layer_id_candidates(layer_id, layer_def)))

    name_matched = bool(zone_layer_name and _layer_name_matches(zone_layer_name, layer_name_candidates))
    if id_matched and (not zone_layer_name or not layer_name_candidates or name_matched):
        return True
    if name_matched:
        return True
    if zone_layer_name and normalized_ids:
        return False

    zone_status = _ascii_header(zone.get('status') or '')
    layer_status = _ascii_header(layer_def.get('status') or '')
    if not zone_status or not layer_status:
        return False

    if zone_status == layer_status:
        zone_meta = map_relevance.decorate_zone_row(zone)
        layer_meta = map_relevance.decorate_catalog_row(layer_def)
        zone_fishery = {map_relevance.normalize_fishery(value) for value in list(zone_meta.get('fishery_tags') or []) if map_relevance.normalize_fishery(value)}
        layer_fishery = {map_relevance.normalize_fishery(value) for value in list(layer_meta.get('fishery_tags') or []) if map_relevance.normalize_fishery(value)}
        if zone_fishery and layer_fishery:
            return bool(zone_fishery & layer_fishery)
        zone_gear = {map_relevance.normalize_gear(value) for value in list(zone_meta.get('gear_tags') or []) if map_relevance.normalize_gear(value)}
        layer_gear = {map_relevance.normalize_gear(value) for value in list(layer_meta.get('gear_tags') or []) if map_relevance.normalize_gear(value)}
        if zone_gear and layer_gear:
            return bool(zone_gear & layer_gear)
        zone_blob = _ascii_header(zone_meta.get('selection_blob') or zone_layer_name or zone.get('name') or '')
        layer_blob = _ascii_header(layer_meta.get('selection_blob') or layer_def.get('name') or '')
        zone_tokens = _token_set(zone_blob) - _GENERIC_LAYER_TOKENS
        layer_tokens = _token_set(layer_blob) - _GENERIC_LAYER_TOKENS
        if zone_tokens and layer_tokens and (zone_tokens & layer_tokens):
            return True
        if not normalized_ids and not zone_layer_name and not zone_fishery and not zone_gear:
            return True
    if layer_status == 'stengt omrade' and zone_status == 'nullfiskeomrade':
        return True
    return False



def _local_zone_geojson_for_layer(layer_id: int) -> dict[str, Any]:
    layer_def = _portal_layer_def(layer_id) or {}
    name = str(layer_def.get('name') or '').strip()
    description = str(layer_def.get('description') or '').strip()

    features: list[dict[str, Any]] = []
    for zone in area.ZONES:
        if not _local_zone_matches_layer(zone, layer_id, layer_def):
            continue
        polygon = zone.get('polygon') or []
        if len(polygon) < 3:
            continue
        coordinates = [[float(point[1]), float(point[0])] for point in polygon if isinstance(point, (list, tuple)) and len(point) >= 2]
        if len(coordinates) < 3:
            continue
        if coordinates[0] != coordinates[-1]:
            coordinates.append(list(coordinates[0]))
        features.append({
            'type': 'Feature',
            'properties': {
                'navn': zone.get('name') or name or 'Lokalt regulert område',
                'omraade': zone.get('name') or name or 'Lokalt regulert område',
                'status': zone.get('status') or layer_def.get('status') or '',
                'info': zone.get('notes') or description or '',
                'beskrivelse': zone.get('notes') or description or '',
                'source': zone.get('source') or 'Lokal reserveflate',
                'source_kind': zone.get('source_kind') or 'fallback',
                'url': zone.get('url') or MAP_PORTAL_URL,
                'layer_id': layer_id,
            },
            'geometry': {
                'type': 'Polygon',
                'coordinates': [coordinates],
            },
        })
    return {'type': 'FeatureCollection', 'features': features}



def _portal_cache_meta(meta_path: Path) -> dict[str, Any]:
    if not meta_path.exists():
        return {}
    try:
        data = json.loads(meta_path.read_text(encoding='utf-8'))
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}



def _portal_cache_payload(cache_path: Path) -> dict[str, Any]:
    if not cache_path.exists():
        return {'type': 'FeatureCollection', 'features': []}
    try:
        payload = json.loads(cache_path.read_text(encoding='utf-8'))
    except Exception:
        payload = {'type': 'FeatureCollection', 'features': []}
    if payload.get('type') != 'FeatureCollection':
        return {'type': 'FeatureCollection', 'features': []}
    payload['features'] = list(payload.get('features') or [])
    return payload



def _portal_cache_has_features(payload: dict[str, Any] | None) -> bool:
    return bool((payload or {}).get('features'))



def _write_portal_cache(cache_path: Path, meta_path: Path, payload: dict[str, Any], *, source_kind: str) -> None:
    try:
        cache_path.write_text(json.dumps(payload, ensure_ascii=False), encoding='utf-8')
        meta_path.write_text(json.dumps({'refreshed_at_unix': time.time(), 'source_kind': source_kind}, ensure_ascii=False), encoding='utf-8')
    except Exception:
        pass



def fetch_portal_geojson(layer_id: int, *, force: bool = False, max_age_seconds: int = 6 * 3600) -> dict[str, Any]:
    cache_path = PORTAL_LAYER_CACHE_DIR / f'layer_{layer_id}.geojson'
    meta_path = PORTAL_LAYER_CACHE_DIR / f'layer_{layer_id}.meta.json'
    local_fallback = _local_zone_geojson_for_layer(layer_id)
    cached = _portal_cache_payload(cache_path)
    meta = _portal_cache_meta(meta_path)
    cached_kind = str(meta.get('source_kind') or '').strip().lower() or 'unknown'
    cache_fresh = _cache_is_fresh(meta_path, max_age_seconds)

    if not force and cache_fresh and _portal_cache_has_features(cached):
        if cached_kind == 'live' or not LIVE_ENABLED:
            return cached

    if LIVE_ENABLED:
        url = f'{YGG_BASE}/{layer_id}/query'
        params = {
            'where': '1=1',
            'outFields': '*',
            'returnGeometry': 'true',
            'f': 'geojson',
            'outSR': '4326',
        }
        try:
            data = _safe_get(url, params=params).json()
            if data.get('type') != 'FeatureCollection':
                data = {'type': 'FeatureCollection', 'features': []}
            data['features'] = list(data.get('features') or [])
            if _portal_cache_has_features(data):
                _write_portal_cache(cache_path, meta_path, data, source_kind='live')
                return data
        except Exception:
            pass

    if _portal_cache_has_features(cached):
        return cached

    if _portal_cache_has_features(local_fallback):
        _write_portal_cache(cache_path, meta_path, local_fallback, source_kind='fallback')
        return local_fallback

    empty = {'type': 'FeatureCollection', 'features': []}
    _write_portal_cache(cache_path, meta_path, empty, source_kind='empty')
    return empty



def _feature_attr(feature: dict[str, Any], *keys: str) -> str:
    attrs = feature.get('attributes') or feature.get('properties') or {}
    for key in keys:
        val = attrs.get(key)
        if str(val or '').strip():
            return str(val).strip()
    return ''



def classify_position_live(lat: float, lng: float, species: str = '', gear_type: str = '', control_type: str = '') -> dict[str, Any]:
    hits: list[dict[str, Any]] = []
    highest = {
        'rank': 0,
        'status': 'ingen treff',
        'name': '',
        'notes': 'Ingen treff i Fiskeridirektoratets kartlag for denne posisjonen.',
    }
    priorities = {'stengt område': 4, 'fredningsområde': 3, 'maksimalmål område': 2, 'regulert område': 1}

    for layer in PORTAL_LAYER_DEFS:
        try:
            features = _ygg_query_point(layer['id'], lat, lng)
        except Exception:
            continue
        if not features:
            continue
        feature = features[0]
        name = _feature_attr(feature, 'omraade', 'navn', 'kat_ordning_text', 'område') or layer['name']
        notes = _feature_attr(feature, 'info', 'beskrivelse', 'stengt_text', 'informasjon', 'regelverk', 'regler') or layer.get('description') or layer['name']
        url = _feature_attr(feature, 'url', 'url_lovtekst', 'lenke') or MAP_PORTAL_URL
        hit = {
            'layer': layer['name'],
            'status': layer['status'],
            'name': name,
            'notes': notes,
            'url': url,
            'source': 'Fiskeridirektoratet kartportal',
        }
        hits.append(hit)
        rank = priorities.get(layer['status'], 0)
        if rank > highest['rank']:
            highest = {'rank': rank, 'status': layer['status'], 'name': name, 'notes': notes}

    return {
        'match': bool(hits),
        'status': highest['status'],
        'name': highest['name'],
        'source': 'Fiskeridirektoratet kartportal',
        'notes': highest['notes'],
        'hits': hits,
        'lat': lat,
        'lng': lng,
        'portal_url': MAP_PORTAL_URL,
    }



def compose_live_sources(control_type: str = '', species: str = '', gear_type: str = '', lat: float | None = None, lng: float | None = None, area_status: str = '') -> dict[str, Any]:
    diagnostics: list[str] = []
    sources: list[dict[str, str]] = [
        {'name': 'Fiskeridirektoratet kartportal', 'ref': 'Frednings- og forbudsområder', 'url': MAP_PORTAL_URL},
        {'name': 'Fiskeridirektoratet', 'ref': 'Fartøyregisteret API', 'url': FDIR_TAR_URL},
    ]
    if _norm(control_type).startswith('kom'):
        sources.append({'name': 'Fiskeridirektoratet', 'ref': 'J-meldinger', 'url': JM_URL})
    if _norm(species) == 'hummer':
        sources.append({'name': 'Fiskeridirektoratet', 'ref': 'Registrerte hummarfiskarar', 'url': HUMMER_REGISTER_URL})
    if lat is not None and lng is not None:
        try:
            live_pos = classify_position_live(lat, lng, species=species, gear_type=gear_type)
            for hit in live_pos.get('hits') or []:
                sources.append({'name': hit.get('source') or 'Fiskeridirektoratet kartportal', 'ref': hit.get('name') or hit.get('layer') or '', 'url': hit.get('url') or MAP_PORTAL_URL})
        except Exception as exc:
            diagnostics.append(str(exc))
    sources.extend(get_lovdata_refs(species=species, gear_type=gear_type, control_type=control_type))
    # dedupe
    deduped: list[dict[str, str]] = []
    seen = set()
    for item in sources:
        key = (item.get('name', ''), item.get('ref', ''), item.get('url', ''))
        if key in seen:
            continue
        seen.add(key)
        deduped.append(item)
    return {'sources': deduped, 'diagnostics': diagnostics}


_DIRECTORY_STOPWORDS = {
    'veibeskrivelse', 'vis', 'vis nummer', 'vis telefon', 'telefonnummer', 'kart', 'nær meg', 'ring', 'send sms', 'facebook', 'instagram',
    'linkedin', 'hjelp', 'personvern', 'cookiepolicy', 'submit', 'søk', 'bunntekst', 'utgiver', '1881', 'gulesider'
}


def _clean_directory_name(value: str) -> str:
    name = ' '.join(str(value or '').split()).strip(' ,;|-')
    if registry.is_bad_person_name(name):
        return ''
    return name


def _looks_like_name(value: str) -> bool:
    value = _clean_directory_name(value)
    if not value or len(value) < 4:
        return False
    if any(ch.isdigit() for ch in value):
        return False
    low = value.lower()
    if low in _DIRECTORY_STOPWORDS:
        return False
    words = value.split()
    return len(words) >= 2 and all(word[:1].isalpha() for word in words[:3])


def _looks_like_address(value: str) -> bool:
    value = ' '.join(str(value or '').strip().split())
    if not value:
        return False
    low = value.lower()
    if re.search(r'\b\d{4}\b', value):
        return True
    tokens = ['vei', 'veien', 'gata', 'gate', 'vn', 'plass', 'allé', 'alle', 'brygge', 'road']
    return any(token in low for token in tokens)


def _extract_directory_jsonld(soup: BeautifulSoup, source_name: str, source_url: str) -> list[dict[str, str]]:
    out: list[dict[str, str]] = []
    seen: set[tuple[str, str, str]] = set()

    def visit(obj: Any) -> None:
        if isinstance(obj, list):
            for item in obj:
                visit(item)
            return
        if not isinstance(obj, dict):
            return
        if '@graph' in obj:
            visit(obj['@graph'])
        typ = str(obj.get('@type') or obj.get('type') or '')
        if typ and typ.lower() not in {'person', 'localbusiness', 'organization', 'contactpoint'}:
            return
        name = _clean_directory_name(str(obj.get('name') or '').strip())
        phone = str(obj.get('telephone') or '').strip()
        address = obj.get('address')
        if isinstance(address, dict):
            address = ' '.join(str(address.get(part) or '').strip() for part in ['streetAddress', 'postalCode', 'addressLocality'] if str(address.get(part) or '').strip()).strip()
        address = str(address or '').strip()
        if not any([name, phone, address]):
            return
        norm_phone = ''
        match = PHONE_RE.search(phone.replace(' ', '')) if phone else None
        if match:
            norm_phone = match.group(1)
        key = (name.lower(), norm_phone, address.lower())
        if key in seen:
            return
        seen.add(key)
        out.append({'name': name, 'phone': norm_phone or phone, 'address': address, 'source': source_name, 'source_url': source_url})

    for tag in soup.find_all('script', attrs={'type': re.compile(r'ld\+json', re.I)}):
        raw = (tag.string or tag.get_text() or '').strip()
        if not raw:
            continue
        try:
            payload = json.loads(raw)
        except Exception:
            continue
        visit(payload)
    return out


def _extract_directory_text_candidates(html: str, source_name: str, source_url: str) -> list[dict[str, str]]:
    soup = BeautifulSoup(html, 'html.parser')
    for tag in soup(['script', 'style', 'noscript']):
        tag.decompose()
    lines = [' '.join(line.split()) for line in soup.get_text('\n').splitlines()]
    lines = [line for line in lines if line and line.lower() not in _DIRECTORY_STOPWORDS]
    out: list[dict[str, str]] = []
    seen: set[tuple[str, str, str]] = set()
    for idx, line in enumerate(lines):
        pm = PHONE_RE.search(line.replace(' ', '')) or PHONE_RE.search(line)
        if not pm:
            continue
        phone = pm.group(1)
        prev = lines[max(0, idx - 3): idx]
        nxt = lines[idx + 1: idx + 4]
        name = next((cand for cand in reversed(prev) if _looks_like_name(cand)), '')
        address = next((cand for cand in prev + nxt if _looks_like_address(cand)), '')
        if not name:
            name = next((cand for cand in nxt if _looks_like_name(cand)), '')
        if not any([name, address, phone]):
            continue
        key = (name.lower(), phone, address.lower())
        if key in seen:
            continue
        seen.add(key)
        out.append({'name': name, 'phone': phone, 'address': address, 'source': source_name, 'source_url': source_url})
    return out


def _fetch_directory_html(urls: list[str]) -> tuple[str, str]:
    for url in urls:
        try:
            resp = _safe_get(url)
        except Exception:
            continue
        if resp.status_code == 200 and '<html' in resp.text.lower():
            return url, resp.text
    return '', ''


def _score_directory_candidate(row: dict[str, str], phone: str = '', name: str = '', address: str = '') -> int:
    score = 0
    row_phone = ''.join(ch for ch in str(row.get('phone') or '') if ch.isdigit())[-8:]
    target_phone = ''.join(ch for ch in str(phone or '') if ch.isdigit())[-8:]
    if target_phone and row_phone == target_phone:
        score += 120
    row_name = _norm(row.get('name'))
    target_name = _norm(name)
    if target_name:
        if row_name == target_name:
            score += 90
        elif target_name in row_name:
            score += 35
    row_address = _norm(row.get('address'))
    target_address = _norm(address)
    if target_address:
        if row_address == target_address:
            score += 60
        elif target_address and target_address in row_address:
            score += 20
    return score


def lookup_directory_candidates(phone: str = '', name: str = '', address: str = '') -> dict[str, Any]:
    search_terms: list[str] = []
    base_query = ' '.join(part for part in [phone, name, address] if str(part or '').strip()).strip()
    if phone:
        search_terms.append(str(phone).strip())
    if name and address:
        search_terms.append(' '.join([str(name).strip(), str(address).strip()]).strip())
    if name:
        search_terms.append(str(name).strip())
    if address:
        search_terms.append(str(address).strip())
    if base_query:
        search_terms.append(base_query)
    ordered_terms: list[str] = []
    seen_terms: set[str] = set()
    for term in search_terms:
        normalized = ' '.join(str(term or '').split()).strip()
        if not normalized or normalized.lower() in seen_terms:
            continue
        seen_terms.add(normalized.lower())
        ordered_terms.append(normalized)
    if not ordered_terms:
        return {'found': False, 'message': 'Ingen søkeverdi oppgitt for katalogsøk.', 'candidates': []}

    candidates: list[dict[str, str]] = []
    for query in ordered_terms[:4]:
        searches = [
            ('1881', [
                f'https://www.1881.no/?query={quote_plus(query)}',
                f'https://www.1881.no/sok/?query={quote_plus(query)}',
                f'https://www.1881.no/search/?query={quote_plus(query)}',
            ]),
            ('Gulesider', [
                f'https://www.gulesider.no/{quote(query)}/personer',
                f'https://www.gulesider.no/person?query={quote_plus(query)}',
                f'https://www.gulesider.no/personer?query={quote_plus(query)}',
            ]),
        ]
        for source_name, urls in searches:
            used_url, html = _fetch_directory_html(urls)
            if not html:
                continue
            soup = BeautifulSoup(html, 'html.parser')
            rows = _extract_directory_jsonld(soup, source_name, used_url)
            if not rows:
                rows = _extract_directory_text_candidates(html, source_name, used_url)
            candidates.extend(rows[:10])

    scored = []
    seen: set[tuple[str, str, str]] = set()
    for row in candidates:
        key = (_norm(row.get('name')), ''.join(ch for ch in str(row.get('phone') or '') if ch.isdigit())[-8:], _norm(row.get('address')))
        if key in seen:
            continue
        seen.add(key)
        score = _score_directory_candidate(row, phone=phone, name=name, address=address)
        if score > 0 or row.get('phone') or row.get('address'):
            item = dict(row)
            item['match_score'] = score
            scored.append(item)
    scored.sort(key=lambda item: (-int(item.get('match_score') or 0), _norm(item.get('name'))))
    if not scored:
        return {'found': False, 'message': 'Ingen tydelige treff i offentlige kataloger.', 'candidates': []}
    best = dict(scored[0])
    person = {
        'name': _clean_directory_name(best.get('name') or '') or ('' if registry.is_bad_person_name(name) else name),
        'address': best.get('address') or address,
        'phone': best.get('phone') or phone,
        'source': best.get('source') or 'Offentlig katalog',
        'source_url': best.get('source_url') or '',
        'match_reason': '1881 / Gulesider',
    }
    return {'found': True, 'person': person, 'candidates': scored[:8], 'message': 'Treff i offentlig katalog.'}

# -------------------------
# v43 feltklar portal / kart-overstyringer
# -------------------------

MAP_PORTAL_URL = os.getenv('KV_PORTAL_MAP_URL', 'https://portal.fiskeridir.no/portal/apps/webappviewer/index.html?id=ea6c536f760548fe9f56e6edcc4825d8')
YGG_BASE = os.getenv('KV_PORTAL_MAPSERVER', 'https://portal.fiskeridir.no/server/rest/services/fiskeridirWMS_fiskeri/MapServer')
VERN_BASE = os.getenv('KV_PORTAL_VERN_MAPSERVER', 'https://portal.fiskeridir.no/server/rest/services/Fiskeridir_vern/MapServer')
PORTAL_LAYER_SCHEMA_VERSION = os.getenv('KV_PORTAL_LAYER_SCHEMA_VERSION', 'v76')
PORTAL_LAYER_CACHE_JSON = CACHE_DIR / f'portal_layer_catalog_cache_{PORTAL_LAYER_SCHEMA_VERSION}.json'
PORTAL_LAYER_CACHE_META = CACHE_DIR / f'portal_layer_catalog_meta_{PORTAL_LAYER_SCHEMA_VERSION}.json'
PORTAL_LAYER_CACHE_DIR = CACHE_DIR / f'portal_layers_{PORTAL_LAYER_SCHEMA_VERSION}'
PORTAL_LAYER_CACHE_DIR.mkdir(parents=True, exist_ok=True)


def _fallback_portal_layer_defs() -> list[dict[str, Any]]:
    return [
        {'id': 75, 'name': 'Høstingsforskriften forbudsområder', 'status': 'stengt område', 'color': '#b5171e', 'description': 'Forbudsområder etter høstingsforskriften.', 'geometry_type': 'esriGeometryPolygon', 'alertable': True, 'local_zone_aliases': ['Høstingsforskriften forbudsområder']},
        {'id': 76, 'name': 'Hummer - fredningsområder', 'status': 'fredningsområde', 'color': '#f4a261', 'description': 'Fredningsområder for hummer.', 'geometry_type': 'esriGeometryPolygon', 'alertable': True, 'legacy_ids': [1], 'local_zone_aliases': ['Hummer - fredningsområder']},
        {'id': 77, 'name': 'Hummer - maksimalmål område', 'status': 'maksimalmål område', 'color': '#bc4749', 'description': 'Område med særskilt maksimalmål for hummer.', 'geometry_type': 'esriGeometryPolygon', 'alertable': True, 'legacy_ids': [23], 'local_zone_aliases': ['Hummer - maksimalmål område']},
        {'id': 78, 'name': 'J-melding stengte fiskefelt', 'status': 'stengt område', 'color': '#c1121f', 'description': 'Gjeldende J-melding stengte fiskefelt.', 'geometry_type': 'esriGeometryPolygon', 'alertable': True, 'local_zone_aliases': ['J-melding stengte fiskefelt']},
        {'id': 73, 'name': 'Forbud mot høsting av flatøsters Sørlandsleia', 'status': 'stengt område', 'color': '#e76f51', 'description': 'Forbudsområde for flatøsters.', 'geometry_type': 'esriGeometryPolygon', 'alertable': True, 'legacy_ids': [0], 'local_zone_aliases': ['Flatøsters - forbudsområde']},
        {'id': 80, 'name': 'Korallrev - forbudsområde', 'status': 'stengt område', 'color': '#6d597a', 'description': 'Forbud mot fiske nær korallrev.', 'geometry_type': 'esriGeometryPolygon', 'alertable': True, 'legacy_ids': [6], 'local_zone_aliases': ['Korallrev - forbudsområde']},
        {'id': 82, 'name': 'Kysttorsk - forbudsområde', 'status': 'stengt område', 'color': '#d62828', 'description': 'Forbudsområde for kysttorsk.', 'geometry_type': 'esriGeometryPolygon', 'alertable': True, 'legacy_ids': [3], 'local_zone_aliases': ['Kysttorsk - forbudsområde']},
        {'id': 83, 'name': 'Kysttorsk - stengte gytefelt januar-april', 'status': 'stengt område', 'color': '#e63946', 'description': 'Stengte gytefelt for kysttorsk.', 'geometry_type': 'esriGeometryPolygon', 'alertable': True, 'legacy_ids': [2], 'local_zone_aliases': ['Kysttorsk - stengte områder', 'Kysttorsk - stengte gytefelt januar-april']},
        {'id': 84, 'name': 'Leppefisk - forskningsområde', 'status': 'regulert område', 'color': '#3d5a80', 'description': 'Forsknings- og reguleringsområde for leppefisk.', 'geometry_type': 'esriGeometryPolygon', 'alertable': True, 'local_zone_aliases': ['Leppefisk - forskningsområde']},
        {'id': 87, 'name': 'Nasjonale laksefjorder', 'status': 'regulert område', 'color': '#457b9d', 'description': 'Nasjonale laksefjorder med særregler.', 'geometry_type': 'esriGeometryPolygon', 'alertable': True, 'local_zone_aliases': ['Nasjonale laksefjorder']},
        {'id': 3, 'name': 'Oslofjorden - nullfiskeområder', 'status': 'stengt område', 'color': '#1d3557', 'description': 'Nullfiskeområder i Oslofjorden.', 'geometry_type': 'esriGeometryPolygon', 'alertable': True, 'legacy_ids': [37], 'local_zone_aliases': ['Oslofjorden - nullfiskeområder']},
        {'id': 35, 'name': 'Oslofjorden - fritidsfiskeregler', 'status': 'regulert område', 'color': '#457b9d', 'description': 'Særregler for fritidsfiske i Oslofjorden.', 'geometry_type': 'esriGeometryPolygon', 'alertable': True, 'local_zone_aliases': ['Oslofjorden - fritidsfiskeregler']},
        {'id': 200, 'name': 'Saltstraumen - forbud steinbit', 'status': 'stengt område', 'color': '#577590', 'description': 'Forbud eller særregulering for steinbit i Saltstraumen.', 'geometry_type': 'esriGeometryPolygon', 'alertable': True, 'legacy_ids': [34], 'local_zone_aliases': ['Saltstraumen - forbud steinbit']},
        {'id': 208, 'name': 'Raet nasjonalpark - sonevern', 'status': 'regulert område', 'color': '#2a9d8f', 'description': 'Sonevern og fiskeriregler i Raet nasjonalpark.', 'geometry_type': 'esriGeometryPolygon', 'alertable': True, 'local_zone_aliases': ['Raet nasjonalpark - sonevern']},
        {'id': 88, 'name': 'Reguleringer stormasket trål inntil 12 nm', 'status': 'regulert område', 'color': '#4d908e', 'description': 'Reguleringsområder for stormasket trål.', 'geometry_type': 'esriGeometryPolygon', 'alertable': True, 'local_zone_aliases': ['Reguleringer stormasket trål inntil 12 nm']},
        {'id': 89, 'name': 'Tare høstefelt', 'status': 'regulert område', 'color': '#7a9e7e', 'description': 'Tarehøstefelt.', 'geometry_type': 'esriGeometryPolygon', 'alertable': True, 'local_zone_aliases': ['Tare høstefelt']},
        {'id': 90, 'name': 'Tare referanseområder', 'status': 'fredningsområde', 'color': '#84a98c', 'description': 'Referanseområder for tare med særskilt vern.', 'geometry_type': 'esriGeometryPolygon', 'alertable': True, 'local_zone_aliases': ['Tare referanseområder']},
        {'id': 93, 'name': 'Tobis åpne områder', 'status': 'regulert område', 'color': '#8ecae6', 'description': 'Områder åpnet for tobisfiske.', 'geometry_type': 'esriGeometryPolygon', 'alertable': False, 'local_zone_aliases': ['Tobis åpne områder']},
        {'id': 94, 'name': 'Torsk - gyteområder forbudsområder', 'status': 'stengt område', 'color': '#b56576', 'description': 'Forbudsområder knyttet til torskens gyteområder.', 'geometry_type': 'esriGeometryPolygon', 'alertable': True, 'local_zone_aliases': ['Torsk - gyteområder forbudsområder']},
        {'id': 85, 'name': 'Torsk - oppvekstområder forbudsområder', 'status': 'stengt område', 'color': '#8d5a97', 'description': 'Forbudsområder knyttet til torskens oppvekstområder.', 'geometry_type': 'esriGeometryPolygon', 'alertable': True, 'local_zone_aliases': ['Torsk - oppvekstområder forbudsområder']},
        {'id': 91, 'name': 'Verneområder bunnhabitat', 'status': 'fredningsområde', 'color': '#6a4c93', 'description': 'Verneområder for sårbare bunnhabitater.', 'geometry_type': 'esriGeometryPolygon', 'alertable': True, 'local_zone_aliases': ['Verneområder bunnhabitat']},
        {'id': 92, 'name': 'Fiskeforbud Borgundfjorden', 'status': 'stengt område', 'color': '#9d0208', 'description': 'Lokalt fiskeforbud i Borgundfjorden.', 'geometry_type': 'esriGeometryPolygon', 'alertable': True, 'legacy_ids': [142], 'local_zone_aliases': ['Fiskeforbud Borgundfjorden']},
        {'id': 32, 'name': 'Breivikfjorden lokalregulering', 'status': 'regulert område', 'color': '#355070', 'description': 'Lokale fiskerireguleringer i Breivikfjorden.', 'geometry_type': 'esriGeometryPolygon', 'alertable': True, 'legacy_ids': [186], 'local_zone_aliases': ['Breivikfjorden lokalregulering']},
        {'id': 139, 'name': 'Trålforbud Jenn egga / Malangsgrunnen', 'status': 'stengt område', 'color': '#7b2cbf', 'description': 'Trålforbudsområde ved Jenn egga / Malangsgrunnen.', 'geometry_type': 'esriGeometryPolygon', 'alertable': True, 'legacy_ids': [197], 'local_zone_aliases': ['Trålforbud Jenn egga / Malangsgrunnen']},
        {'id': 140, 'name': 'Trålforbud Storegga', 'status': 'stengt område', 'color': '#9d4edd', 'description': 'Trålforbudsområde ved Storegga.', 'geometry_type': 'esriGeometryPolygon', 'alertable': True, 'legacy_ids': [198], 'local_zone_aliases': ['Trålforbud Storegga']},
        {'id': 25, 'name': 'Svalbard - fiskeforbud sårbare økosystemer', 'status': 'stengt område', 'color': '#560bad', 'description': 'Fiskeforbud for sårbare økosystemer ved Svalbard.', 'geometry_type': 'esriGeometryPolygon', 'alertable': True, 'local_zone_aliases': ['Svalbard - fiskeforbud sårbare økosystemer']},
        {'id': 26, 'name': 'Svalbard - forbud mot fiske i fiskevernsonen', 'status': 'stengt område', 'color': '#480ca8', 'description': 'Forbudsområde i fiskevernsonen ved Svalbard.', 'geometry_type': 'esriGeometryPolygon', 'alertable': True, 'local_zone_aliases': ['Svalbard - forbud mot fiske i fiskevernsonen']},
        {'id': 33, 'name': 'Forbud mot å fiske hyse i Finnmark', 'status': 'stengt område', 'color': '#9b2226', 'description': 'Forbudsområde for hysefiske i Finnmark.', 'geometry_type': 'esriGeometryPolygon', 'alertable': True, 'local_zone_aliases': ['Forbud mot å fiske hyse i Finnmark']},
        {'id': 74, 'name': 'Henningsværboksen', 'status': 'regulert område', 'color': '#264653', 'description': 'Særregulert område i Henningsvær.', 'geometry_type': 'esriGeometryPolygon', 'alertable': True, 'local_zone_aliases': ['Henningsværboksen']},
        {'id': 95, 'name': 'Lofotfiske 2025', 'status': 'regulert område', 'color': '#355070', 'description': 'Aktuelle reguleringer for Lofotfiske 2025.', 'geometry_type': 'esriGeometryPolygon', 'alertable': True, 'local_zone_aliases': ['Lofotfiske 2025']},
        {'id': 96, 'name': 'Havdeling torsk/hyse/sei fartøy 21-27,9 m', 'status': 'regulert område', 'color': '#4d908e', 'description': 'Avgrensning for havdeling knyttet til torsk, hyse og sei.', 'geometry_type': 'esriGeometryPolygon', 'alertable': True, 'local_zone_aliases': ['Havdeling torsk/hyse/sei fartøy 21-27,9 m']},
        {'id': 97, 'name': 'Havdeling torsk/hyse/sei fartøy over 28 m', 'status': 'regulert område', 'color': '#577590', 'description': 'Avgrensning for havdeling knyttet til større fartøy.', 'geometry_type': 'esriGeometryPolygon', 'alertable': True, 'local_zone_aliases': ['Havdeling torsk/hyse/sei fartøy over 28 m']},
        {'id': 79, 'name': 'Kongekrabbe regulering', 'status': 'regulert område', 'color': '#0a9396', 'description': 'Regulering av fangst av kongekrabbe.', 'geometry_type': 'esriGeometryPolyline', 'alertable': False, 'local_zone_aliases': ['Kongekrabbe regulering']},
        {'id': 81, 'name': 'Krokbegrensning line', 'status': 'regulert område', 'color': '#118ab2', 'description': 'Linjer som viser krokbegrensninger.', 'geometry_type': 'esriGeometryPolyline', 'alertable': False, 'local_zone_aliases': ['Krokbegrensning line']},
        {'id': 71, 'name': 'Fjordlinjer - kysttorskregulering', 'status': 'regulert område', 'color': '#023047', 'description': 'Fjordlinjer brukt i kysttorskreguleringer.', 'geometry_type': 'esriGeometryPolyline', 'alertable': False, 'local_zone_aliases': ['Fjordlinjer - kysttorskregulering']},
        {'id': 72, 'name': 'Fjordlinjer - seinot', 'status': 'regulert område', 'color': '#219ebc', 'description': 'Fjordlinjer for seinotregulering.', 'geometry_type': 'esriGeometryPolyline', 'alertable': False, 'local_zone_aliases': ['Fjordlinjer - seinot']},
        {'id': 70, 'name': 'Fjordlinjer - kysttorskregulering punkter', 'status': 'regulert område', 'color': '#8ecae6', 'description': 'Punkter knyttet til fjordlinjer for kysttorsk.', 'geometry_type': 'esriGeometryPoint', 'alertable': False, 'local_zone_aliases': ['Fjordlinjer - kysttorskregulering punkter']},
    ]


def _layer_id_candidates(layer_id: int, layer_def: dict[str, Any]) -> set[int]:
    ids: set[int] = set()
    try:
        ids.add(int(layer_id))
    except Exception:
        pass
    for key in ('legacy_ids', 'local_zone_ids', 'portal_layer_ids'):
        for value in list(layer_def.get(key) or []):
            try:
                ids.add(int(value))
            except Exception:
                continue
    return ids


def _layer_name_candidates(layer_def: dict[str, Any]) -> list[str]:
    names: list[str] = []
    for value in [layer_def.get('name'), layer_def.get('layer_name')]:
        value = str(value or '').strip()
        if value and value not in names:
            names.append(value)
    for value in list(layer_def.get('local_zone_aliases') or []):
        value = str(value or '').strip()
        if value and value not in names:
            names.append(value)
    return names


def _token_set(value: str | None) -> set[str]:
    tokens = set()
    for token in re.split(r'[^a-z0-9]+', _ascii_header(value)):
        if not token:
            continue
        if len(token) >= 4 or token.isdigit():
            tokens.add(token)
    return tokens


_GENERIC_LAYER_TOKENS = {
    'omrade', 'omrader', 'områder', 'stengt', 'fredning', 'fredningsomrade', 'forbud', 'forbudsomrade',
    'regulering', 'regulert', 'nullfiske', 'fiskeforbud', 'maksimalmal', 'lokal', 'felt', 'sone', 'soner',
    'fiske', 'fiskeri', 'kyst', 'januar', 'april', 'jmelding', 'melding'
}


def _layer_name_matches(zone_layer_name: str, candidate_names: list[str]) -> bool:
    zone_norm = _ascii_header(zone_layer_name)
    if not zone_norm:
        return False
    zone_tokens = _token_set(zone_layer_name)
    for candidate in candidate_names:
        cand_norm = _ascii_header(candidate)
        if not cand_norm:
            continue
        if zone_norm == cand_norm:
            return True
        if zone_norm in cand_norm or cand_norm in zone_norm:
            return True
        cand_tokens = _token_set(candidate)
        if zone_tokens and cand_tokens:
            overlap = zone_tokens & cand_tokens
            if len(overlap) >= max(2, min(len(zone_tokens), len(cand_tokens)) - 1):
                return True
    return False


def _portal_color_for(status: str, name: str = '') -> str:
    normalized_status = _ascii_header(status)
    normalized_name = _ascii_header(name)
    if 'maksimalmal' in normalized_status or 'maksimalmal' in normalized_name:
        return '#bc4749'
    if normalized_status == 'fredningsomrade':
        return '#f4a261'
    if normalized_status == 'stengt omrade':
        return '#c1121f'
    if normalized_status == 'fiskeriomrade':
        return '#2a9d8f'
    if normalized_status == 'regulert omrade':
        if 'tare' in normalized_name:
            return '#7a9e7e'
        if 'laksefjord' in normalized_name:
            return '#457b9d'
        return '#3d5a80'
    return '#c1121f'


def _portal_status_from(name: str, description: str = '') -> str:
    blob = _ascii_header(' '.join([name or '', description or '']))
    if any(token in blob for token in ['nullfiske', 'stengt', 'forbud', 'saarbare okosystemer', 'tralforbud']):
        return 'stengt område'
    if 'frednings' in blob or 'verneomraade' in blob or 'bevaringsomrade' in blob:
        return 'fredningsområde'
    if 'maksimalmal' in blob:
        return 'maksimalmål område'
    if any(token in blob for token in ['gytefelt', 'gyteomrade', 'oppvekst', 'beiteomrade', 'fiskeplass', 'fiskeplasser', 'rekefelt', 'laassettingsplasser', 'lassettingsplasser', 'skjellforekomst']):
        return 'fiskeriområde'
    if any(token in blob for token in ['havdeling', 'regulering']):
        return 'regulert område'
    return 'regulert område'


def _portal_alertable(geometry_type: str, status: str, name: str) -> bool:
    geom = str(geometry_type or '')
    if geom != 'esriGeometryPolygon':
        return False
    normalized_name = _ascii_header(name)
    if 'apne omrader' in normalized_name or 'tillatt omrade' in normalized_name:
        return False
    return _ascii_header(status) in {'stengt omrade', 'fredningsomrade', 'maksimalmal omrade', 'regulert omrade'}


def _load_portal_catalog_cache() -> list[dict[str, Any]]:
    if not PORTAL_LAYER_CACHE_JSON.exists():
        return []
    try:
        payload = json.loads(PORTAL_LAYER_CACHE_JSON.read_text(encoding='utf-8'))
    except Exception:
        return []
    if not isinstance(payload, list):
        return []
    return _enrich_catalog_rows(payload)


def _write_portal_catalog_cache(rows: list[dict[str, Any]], *, source_kind: str) -> None:
    try:
        PORTAL_LAYER_CACHE_JSON.write_text(json.dumps(rows, ensure_ascii=False), encoding='utf-8')
        PORTAL_LAYER_CACHE_META.write_text(json.dumps({'refreshed_at_unix': time.time(), 'source_kind': source_kind}, ensure_ascii=False), encoding='utf-8')
    except Exception:
        pass


def _enrich_catalog_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    enriched: list[dict[str, Any]] = []
    for row in list(rows or []):
        if not isinstance(row, dict):
            continue
        enriched.append(map_relevance.decorate_catalog_row(row))
    return enriched


def refresh_portal_layer_catalog(force: bool = False, max_age_seconds: int = 6 * 3600) -> list[dict[str, Any]]:
    cached = _load_portal_catalog_cache()
    if not force and cached and _cache_is_fresh(PORTAL_LAYER_CACHE_META, max_age_seconds):
        try:
            meta = json.loads(PORTAL_LAYER_CACHE_META.read_text(encoding='utf-8')) if PORTAL_LAYER_CACHE_META.exists() else {}
        except Exception:
            meta = {}
        if str(meta.get('source_kind') or '').strip().lower().startswith('live'):
            return cached

    fallback_index = {int(item['id']): item for item in _fallback_portal_layer_defs() if item.get('id') is not None}
    try:
        data = _safe_get(f'{YGG_BASE}/layers', params={'f': 'json'}, timeout=PORTAL_REQUEST_TIMEOUT).json()
        layers = list(data.get('layers') or [])
        # Portalvisningen viser alle relevante feature-lag i tjenesten, ikke bare et smalt håndplukket utvalg.
        # For å komme nærmere kartportalen henter vi derfor alle feature-lag, og lar UI-et styre standard synlighet.
        rows: list[dict[str, Any]] = []
        for layer in layers:
            layer_id = layer.get('id')
            if layer_id is None:
                continue
            layer_type = str(layer.get('type') or '')
            if 'Feature Layer' not in layer_type:
                continue
            name = str(layer.get('name') or '').strip()
            if not name:
                continue
            description = str(layer.get('description') or '').replace('\u200b', '').strip()
            geometry_type = str(layer.get('geometryType') or 'esriGeometryPolygon')
            fallback = fallback_index.get(int(layer_id)) or {}
            status = fallback.get('status') or _portal_status_from(name, description)
            row = {
                'id': int(layer_id),
                'name': name,
                'status': status,
                'color': fallback.get('color') or _portal_color_for(status, name),
                'description': fallback.get('description') or description or name,
                'geometry_type': geometry_type,
                'alertable': bool(fallback.get('alertable')) if 'alertable' in fallback else _portal_alertable(geometry_type, status, name),
                'service_url': f'{YGG_BASE}/{int(layer_id)}',
                'source_kind': 'live',
                'legacy_ids': list(fallback.get('legacy_ids') or []),
                'local_zone_aliases': list(fallback.get('local_zone_aliases') or []),
            }
            rows.append(row)
        if rows:
            existing_names = {_ascii_header(item.get('name')) for item in rows if item.get('name')}
            for fallback in _fallback_portal_layer_defs():
                fallback_name = _ascii_header(fallback.get('name'))
                if fallback_name and fallback_name in existing_names:
                    continue
                rows.append(dict(fallback, source_kind='fallback-extra'))
            rows = _enrich_catalog_rows(rows)
            rows.sort(key=lambda item: (_ascii_header(item.get('status')), _ascii_header(item.get('name'))))
            _write_portal_catalog_cache(rows, source_kind='live')
            return rows
    except Exception:
        pass

    if cached:
        return cached
    fallback = _enrich_catalog_rows(_fallback_portal_layer_defs())
    _write_portal_catalog_cache(fallback, source_kind='fallback')
    return fallback


def _merge_catalog_with_fallback(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    fallback_rows = _fallback_portal_layer_defs()
    merged: list[dict[str, Any]] = []
    existing_names: set[str] = set()
    for row in list(rows or []):
        if not isinstance(row, dict):
            continue
        item = dict(row)
        fallback_match = None
        item_name = str(item.get('name') or '').strip()
        for fallback in fallback_rows:
            try:
                if item.get('id') is not None and fallback.get('id') is not None and int(item.get('id')) == int(fallback.get('id')):
                    fallback_match = fallback
                    break
            except Exception:
                pass
            if item_name and _layer_name_matches(item_name, _layer_name_candidates(fallback)):
                fallback_match = fallback
                break
        if fallback_match:
            item.setdefault('status', fallback_match.get('status') or '')
            item.setdefault('color', fallback_match.get('color') or '')
            item.setdefault('description', fallback_match.get('description') or '')
            merged_legacy = list(item.get('legacy_ids') or [])
            for value in list(fallback_match.get('legacy_ids') or []):
                if value not in merged_legacy:
                    merged_legacy.append(value)
            if merged_legacy:
                item['legacy_ids'] = merged_legacy
            merged_aliases = list(item.get('local_zone_aliases') or [])
            for value in _layer_name_candidates(fallback_match):
                if value not in merged_aliases:
                    merged_aliases.append(value)
            if merged_aliases:
                item['local_zone_aliases'] = merged_aliases
        merged.append(item)
        normalized_name = _ascii_header(item.get('name'))
        if normalized_name:
            existing_names.add(normalized_name)
    for fallback in fallback_rows:
        fallback_name = _ascii_header(fallback.get('name'))
        if fallback_name and fallback_name in existing_names:
            continue
        merged.append(dict(fallback))
    return merged


def _portal_selection_score(row: dict[str, Any], *, fishery: str = '', control_type: str = '', gear_type: str = '') -> tuple[int, str]:
    score = 0
    preferred_ids = map_relevance.selection_profile_layer_ids(fishery=fishery, control_type=control_type, gear_type=gear_type)
    try:
        layer_id = int(row.get('id')) if row.get('id') is not None else None
    except Exception:
        layer_id = None
    if fishery or control_type or gear_type:
        if map_relevance.matches_selection(row, fishery=fishery, control_type=control_type, gear_type=gear_type):
            score += 40
        if preferred_ids and layer_id is not None and layer_id in preferred_ids:
            score += 60
    if row.get('alertable'):
        score += 10
    status = str(row.get('status') or '').strip().lower()
    if status == 'stengt område':
        score += 9
    elif status == 'fredningsområde':
        score += 8
    elif status == 'maksimalmål område':
        score += 7
    elif status == 'regulert område':
        score += 4
    return (score, _ascii_header(row.get('name') or ''))


def _portal_display_score(row: dict[str, Any], *, fishery: str = '', control_type: str = '', gear_type: str = '') -> tuple[int, str]:
    score, label = _portal_selection_score(row, fishery=fishery, control_type=control_type, gear_type=gear_type)
    try:
        layer_id = int(row.get('id')) if row.get('id') is not None else None
    except Exception:
        layer_id = None
    if layer_id is not None and layer_id in {
        75, 76, 77, 78, 73, 80, 82, 83, 3, 35, 200, 208,
        94, 85, 91, 92, 32, 139, 140, 25, 26, 33,
    }:
        score += 120
    geometry_type = str(row.get('geometry_type') or '').lower()
    if 'polygon' in geometry_type:
        score += 12
    elif 'polyline' in geometry_type or 'line' in geometry_type:
        score += 6
    return (score, label)


def _sorted_portal_catalog_rows(rows: list[dict[str, Any]], *, fishery: str = '', control_type: str = '', gear_type: str = '') -> list[dict[str, Any]]:
    filtered_rows: list[dict[str, Any]] = []
    for row in list(rows or []):
        if not isinstance(row, dict):
            continue
        enriched = map_relevance.decorate_catalog_row(row)
        if not map_relevance.is_restrictive_law_layer(enriched):
            continue
        if (fishery or control_type or gear_type) and not map_relevance.matches_selection(enriched, fishery=fishery, control_type=control_type, gear_type=gear_type):
            continue
        filtered_rows.append(enriched)
    return sorted(
        filtered_rows,
        key=lambda row: (
            -_portal_display_score(row, fishery=fishery, control_type=control_type, gear_type=gear_type)[0],
            _portal_display_score(row, fishery=fishery, control_type=control_type, gear_type=gear_type)[1],
        ),
    )


def portal_layer_catalog(*, fishery: str = '', control_type: str = '', gear_type: str = '') -> list[dict[str, Any]]:
    rows = _enrich_catalog_rows(_merge_catalog_with_fallback(refresh_portal_layer_catalog(force=False)))
    return _sorted_portal_catalog_rows(rows, fishery=fishery, control_type=control_type, gear_type=gear_type)


def portal_layer_catalog_fast(*, fishery: str = '', control_type: str = '', gear_type: str = '') -> list[dict[str, Any]]:
    """Returner kartkatalog for sidevisning uten a blokkere pa eksterne nettverkskall.

    Bruker sist kjente cache hvis den finnes, ellers lokale fallback-lag. Dette brukes
    pa server-renderte sider som "Ny kontroll", slik at sideaapning ikke star og venter
    pa treg eller utilgjengelig karttjeneste.
    """
    cached = _load_portal_catalog_cache()
    base_rows = cached if cached else _enrich_catalog_rows(_fallback_portal_layer_defs())
    rows = _enrich_catalog_rows(_merge_catalog_with_fallback(base_rows))
    return _sorted_portal_catalog_rows(rows, fishery=fishery, control_type=control_type, gear_type=gear_type)


def _portal_layer_client_row(row: dict[str, Any]) -> dict[str, Any]:
    def _as_str_list(value: Any) -> list[str]:
        return [str(item) for item in list(value or []) if str(item or '').strip()]

    legacy_ids: list[int] = []
    for item in list(row.get('legacy_ids') or []):
        try:
            legacy_ids.append(int(item))
        except Exception:
            continue

    payload: dict[str, Any] = {
        'id': int(row.get('id')) if row.get('id') is not None else None,
        'name': str(row.get('name') or ''),
        'status': str(row.get('status') or ''),
        'color': str(row.get('color') or ''),
        'description': str(row.get('description') or ''),
        'geometry_type': str(row.get('geometry_type') or ''),
        'legacy_ids': legacy_ids,
        'fishery_tags': _as_str_list(row.get('fishery_tags')),
        'gear_tags': _as_str_list(row.get('gear_tags')),
        'control_tags': _as_str_list(row.get('control_tags')),
        'selection_summary': str(row.get('selection_summary') or ''),
        'panel_group': str(row.get('panel_group') or ''),
        'panel_group_key': str(row.get('panel_group_key') or ''),
        'panel_group_order': int(row.get('panel_group_order') or 999),
        'default_visible': bool(row.get('default_visible', True)),
        'service_url': str(row.get('service_url') or ''),
    }
    return payload


def portal_layer_catalog_page_payload(*, fishery: str = '', control_type: str = '', gear_type: str = '') -> list[dict[str, Any]]:
    rows = portal_layer_catalog_fast(fishery=fishery, control_type=control_type, gear_type=gear_type)
    return [_portal_layer_client_row(row) for row in rows if isinstance(row, dict)]


def _portal_layer_defs() -> list[dict[str, Any]]:
    rows = portal_layer_catalog()
    return rows or _fallback_portal_layer_defs()


def _portal_layer_def(layer_id: int) -> dict[str, Any] | None:
    for item in _portal_layer_defs():
        item_id = item.get('id')
        if item_id is None:
            continue
        try:
            if int(layer_id) in _layer_id_candidates(int(item_id), item):
                return item
        except Exception:
            continue
    return None


def _resolve_portal_catalog_rows(layer_ids: list[int] | None = None) -> list[dict[str, Any]]:
    rows = [row for row in portal_layer_catalog() if row.get('id') is not None]
    requested = {int(value) for value in (layer_ids or []) if str(value).strip()} if layer_ids else set()
    if not requested:
        return rows
    resolved: list[dict[str, Any]] = []
    seen: set[int] = set()
    for row in rows:
        try:
            row_id = int(row.get('id'))
        except Exception:
            continue
        if not (_layer_id_candidates(row_id, row) & requested):
            continue
        if row_id in seen:
            continue
        seen.add(row_id)
        resolved.append(row)
    return resolved


def _iter_coords(value: Any):
    if isinstance(value, (list, tuple)):
        if len(value) >= 2 and isinstance(value[0], (int, float)) and isinstance(value[1], (int, float)):
            yield float(value[0]), float(value[1])
            return
        for item in value:
            yield from _iter_coords(item)


def _feature_bbox(feature: dict[str, Any]) -> tuple[float, float, float, float] | None:
    geometry = (feature or {}).get('geometry') or {}
    coords = list(_iter_coords(geometry.get('coordinates')))
    if not coords:
        return None
    xs = [coord[0] for coord in coords]
    ys = [coord[1] for coord in coords]
    return (min(xs), min(ys), max(xs), max(ys))


def _bbox_intersects(a: tuple[float, float, float, float], b: tuple[float, float, float, float]) -> bool:
    return not (a[2] < b[0] or a[0] > b[2] or a[3] < b[1] or a[1] > b[3])


def _filter_feature_collection_by_bbox(payload: dict[str, Any], bbox: tuple[float, float, float, float]) -> dict[str, Any]:
    if not bbox:
        return payload
    filtered: list[dict[str, Any]] = []
    for feature in list((payload or {}).get('features') or []):
        fb = _feature_bbox(feature)
        if fb is None or _bbox_intersects(fb, bbox):
            filtered.append(feature)
    return {'type': 'FeatureCollection', 'features': filtered}


def _portal_bbox_cache_key(layer_id: int, bbox: tuple[float, float, float, float] | None) -> str | None:
    if not bbox:
        return None
    rounded = tuple(round(float(value), 3) for value in bbox)
    return f'{int(layer_id)}:{rounded[0]}:{rounded[1]}:{rounded[2]}:{rounded[3]}'


def _portal_bbox_cache_get(cache_key: str | None) -> dict[str, Any] | None:
    if not cache_key:
        return None
    with _BBOX_CACHE_LOCK:
        entry = _BBOX_CACHE.get(cache_key)
        if not entry:
            return None
        stored_at, payload = entry
        if (time.time() - stored_at) > PORTAL_BBOX_CACHE_TTL:
            _BBOX_CACHE.pop(cache_key, None)
            return None
        return payload


def _portal_bbox_cache_put(cache_key: str | None, payload: dict[str, Any]) -> None:
    if not cache_key:
        return
    with _BBOX_CACHE_LOCK:
        _BBOX_CACHE[cache_key] = (time.time(), payload)
        if len(_BBOX_CACHE) > 512:
            for key, _ in sorted(_BBOX_CACHE.items(), key=lambda item: item[1][0])[:128]:
                _BBOX_CACHE.pop(key, None)


def _merge_feature_collections(*payloads: dict[str, Any] | None) -> dict[str, Any]:
    features: list[dict[str, Any]] = []
    seen: set[str] = set()
    for payload in payloads:
        for feature in list((payload or {}).get('features') or []):
            props = feature.get('properties') or {}
            geom = feature.get('geometry') or {}
            key = json.dumps([props.get('layer_id'), props.get('navn') or props.get('omraade') or props.get('name'), geom], ensure_ascii=False, sort_keys=True)
            if key in seen:
                continue
            seen.add(key)
            features.append(feature)
    return {'type': 'FeatureCollection', 'features': features}


def fetch_portal_geojson(layer_id: int, *, force: bool = False, max_age_seconds: int = 6 * 3600, bbox: tuple[float, float, float, float] | None = None) -> dict[str, Any]:
    cache_path = PORTAL_LAYER_CACHE_DIR / f'layer_{layer_id}.geojson'
    meta_path = PORTAL_LAYER_CACHE_DIR / f'layer_{layer_id}.meta.json'
    local_fallback = _local_zone_geojson_for_layer(layer_id)
    cached = _portal_cache_payload(cache_path)
    cache_fresh = _cache_is_fresh(meta_path, max_age_seconds)
    bbox_cache_key = _portal_bbox_cache_key(layer_id, bbox)

    if not force:
        cached_bbox = _portal_bbox_cache_get(bbox_cache_key)
        if cached_bbox is not None:
            return cached_bbox

    local_view = _filter_feature_collection_by_bbox(local_fallback, bbox) if bbox else local_fallback
    cached_view = _filter_feature_collection_by_bbox(cached, bbox) if bbox else cached

    if bbox and LIVE_ENABLED:
        params = {
            'where': '1=1',
            'outFields': '*',
            'returnGeometry': 'true',
            'f': 'geojson',
            'outSR': '4326',
            'geometry': ','.join(str(part) for part in bbox),
            'geometryType': 'esriGeometryEnvelope',
            'inSR': '4326',
            'spatialRel': 'esriSpatialRelIntersects',
        }
        try:
            data = _safe_get(f'{YGG_BASE}/{layer_id}/query', params=params, timeout=PORTAL_REQUEST_TIMEOUT).json()
            normalized = normalize_geojson(data)
            merged_live = _merge_feature_collections(normalized, local_view)
            if merged_live.get('features'):
                if normalized.get('features'):
                    _write_portal_cache(cache_path, meta_path, normalized, source_kind='live')
                _portal_bbox_cache_put(bbox_cache_key, merged_live)
                return merged_live
        except Exception:
            if _portal_cache_has_features(cached_view):
                merged_cached = _merge_feature_collections(cached_view, local_view)
                _portal_bbox_cache_put(bbox_cache_key, merged_cached)
                return merged_cached
            if _portal_cache_has_features(local_view):
                _portal_bbox_cache_put(bbox_cache_key, local_view)
                return local_view

    if not force and cache_fresh and _portal_cache_has_features(cached_view):
        merged_cached = _merge_feature_collections(cached_view, local_view)
        _portal_bbox_cache_put(bbox_cache_key, merged_cached)
        return merged_cached

    # Mobile maps request small bounding boxes repeatedly while the user pans/zooms.
    # Do not fall back to downloading a full portal layer for a bbox request; that
    # can be several megabytes and makes the app feel frozen on mobile networks.
    if bbox:
        if _portal_cache_has_features(cached_view):
            merged_cached = _merge_feature_collections(cached_view, local_view)
            _portal_bbox_cache_put(bbox_cache_key, merged_cached)
            return merged_cached
        if _portal_cache_has_features(local_view):
            _portal_bbox_cache_put(bbox_cache_key, local_view)
            return local_view
        empty = {'type': 'FeatureCollection', 'features': []}
        _portal_bbox_cache_put(bbox_cache_key, empty)
        return empty

    if LIVE_ENABLED:
        params = {
            'where': '1=1',
            'outFields': '*',
            'returnGeometry': 'true',
            'f': 'geojson',
            'outSR': '4326',
        }
        try:
            data = _safe_get(f'{YGG_BASE}/{layer_id}/query', params=params, timeout=PORTAL_REQUEST_TIMEOUT).json()
            normalized = normalize_geojson(data)
            if _portal_cache_has_features(normalized):
                _write_portal_cache(cache_path, meta_path, normalized, source_kind='live')
                filtered_live = _filter_feature_collection_by_bbox(normalized, bbox) if bbox else normalized
                merged_live = _merge_feature_collections(filtered_live, local_view)
                _portal_bbox_cache_put(bbox_cache_key, merged_live)
                return merged_live
        except Exception:
            pass

    if _portal_cache_has_features(cached_view):
        merged_cached = _merge_feature_collections(cached_view, local_view)
        _portal_bbox_cache_put(bbox_cache_key, merged_cached)
        return merged_cached

    if _portal_cache_has_features(local_view):
        _write_portal_cache(cache_path, meta_path, local_fallback, source_kind='fallback')
        _portal_bbox_cache_put(bbox_cache_key, local_view)
        return local_view

    empty = {'type': 'FeatureCollection', 'features': []}
    _write_portal_cache(cache_path, meta_path, empty, source_kind='empty')
    _portal_bbox_cache_put(bbox_cache_key, empty)
    return empty


def normalize_geojson(data: dict[str, Any] | None) -> dict[str, Any]:
    if not isinstance(data, dict) or data.get('type') != 'FeatureCollection':
        return {'type': 'FeatureCollection', 'features': []}
    return {'type': 'FeatureCollection', 'features': list(data.get('features') or [])}




def _portal_point_cache_key(layer_id: int, lat: float, lng: float, *, geometry_type: str = '') -> str:
    return f"{int(layer_id)}:{round(float(lat), 5)}:{round(float(lng), 5)}:{str(geometry_type or '').strip().lower()}"


def _portal_point_cache_get(cache_key: str) -> list[dict[str, Any]] | None:
    with _PORTAL_POINT_CACHE_LOCK:
        item = _PORTAL_POINT_CACHE.get(cache_key)
        if not item:
            return None
        stored_at, payload = item
        if (time.time() - stored_at) > PORTAL_POINT_CACHE_TTL:
            _PORTAL_POINT_CACHE.pop(cache_key, None)
            return None
        return list(payload or [])


def _portal_point_cache_put(cache_key: str, payload: list[dict[str, Any]]) -> None:
    with _PORTAL_POINT_CACHE_LOCK:
        _PORTAL_POINT_CACHE[cache_key] = (time.time(), list(payload or []))
        if len(_PORTAL_POINT_CACHE) > 1024:
            for key, _ in sorted(_PORTAL_POINT_CACHE.items(), key=lambda item: item[1][0])[:256]:
                _PORTAL_POINT_CACHE.pop(key, None)

def _ygg_query_point(layer_id: int, lat: float, lng: float, *, geometry_type: str = 'esriGeometryPolygon') -> list[dict[str, Any]]:
    if str(geometry_type or '') != 'esriGeometryPolygon':
        return []
    cache_key = _portal_point_cache_key(layer_id, lat, lng, geometry_type=geometry_type)
    cached = _portal_point_cache_get(cache_key)
    if cached is not None:
        return cached
    params = {
        'f': 'geojson',
        'geometry': f'{lng},{lat}',
        'geometryType': 'esriGeometryPoint',
        'inSR': '4326',
        'spatialRel': 'esriSpatialRelIntersects',
        'returnGeometry': 'true',
        'outFields': '*',
    }
    data = _safe_get(f'{YGG_BASE}/{layer_id}/query', params=params, timeout=ZONE_POINT_QUERY_TIMEOUT).json()
    payload = list(data.get('features') or [])
    _portal_point_cache_put(cache_key, payload)
    return payload




def _portal_identify_point(layer_id: int, lat: float, lng: float) -> list[dict[str, Any]]:
    cache_key = _portal_point_cache_key(layer_id, lat, lng, geometry_type='identify')
    cached = _portal_point_cache_get(cache_key)
    if cached is not None:
        return cached
    params = {
        'f': 'json',
        'geometry': f'{lng},{lat}',
        'geometryType': 'esriGeometryPoint',
        'inSR': '4326',
        'spatialRel': 'esriSpatialRelIntersects',
        'returnGeometry': 'false',
        'outFields': '*',
    }
    try:
        data = _safe_get(f'{YGG_BASE}/{layer_id}/query', params=params, timeout=ZONE_POINT_QUERY_TIMEOUT).json()
    except Exception:
        return []
    payload = list(data.get('features') or [])
    _portal_point_cache_put(cache_key, payload)
    return payload


def identify_portal_point(lat: float, lng: float, layer_ids: list[int] | None = None) -> dict[str, Any]:
    rows = _resolve_portal_catalog_rows(layer_ids)
    priorities = {'stengt område': 4, 'fredningsområde': 3, 'maksimalmål område': 2, 'regulert område': 1, 'fiskeriområde': 0}
    hits: list[dict[str, Any]] = []
    seen: set[str] = set()

    for layer in rows:
        layer_id = layer.get('id')
        if layer_id is None:
            continue
        # live source
        for feature in _portal_identify_point(int(layer_id), lat, lng):
            name = _feature_attr(feature, 'navn', 'omraade', 'område', 'name', 'kat_ordning_text', 'regelverk', 'forskrift') or layer.get('name') or 'Område'
            desc = _feature_attr(feature, 'info', 'beskrivelse', 'informasjon', 'stengt_text', 'regler', 'forskrift') or layer.get('description') or ''
            url = _feature_attr(feature, 'url', 'url_lovtekst', 'lenke') or MAP_PORTAL_URL
            key = f"{layer_id}|{name}|{layer.get('status') or ''}|live"
            if key in seen:
                continue
            seen.add(key)
            hits.append({
                'layer_id': int(layer_id),
                'layer': layer.get('name') or '',
                'status': layer.get('status') or '',
                'name': name,
                'description': desc,
                'url': url,
                'source': 'Fiskeridirektoratets kartdatabase',
                'database': 'Fiskeridirektoratets kartdatabase',
            })
        # local reserve fallback
        layer_def = _portal_layer_def(int(layer_id)) or layer
        for zone in area.ZONES:
            if not _local_zone_matches_layer(zone, int(layer_id), layer_def):
                continue
            polygon = zone.get('polygon') or []
            if polygon and area.point_in_polygon(lat, lng, polygon):
                name = zone.get('name') or layer.get('name') or 'Område'
                desc = zone.get('notes') or layer.get('description') or ''
                url = zone.get('url') or MAP_PORTAL_URL
                key = f"{layer_id}|{name}|{layer.get('status') or zone.get('status') or ''}|local"
                if key in seen:
                    continue
                seen.add(key)
                hits.append({
                    'layer_id': int(layer_id),
                    'layer': layer.get('name') or '',
                    'status': zone.get('status') or layer.get('status') or '',
                    'name': name,
                    'description': desc,
                    'url': url,
                    'source': zone.get('source') or 'Lokal reserveflate i appen',
                    'database': zone.get('source') or 'Lokal reserveflate i appen',
                })
    hits.sort(key=lambda item: (-priorities.get(str(item.get('status') or '').lower(), 0), str(item.get('name') or '')))
    return {
        'match': bool(hits),
        'lat': lat,
        'lng': lng,
        'hits': hits,
    }





def _portal_bundle_cache_key(layer_ids: list[int] | None, bbox: tuple[float, float, float, float] | None) -> str:
    ids = ','.join(str(int(value)) for value in sorted({int(value) for value in (layer_ids or [])}))
    bbox_key = ''
    if bbox:
        bbox_key = ','.join(f'{float(value):.3f}' for value in bbox)
    return f'{ids}|{bbox_key}'


def _portal_bundle_cache_get(cache_key: str, max_age_seconds: float) -> dict[str, Any] | None:
    with _PORTAL_BUNDLE_CACHE_LOCK:
        item = _PORTAL_BUNDLE_CACHE.get(cache_key)
        if not item:
            return None
        stored_at, payload = item
        if (time.time() - stored_at) > max_age_seconds:
            _PORTAL_BUNDLE_CACHE.pop(cache_key, None)
            return None
        return dict(payload)


def _portal_bundle_cache_put(cache_key: str, payload: dict[str, Any]) -> None:
    with _PORTAL_BUNDLE_CACHE_LOCK:
        _PORTAL_BUNDLE_CACHE[cache_key] = (time.time(), dict(payload))
        if len(_PORTAL_BUNDLE_CACHE) > 96:
            for key, _ in sorted(_PORTAL_BUNDLE_CACHE.items(), key=lambda item: item[1][0])[:24]:
                _PORTAL_BUNDLE_CACHE.pop(key, None)


def _compact_portal_properties(raw: dict[str, Any], layer: dict[str, Any]) -> dict[str, Any]:
    allowed = (
        'navn', 'omraade', 'område', 'name', 'kat_ordning_text',
        'info', 'beskrivelse', 'informasjon', 'stengt_text',
        'omraade_stengt_text', 'vurderes_aapnet_text', 'regler',
        'regelverk', 'forskrift', 'url', 'url_lovtekst', 'lenke'
    )
    props: dict[str, Any] = {}
    source = raw or {}
    for key in allowed:
        value = source.get(key)
        if value not in {None, ''}:
            props[key] = value
    props['__layer_id'] = int(layer.get('id') or 0)
    props['__layer_name'] = layer.get('name') or ''
    props['__layer_status'] = layer.get('status') or ''
    props['__layer_color'] = layer.get('color') or '#c1121f'
    props['__layer_description'] = layer.get('description') or ''
    props['__layer_url'] = layer.get('service_url') or MAP_PORTAL_URL
    props['__layer_source'] = 'Fiskeridirektoratets kartdatabase'
    return props

def _annotate_portal_feature(feature: dict[str, Any], layer: dict[str, Any]) -> dict[str, Any]:
    enriched = {'type': 'Feature', 'geometry': (feature or {}).get('geometry')}
    raw_props = dict((feature or {}).get('properties') or (feature or {}).get('attributes') or {})
    enriched['properties'] = _compact_portal_properties(raw_props, layer)
    return enriched


def fetch_portal_bundle(*, layer_ids: list[int] | None = None, bbox: tuple[float, float, float, float] | None = None, max_age_seconds: int = 6 * 3600) -> dict[str, Any]:
    requested_ids = sorted({int(value) for value in (layer_ids or []) if str(value).strip()})
    rows = _resolve_portal_catalog_rows(requested_ids)
    rows = [row for row in rows if row.get('id') is not None]
    canonical_ids = [int(row.get('id')) for row in rows]
    bundle_cache_key = _portal_bundle_cache_key(canonical_ids or requested_ids or [int(row.get('id')) for row in rows], bbox)
    cached_bundle = _portal_bundle_cache_get(bundle_cache_key, min(max_age_seconds, PORTAL_BUNDLE_CACHE_TTL))
    if cached_bundle is not None:
        return cached_bundle

    features: list[dict[str, Any]] = []
    active_layers: list[dict[str, Any]] = []
    seen: set[str] = set()
    max_workers = max(2, min(6, int(os.getenv('KV_MAP_BUNDLE_WORKERS', '4') or '4')))

    def _load(row: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
        payload = fetch_portal_geojson(int(row['id']), bbox=bbox, max_age_seconds=max_age_seconds)
        return row, normalize_geojson(payload)

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = [executor.submit(_load, row) for row in rows]
        for future in as_completed(futures):
            try:
                row, payload = future.result()
            except Exception:
                continue
            normalized = normalize_geojson(payload)
            if not normalized.get('features'):
                continue
            active_layers.append(row)
            for feature in normalized.get('features') or []:
                annotated = _annotate_portal_feature(feature, row)
                props = annotated.get('properties') or {}
                geom = annotated.get('geometry') or {}
                key = json.dumps([props.get('__layer_id'), props.get('navn') or props.get('omraade') or props.get('område') or props.get('name'), geom], ensure_ascii=False, sort_keys=True)
                if key in seen:
                    continue
                seen.add(key)
                features.append(annotated)

    active_layers.sort(key=lambda item: (str(item.get('status') or ''), str(item.get('name') or '')))
    payload = {
        'type': 'FeatureCollection',
        'features': features,
        'layers': active_layers,
        'bbox': list(bbox) if bbox else None,
        'portal_url': MAP_PORTAL_URL,
        'mapserver_url': YGG_BASE,
    }
    _portal_bundle_cache_put(bundle_cache_key, payload)
    return payload

def classify_position_live(lat: float, lng: float, species: str = '', gear_type: str = '', control_type: str = '') -> dict[str, Any]:
    """Fast point check against restrictive law/regulation layers."""
    hits: list[dict[str, Any]] = []
    highest = {
        'rank': 0,
        'status': 'ingen treff',
        'name': '',
        'notes': 'Ingen treff i Fiskeridirektoratets regulerings- og vernelag for denne posisjonen.',
    }
    priorities = {'stengt område': 4, 'fredningsområde': 3, 'maksimalmål område': 2, 'regulert område': 1, 'nullfiskeområde': 4}
    point_seen: set[str] = set()

    layers_to_check = portal_layer_catalog(fishery=species, control_type=control_type, gear_type=gear_type)
    if not layers_to_check:
        layers_to_check = [
            layer for layer in _portal_layer_defs()
            if map_relevance.is_restrictive_law_layer(map_relevance.decorate_catalog_row(layer))
            and map_relevance.matches_selection(map_relevance.decorate_catalog_row(layer), fishery=species, control_type=control_type, gear_type=gear_type)
        ]
    layers_to_check = [layer for layer in layers_to_check if layer.get('alertable')][:ZONE_CHECK_MAX_LIVE_LAYERS]

    def _hits_for_layer(layer: dict[str, Any]) -> list[dict[str, Any]]:
        try:
            features = _ygg_query_point(int(layer['id']), lat, lng, geometry_type=layer.get('geometry_type') or 'esriGeometryPolygon')
        except Exception:
            return []
        rows: list[dict[str, Any]] = []
        for feature in features or []:
            name = _feature_attr(feature, 'navn', 'omraade', 'område', 'kat_ordning_text', 'regelverk', 'forskrift') or layer.get('name') or 'Karttreff'
            notes = _feature_attr(feature, 'info', 'beskrivelse', 'stengt_text', 'informasjon', 'regelverk', 'regler', 'forskrift') or layer.get('description') or layer.get('name') or ''
            url = _feature_attr(feature, 'url', 'url_lovtekst', 'lenke') or MAP_PORTAL_URL
            rows.append({
                'layer': layer.get('name') or '',
                'status': layer.get('status') or 'regulert område',
                'name': name,
                'notes': notes,
                'url': url,
                'source': 'Fiskeridirektoratet kartportal',
                'layer_id': layer.get('id'),
                'layer_ids': [layer.get('id')] if layer.get('id') is not None else [],
                'feature': _annotate_portal_feature(feature, layer),
            })
        return rows

    if layers_to_check:
        worker_count = max(1, min(ZONE_CHECK_WORKERS, len(layers_to_check)))
        executor = ThreadPoolExecutor(max_workers=worker_count)
        futures = [executor.submit(_hits_for_layer, layer) for layer in layers_to_check]
        try:
            for future in as_completed(futures, timeout=ZONE_CHECK_TOTAL_TIMEOUT):
                try:
                    layer_hits = future.result(timeout=0.05)
                except Exception:
                    continue
                for hit in layer_hits:
                    dedupe_key = json.dumps([hit.get('layer_id'), hit.get('name'), hit.get('notes')], ensure_ascii=False, sort_keys=True)
                    if dedupe_key in point_seen:
                        continue
                    point_seen.add(dedupe_key)
                    hits.append(hit)
                    rank = priorities.get(hit.get('status') or '', 0)
                    if rank > highest['rank']:
                        highest = {'rank': rank, 'status': hit.get('status') or '', 'name': hit.get('name') or '', 'notes': hit.get('notes') or ''}
        except FuturesTimeoutError:
            pass
        finally:
            for future in futures:
                if not future.done():
                    future.cancel()
            executor.shutdown(wait=False, cancel_futures=True)

    hits.sort(key=lambda item: (-priorities.get(item.get('status') or '', 0), _ascii_header(item.get('name'))))
    return {
        'match': bool(hits),
        'status': highest['status'],
        'name': highest['name'],
        'source': 'Fiskeridirektoratet kartportal',
        'notes': highest['notes'],
        'hits': hits,
        'lat': lat,
        'lng': lng,
        'portal_url': MAP_PORTAL_URL,
    }

