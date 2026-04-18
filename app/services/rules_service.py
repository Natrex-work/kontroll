from __future__ import annotations

from typing import Any

from .. import area, live_sources, rules
from .case_service import merge_source_rows


def get_rule_bundle_with_live_sources(*, control_type: str, species: str, gear_type: str, area_status: str = '', control_date: str = '', area_name: str = '', area_notes: str = '', lat: float | None = None, lng: float | None = None) -> dict[str, Any]:
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
    return bundle


def check_zone_status(lat: float, lng: float, species: str = '', gear_type: str = '') -> dict[str, Any]:
    result = area.classify_position(lat, lng)
    local_is_fallback = str(result.get('source_kind') or '').lower() == 'fallback'
    try:
        live_result = live_sources.classify_position_live(lat, lng, species=species, gear_type=gear_type)
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
    try:
        reverse = live_sources.reverse_geocode_live(lat, lng)
        if reverse.get('name') and not result.get('nearest_place'):
            result['nearest_place'] = reverse.get('name')
        if reverse.get('location_label'):
            result['location_name'] = reverse.get('location_label')
        elif not result.get('location_name'):
            result['location_name'] = result.get('nearest_place') or ''
        result['reverse_geocode'] = reverse
    except Exception:
        if not result.get('location_name'):
            result['location_name'] = result.get('nearest_place') or ''
        result['reverse_geocode'] = {'found': False}
    if result.get('match'):
        rec = rules.recommend_area_violation(area_status=result.get('status') or '', area_name=result.get('name') or '', species=species, gear_type=gear_type, notes=result.get('notes') or '')
        if rec:
            result['recommended_violation'] = rec
    return result
