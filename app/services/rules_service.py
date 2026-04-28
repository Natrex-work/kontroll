from __future__ import annotations

import copy
import os
import time
from typing import Any

from .. import area, live_sources, rules
from .case_service import merge_source_rows

_ZONE_STATUS_CACHE: dict[tuple[float, float, str, str, str], tuple[float, dict[str, Any]]] = {}
_ZONE_STATUS_CACHE_SECONDS = max(15.0, min(600.0, float(os.getenv('KV_ZONE_STATUS_CACHE_SECONDS', '90') or '90')))
_REVERSE_GEOCODE_ALWAYS = os.getenv('KV_REVERSE_GEOCODE_ALWAYS', '0').lower() in {'1', 'true', 'yes', 'on'}

_RULE_BUNDLE_CACHE: dict[tuple[str, str, str, str, str, str, float | None, float | None], tuple[float, dict[str, Any]]] = {}
_RULE_BUNDLE_CACHE_SECONDS = 300.0


def _zone_cache_key(lat: float, lng: float, species: str = '', gear_type: str = '', control_type: str = '') -> tuple[float, float, str, str, str]:
    return (round(float(lat), 4), round(float(lng), 4), str(species or '').strip().lower(), str(gear_type or '').strip().lower(), str(control_type or '').strip().lower())


def _zone_cache_get(lat: float, lng: float, species: str = '', gear_type: str = '', control_type: str = '') -> dict[str, Any] | None:
    key = _zone_cache_key(lat, lng, species=species, gear_type=gear_type, control_type=control_type)
    item = _ZONE_STATUS_CACHE.get(key)
    if not item:
        return None
    ts, payload = item
    if (time.time() - ts) > _ZONE_STATUS_CACHE_SECONDS:
        _ZONE_STATUS_CACHE.pop(key, None)
        return None
    return copy.deepcopy(payload)


def _zone_cache_put(lat: float, lng: float, payload: dict[str, Any], species: str = '', gear_type: str = '', control_type: str = '') -> None:
    key = _zone_cache_key(lat, lng, species=species, gear_type=gear_type, control_type=control_type)
    _ZONE_STATUS_CACHE[key] = (time.time(), copy.deepcopy(payload))
    if len(_ZONE_STATUS_CACHE) > 256:
        for stale_key, _ in sorted(_ZONE_STATUS_CACHE.items(), key=lambda item: item[1][0])[:64]:
            _ZONE_STATUS_CACHE.pop(stale_key, None)


def _rule_bundle_cache_key(*, control_type: str, species: str, gear_type: str, area_status: str = '', area_name: str = '', area_notes: str = '', lat: float | None = None, lng: float | None = None) -> tuple[str, str, str, str, str, str, float | None, float | None]:
    return (
        str(control_type or '').strip().lower(),
        str(species or '').strip().lower(),
        str(gear_type or '').strip().lower(),
        str(area_status or '').strip().lower(),
        str(area_name or '').strip().lower(),
        str(area_notes or '').strip().lower(),
        round(float(lat), 4) if lat is not None else None,
        round(float(lng), 4) if lng is not None else None,
    )


def _rule_bundle_cache_get(*, control_type: str, species: str, gear_type: str, area_status: str = '', area_name: str = '', area_notes: str = '', lat: float | None = None, lng: float | None = None) -> dict[str, Any] | None:
    key = _rule_bundle_cache_key(control_type=control_type, species=species, gear_type=gear_type, area_status=area_status, area_name=area_name, area_notes=area_notes, lat=lat, lng=lng)
    item = _RULE_BUNDLE_CACHE.get(key)
    if not item:
        return None
    ts, payload = item
    if (time.time() - ts) > _RULE_BUNDLE_CACHE_SECONDS:
        _RULE_BUNDLE_CACHE.pop(key, None)
        return None
    return copy.deepcopy(payload)


def _rule_bundle_cache_put(payload: dict[str, Any], *, control_type: str, species: str, gear_type: str, area_status: str = '', area_name: str = '', area_notes: str = '', lat: float | None = None, lng: float | None = None) -> None:
    key = _rule_bundle_cache_key(control_type=control_type, species=species, gear_type=gear_type, area_status=area_status, area_name=area_name, area_notes=area_notes, lat=lat, lng=lng)
    _RULE_BUNDLE_CACHE[key] = (time.time(), copy.deepcopy(payload))
    if len(_RULE_BUNDLE_CACHE) > 256:
        for stale_key, _ in sorted(_RULE_BUNDLE_CACHE.items(), key=lambda item: item[1][0])[:64]:
            _RULE_BUNDLE_CACHE.pop(stale_key, None)


def get_rule_bundle_with_live_sources(*, control_type: str, species: str, gear_type: str, area_status: str = '', control_date: str = '', area_name: str = '', area_notes: str = '', lat: float | None = None, lng: float | None = None) -> dict[str, Any]:
    cached_bundle = _rule_bundle_cache_get(control_type=control_type, species=species, gear_type=gear_type, area_status=area_status, area_name=area_name, area_notes=area_notes, lat=lat, lng=lng)
    if cached_bundle is not None:
        return cached_bundle
    bundle = rules.get_rule_bundle(control_type, species, gear_type, area_status=area_status, control_date=control_date, area_name=area_name, area_notes=area_notes, lat=lat, lng=lng)
    live_sources_rows: list[dict[str, Any]] = []
    diagnostics: list[str] = []
    try:
        live_bundle = live_sources.compose_live_sources(control_type=control_type, species=species, gear_type=gear_type, lat=lat, lng=lng, area_status=area_status)
        live_sources_rows = live_bundle.get('sources') or []
        diagnostics = [d for d in live_bundle.get('diagnostics') or [] if str(d).strip()]
    except Exception as exc:
        diagnostics = [str(exc)]
    bundle['sources'] = merge_source_rows(bundle.get('sources') or [], live_sources_rows)
    if diagnostics:
        desc = str(bundle.get('description') or '').strip()
        bundle['description'] = (desc + ' Live-status: ' + ' | '.join(diagnostics)).strip()
    _rule_bundle_cache_put(bundle, control_type=control_type, species=species, gear_type=gear_type, area_status=area_status, area_name=area_name, area_notes=area_notes, lat=lat, lng=lng)
    return bundle


def check_zone_status(lat: float, lng: float, species: str = '', gear_type: str = '', control_type: str = '') -> dict[str, Any]:
    cached = _zone_cache_get(lat, lng, species=species, gear_type=gear_type, control_type=control_type)
    if cached is not None:
        return cached
    result = area.classify_position(lat, lng, species=species, gear_type=gear_type, control_type=control_type)
    local_is_fallback = str(result.get('source_kind') or '').lower() == 'fallback'
    try:
        live_result = live_sources.classify_position_live(lat, lng, species=species, gear_type=gear_type, control_type=control_type)
        if live_result.get('match'):
            result = {
                'match': True,
                'status': live_result.get('status') or 'regulert område',
                'name': live_result.get('name') or '',
                'source': live_result.get('source') or result.get('source'),
                'source_kind': 'live',
                'notes': live_result.get('notes') or '',
                'hits': live_result.get('hits') or [],
                'nearest_place': result.get('nearest_place'),
                'distance_to_place_km': result.get('distance_to_place_km'),
            }
        elif local_is_fallback and result.get('match'):
            result = dict(result)
            result['notes'] = (str(result.get('notes') or '').strip() + ' Lokalt reservekart er brukt fordi live-karttjenesten ikke ga treff for denne posisjonen.').strip()
        elif local_is_fallback:
            result = {
                'match': False,
                'status': 'ingen treff',
                'name': '',
                'source': live_result.get('source') or 'Fiskeridirektoratet kartportal',
                'source_kind': 'live',
                'notes': 'Ingen treff i kartlagene for fredningsområder, stengte områder eller tilsvarende regulerte områder.',
                'hits': [],
                'nearest_place': result.get('nearest_place'),
                'distance_to_place_km': result.get('distance_to_place_km'),
            }
        elif not result.get('match'):
            result = {
                'match': False,
                'status': 'ingen treff',
                'name': '',
                'source': live_result.get('source') or 'Fiskeridirektoratet kartportal',
                'source_kind': 'live',
                'notes': 'Ingen treff i kartlagene for fredningsområder, stengte områder eller tilsvarende regulerte områder.',
                'hits': [],
                'nearest_place': result.get('nearest_place'),
                'distance_to_place_km': result.get('distance_to_place_km'),
            }
    except Exception as exc:
        if not result.get('match'):
            result = {
                'match': False,
                'status': 'ingen treff',
                'name': '',
                'source': 'Fiskeridirektoratet kartportal',
                'source_kind': 'fallback' if local_is_fallback else result.get('source_kind') or 'unknown',
                'notes': 'Ingen treff i kartlagene for fredningsområder, stengte områder eller tilsvarende regulerte områder.',
                'hits': [],
                'nearest_place': result.get('nearest_place'),
                'distance_to_place_km': result.get('distance_to_place_km'),
            }
        result['debug_live_error'] = str(exc)
    # Den lokale stedslisten er bare reserve. For rapporttekst skal nærmeste
    # kommune/sted helst komme fra reverse geocoding når lokal treffavstand er grov.
    local_distance = result.get('distance_to_place_km')
    should_reverse = _REVERSE_GEOCODE_ALWAYS or not result.get('nearest_place')
    try:
        should_reverse = should_reverse or (local_distance is not None and float(local_distance) > 2.0)
    except Exception:
        should_reverse = True
    if should_reverse:
        try:
            reverse = live_sources.reverse_geocode_live(lat, lng)
            if reverse.get('name'):
                result['nearest_place'] = reverse.get('name')
            municipality = reverse.get('municipality') or ''
            locality = reverse.get('locality') or reverse.get('name') or ''
            label_parts = []
            for value in [locality, municipality]:
                value = str(value or '').strip()
                if value and value not in label_parts:
                    label_parts.append(value)
            if label_parts:
                result['location_name'] = ', '.join(label_parts)
            elif reverse.get('location_label'):
                result['location_name'] = reverse.get('location_label')
            elif not result.get('location_name'):
                result['location_name'] = result.get('nearest_place') or ''
            if municipality:
                result['municipality'] = municipality
            result['reverse_geocode'] = reverse
        except Exception:
            if not result.get('location_name'):
                result['location_name'] = result.get('nearest_place') or ''
            result['reverse_geocode'] = {'found': False}
    else:
        if not result.get('location_name'):
            result['location_name'] = result.get('nearest_place') or ''
        result['reverse_geocode'] = {'found': False, 'skipped': True, 'reason': 'local_nearest_place_available'}
    if result.get('match'):
        rec = rules.recommend_area_violation(area_status=result.get('status') or '', area_name=result.get('name') or '', species=species, gear_type=gear_type, notes=result.get('notes') or '')
        if rec:
            result['recommended_violation'] = rec
        hits = result.get('hits')
        if isinstance(hits, list):
            for hit in hits:
                if not isinstance(hit, dict):
                    continue
                hit_rec = rules.recommend_area_violation(
                    area_status=hit.get('status') or result.get('status') or '',
                    area_name=hit.get('name') or hit.get('layer') or result.get('name') or '',
                    species=species,
                    gear_type=gear_type,
                    notes=hit.get('notes') or hit.get('description') or hit.get('summary') or result.get('notes') or '',
                )
                if hit_rec:
                    hit['recommended_violation'] = hit_rec
    _zone_cache_put(lat, lng, result, species=species, gear_type=gear_type, control_type=control_type)
    return result
