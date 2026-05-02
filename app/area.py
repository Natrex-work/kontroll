from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any, Dict

from . import map_relevance

BASE_DIR = Path(__file__).resolve().parent.parent
ZONES_PATH = BASE_DIR / 'data' / 'zones.json'
PLACES_PATH = BASE_DIR / 'data' / 'places.json'

STATUS_PRIORITY = {
    'stengt område': 5,
    'nullfiskeområde': 5,
    'fredningsområde': 4,
    'maksimalmål område': 3,
    'regulert område': 2,
    'normalt område': 1,
    'ingen treff': 0,
}


def _load(path: Path) -> list[dict[str, Any]]:
    try:
        data = json.loads(path.read_text(encoding='utf-8'))
        if isinstance(data, list):
            return data
    except Exception:
        pass
    return []


ZONES = _load(ZONES_PATH)
PLACES = _load(PLACES_PATH)


def point_in_polygon(lat: float, lng: float, polygon: list[list[float]]) -> bool:
    inside = False
    j = len(polygon) - 1
    for i in range(len(polygon)):
        yi, xi = polygon[i]
        yj, xj = polygon[j]
        intersect = ((xi > lng) != (xj > lng)) and (lat < (yj - yi) * (lng - xi) / ((xj - xi) or 1e-9) + yi)
        if intersect:
            inside = not inside
        j = i
    return inside


def haversine_km(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    r = 6371.0
    p1 = math.radians(lat1)
    p2 = math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lng2 - lng1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def nearest_place(lat: float, lng: float) -> dict[str, Any] | None:
    best = None
    best_dist = None
    for place in PLACES:
        dist = haversine_km(lat, lng, float(place.get('lat') or 0), float(place.get('lng') or 0))
        if best_dist is None or dist < best_dist:
            best = dict(place)
            best_dist = dist
    if best is None:
        return None
    best['distance_km'] = round(float(best_dist or 0), 2)
    return best


def _zone_rank(zone: dict[str, Any]) -> int:
    raw = zone.get('priority')
    if raw is not None:
        try:
            return int(raw)
        except Exception:
            pass
    return STATUS_PRIORITY.get(str(zone.get('status') or '').strip().lower(), 0)


def _zone_hit(zone: dict[str, Any]) -> dict[str, Any]:
    feature = None
    polygon = zone.get('polygon') or []
    if isinstance(polygon, list) and len(polygon) >= 3:
        ring = []
        for point in polygon:
            if not isinstance(point, (list, tuple)) or len(point) < 2:
                continue
            try:
                ring.append([float(point[1]), float(point[0])])
            except Exception:
                continue
        if len(ring) >= 3:
            if ring[0] != ring[-1]:
                ring.append(list(ring[0]))
            feature = {
                'type': 'Feature',
                'geometry': {'type': 'Polygon', 'coordinates': [ring]},
                'properties': {
                    '__layer_name': zone.get('layer_name') or zone.get('layer') or zone.get('status') or 'sone',
                    '__layer_status': zone.get('status') or 'regulert område',
                    'name': zone.get('name') or 'Ukjent sone',
                }
            }
    return {
        'source': zone.get('source') or 'Lokal reserveflate',
        'layer': zone.get('layer_name') or zone.get('layer') or zone.get('status') or 'sone',
        'name': zone.get('name') or 'Ukjent sone',
        'url': zone.get('source_url') or zone.get('url') or '',
        'status': zone.get('status') or 'regulert område',
        'notes': zone.get('notes') or '',
        'layer_ids': zone.get('layer_ids') or [],
        'zone_id': zone.get('id') or '',
        'feature': feature,
    }


def classify_position(lat: float, lng: float, species: str = '', gear_type: str = '', control_type: str = '') -> Dict[str, Any]:
    result = {
        'match': False,
        'status': 'normalt område',
        'name': 'Ingen kjent reguleringssone',
        'source': 'Lokal reserveflate',
        'notes': 'Posisjonen er ikke inne i en registrert lokal reserveflate i denne versjonen.',
        'hits': [],
        'nearest_place': None,
        'distance_to_place_km': None,
    }

    place = nearest_place(lat, lng)
    if place:
        result['nearest_place'] = place.get('name')
        result['distance_to_place_km'] = place.get('distance_km')

    matches: list[dict[str, Any]] = []
    for zone in ZONES:
        zone_meta = map_relevance.decorate_zone_row(zone)
        polygon = zone.get('polygon') or []
        if polygon and point_in_polygon(lat, lng, polygon):
            hit = _zone_hit(zone_meta)
            hit['_rank'] = _zone_rank(zone_meta)
            hit['_selection_match'] = 1 if map_relevance.matches_selection(zone_meta, fishery=species, control_type=control_type, gear_type=gear_type) else 0
            matches.append(hit)

    if matches:
        matches.sort(key=lambda item: (-int(item.get('_selection_match') or 0), -int(item.get('_rank') or 0), str(item.get('name') or '')))
        primary = matches[0]
        result.update({
            'match': True,
            'status': primary.get('status') or 'regulert område',
            'name': primary.get('name') or 'Ukjent sone',
            'source': primary.get('source') or 'Lokal reserveflate',
            'notes': primary.get('notes') or '',
            'hits': [
                {key: value for key, value in item.items() if not key.startswith('_')}
                for item in matches
            ],
        })
    return result
