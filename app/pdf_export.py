from __future__ import annotations

import html
import io
import json
import math
import os
import re
from functools import lru_cache
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterable, List

import requests

try:  # pragma: no cover - optional runtime enhancement for HEIC/HEIF support
    from pillow_heif import register_heif_opener
except Exception:  # pragma: no cover
    register_heif_opener = None

if register_heif_opener is not None:  # pragma: no cover
    try:
        register_heif_opener()
    except Exception:
        pass

try:
    from PIL import Image as PILImage, ImageDraw
except Exception:  # pragma: no cover
    PILImage = None
    ImageDraw = None

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.platypus import Image, PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from . import rules
from .config import settings

BASE_DIR = settings.base_dir
GENERATED_DIR = settings.generated_dir
UPLOAD_DIR = settings.upload_dir

CASE_BASIS_LABELS = {
    'patruljeobservasjon': 'Patrulje',
    'tips': 'Tips',
}




def _iter_polygon_rings(geometry: Dict[str, Any]) -> list[list[list[float]]]:
    gtype = str((geometry or {}).get('type') or '')
    coords = (geometry or {}).get('coordinates') or []
    rings: list[list[list[float]]] = []
    if gtype == 'Polygon':
        for ring in coords:
            rings.append([[float(pt[0]), float(pt[1])] for pt in ring if len(pt) >= 2])
    elif gtype == 'MultiPolygon':
        for polygon in coords:
            for ring in polygon:
                rings.append([[float(pt[0]), float(pt[1])] for pt in ring if len(pt) >= 2])
    return rings


def _shape_intersects_bbox(ring: list[list[float]], bbox: tuple[float, float, float, float]) -> bool:
    if not ring:
        return False
    min_lng = min(pt[0] for pt in ring)
    max_lng = max(pt[0] for pt in ring)
    min_lat = min(pt[1] for pt in ring)
    max_lat = max(pt[1] for pt in ring)
    bmin_lng, bmin_lat, bmax_lng, bmax_lat = bbox
    return not (max_lng < bmin_lng or min_lng > bmax_lng or max_lat < bmin_lat or min_lat > bmax_lat)


def _overview_bbox(lat: float, lng: float, radius_km: float = 50.0) -> tuple[float, float, float, float]:
    lat_delta = radius_km / 111.0
    lng_delta = radius_km / max(35.0, 111.0 * math.cos(math.radians(lat)))
    return (lng - lng_delta, lat - lat_delta, lng + lng_delta, lat + lat_delta)


def _project_point(lng: float, lat: float, bbox: tuple[float, float, float, float], width: int, height: int, pad: int = 60) -> tuple[int, int]:
    bmin_lng, bmin_lat, bmax_lng, bmax_lat = bbox
    usable_w = max(1, width - pad * 2)
    usable_h = max(1, height - pad * 2)
    x = pad + ((lng - bmin_lng) / max((bmax_lng - bmin_lng), 1e-9)) * usable_w
    y = height - pad - ((lat - bmin_lat) / max((bmax_lat - bmin_lat), 1e-9)) * usable_h
    return int(x), int(y)


def _collect_overview_shapes(case_row: Dict[str, Any], bbox: tuple[float, float, float, float]) -> list[dict[str, Any]]:
    shapes: list[dict[str, Any]] = []

    # local fallback zones use [lat, lng] order
    try:
        from . import area
        for zone in getattr(area, 'ZONES', []):
            polygon = zone.get('polygon') or []
            ring = [[float(pt[1]), float(pt[0])] for pt in polygon if len(pt) >= 2]
            if ring and _shape_intersects_bbox(ring, bbox):
                shapes.append({
                    'name': zone.get('name') or 'Regulert sone',
                    'status': zone.get('status') or 'regulert område',
                    'color': '#d97706' if 'fredning' in str(zone.get('status') or '').lower() else '#b91c1c',
                    'rings': [ring],
                })
    except Exception:
        pass

    try:
        from . import live_sources
        for layer in live_sources.portal_layer_catalog():
            cache_path = getattr(live_sources, 'PORTAL_LAYER_CACHE_DIR', GENERATED_DIR) / f"layer_{int(layer['id'])}.geojson"
            if not cache_path.exists():
                continue
            try:
                geojson = json.loads(cache_path.read_text(encoding='utf-8'))
            except Exception:
                continue
            for feature in (geojson.get('features') or [])[:500]:
                rings = [ring for ring in _iter_polygon_rings(feature.get('geometry') or {}) if _shape_intersects_bbox(ring, bbox)]
                if rings:
                    shapes.append({
                        'name': layer.get('name') or 'Kartlag',
                        'status': layer.get('status') or 'regulert område',
                        'color': layer.get('color') or '#24527b',
                        'rings': rings[:6],
                    })
            if len(shapes) > 50:
                break
    except Exception:
        pass
    return shapes[:60]


def _generate_vector_overview_map_image(case_row: Dict[str, Any], output_dir: Path, radius_km: float = 50.0) -> dict[str, Any] | None:
    if PILImage is None or ImageDraw is None:
        return None
    try:
        lat = float(case_row.get('latitude'))
        lng = float(case_row.get('longitude'))
    except Exception:
        return None
    output_dir.mkdir(parents=True, exist_ok=True)
    width, height = 1200, 820
    bbox = _overview_bbox(lat, lng, radius_km=radius_km)
    img = PILImage.new('RGB', (width, height), '#f6f9fd')
    draw = ImageDraw.Draw(img)

    # background grid
    for x in range(60, width - 40, 120):
        draw.line((x, 50, x, height - 70), fill='#dbe6f1', width=1)
    for y in range(60, height - 60, 100):
        draw.line((50, y, width - 50, y), fill='#dbe6f1', width=1)

    shapes = _collect_overview_shapes(case_row, bbox)
    for shape in shapes:
        rgba = shape.get('color') or '#24527b'
        for ring in shape.get('rings') or []:
            pts = [_project_point(pt[0], pt[1], bbox, width, height) for pt in ring]
            if len(pts) >= 3:
                draw.polygon(pts, outline=rgba, fill=None, width=3)

    cx, cy = _project_point(lng, lat, bbox, width, height)
    # 50 km radius circle approximated in projected bbox
    circle_lng = lng + (radius_km / max(35.0, 111.0 * math.cos(math.radians(lat))))
    edge_x, _ = _project_point(circle_lng, lat, bbox, width, height)
    pixel_r = max(20, abs(edge_x - cx))
    draw.ellipse((cx - pixel_r, cy - pixel_r, cx + pixel_r, cy + pixel_r), outline='#24527b', width=3)
    draw.ellipse((cx - 8, cy - 8, cx + 8, cy + 8), fill='#c1121f', outline='#ffffff', width=2)

    title = f"Oversiktskart - {case_row.get('case_number') or 'sak'}"
    subtitle = f"Kontrollposisjon: {lat:.6f}, {lng:.6f} · radius ca. {int(radius_km)} km"
    place = str(case_row.get('location_name') or case_row.get('area_name') or '').strip()
    status = str(case_row.get('area_status') or '').strip()
    if place or status:
        subtitle += f" · {place or status}" if not (place and status) else f" · {place} ({status})"
    draw.text((55, 18), title, fill='#10273d')
    draw.text((55, 40), subtitle, fill='#38506a')

    legend_x = width - 345
    legend_y = 24
    draw.rounded_rectangle((legend_x, legend_y, width - 32, legend_y + 130), radius=16, fill='#ffffff', outline='#d6e1eb')
    draw.text((legend_x + 18, legend_y + 12), 'Tegnforklaring', fill='#10273d')
    legend = [
        ('#24527b', f'Radius ca. {int(round(radius_km))} km'),
        ('#c1121f', 'Kontrollposisjon'),
        ('#f4a261', 'Frednings-/reguleringsområde'),
        ('#e63946', 'Stengt / forbudsområde'),
    ]
    for idx, (color, label) in enumerate(legend):
        y = legend_y + 40 + idx * 20
        draw.rectangle((legend_x + 18, y + 4, legend_x + 34, y + 14), fill=color, outline=color)
        draw.text((legend_x + 44, y), label, fill='#33485c')

    radius_label = str(int(round(radius_km))).replace(' ', '_')
    outpath = output_dir / f"{str(case_row.get('case_number') or 'sak').replace(' ', '_')}_overview_map_{radius_label}km.png"
    img.save(outpath)
    return {
        'filename': outpath.name,
        'original_filename': outpath.name,
        'caption': _map_caption_for_radius_1_8_21(radius_km) if '_map_caption_for_radius_1_8_21' in globals() else 'Oversiktskart av kontrollposisjon',
        'finding_key': 'oversiktskart',
        'law_text': str(case_row.get('area_status') or case_row.get('area_name') or '').strip(),
        'violation_reason': '',
        'created_at': datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC'),
        'generated_path': str(outpath),
        'preview_url': (f"/cases/{case_row.get('id')}/generated/{outpath.name}" if case_row.get('id') is not None else None),
    }




OSM_TILE_CACHE_DIR = GENERATED_DIR / '_tile_cache'
OSM_TILE_CACHE_DIR.mkdir(parents=True, exist_ok=True)
OSM_TILE_URL = 'https://tile.openstreetmap.org/{z}/{x}/{y}.png'
OSM_TILES_DISABLED = False


def _latlng_to_world_px(lat: float, lng: float, zoom: int) -> tuple[float, float]:
    scale = 256 * (2 ** zoom)
    x = (lng + 180.0) / 360.0 * scale
    siny = math.sin(math.radians(max(min(lat, 85.05112878), -85.05112878)))
    y = (0.5 - math.log((1 + siny) / (1 - siny)) / (4 * math.pi)) * scale
    return x, y


def _fetch_osm_tile(z: int, x: int, y: int) -> PILImage.Image | None:
    global OSM_TILES_DISABLED
    if PILImage is None or OSM_TILES_DISABLED:
        return None
    n = 2 ** z
    x = x % n
    if y < 0 or y >= n:
        return None
    path = OSM_TILE_CACHE_DIR / f'{z}_{x}_{y}.png'
    if path.exists():
        try:
            return PILImage.open(path).convert('RGBA')
        except Exception:
            pass
    try:
        resp = requests.get(OSM_TILE_URL.format(z=z, x=x, y=y), timeout=2.5, headers={'User-Agent': 'KV-Kontroll-v41/1.0'})
        resp.raise_for_status()
        img = PILImage.open(io.BytesIO(resp.content)).convert('RGBA')
        try:
            img.save(path)
        except Exception:
            pass
        return img
    except Exception:
        OSM_TILES_DISABLED = True
        return None


WEB_MERCATOR_ORIGIN = 20037508.342789244


def _overview_control_layer_ids(case_row: Dict[str, Any], limit: int = 14) -> list[int]:
    control_type = str(case_row.get('control_type') or '').strip()
    fishery = str(case_row.get('fishery_type') or case_row.get('species') or '').strip()
    gear_type = str(case_row.get('gear_type') or '').strip()
    ids: list[int] = []
    try:
        from . import live_sources
        for row in live_sources.portal_layer_catalog_fast(fishery=fishery, control_type=control_type, gear_type=gear_type):
            try:
                layer_id = int(row.get('id'))
            except Exception:
                continue
            if layer_id == 121 or layer_id in ids:
                continue
            ids.append(layer_id)
            if len(ids) >= limit:
                break
    except Exception:
        pass
    if not ids:
        try:
            from . import map_relevance
            ids = [int(value) for value in sorted(map_relevance.selection_profile_layer_ids(fishery=fishery, control_type=control_type, gear_type=gear_type)) if int(value) != 121]
        except Exception:
            ids = []
    if not ids:
        ids = [0, 7, 9, 10, 11, 13, 31, 37, 38]
    return ids[:limit]


def _overview_arcgis_export_overlay(case_row: Dict[str, Any], min_x: float, min_y: float, max_x: float, max_y: float, zoom: int, width: int, height: int) -> PILImage.Image | None:
    if PILImage is None:
        return None
    layer_ids = _overview_control_layer_ids(case_row)
    if not layer_ids:
        return None
    world_size = 256 * (2 ** zoom)
    meters_per_pixel = (WEB_MERCATOR_ORIGIN * 2.0) / world_size
    xmin = min_x * meters_per_pixel - WEB_MERCATOR_ORIGIN
    xmax = max_x * meters_per_pixel - WEB_MERCATOR_ORIGIN
    ymax = WEB_MERCATOR_ORIGIN - min_y * meters_per_pixel
    ymin = WEB_MERCATOR_ORIGIN - max_y * meters_per_pixel
    base_url = str(os.getenv('KV_PORTAL_MAPSERVER', 'https://gis.fiskeridir.no/server/rest/services/Yggdrasil/Fiskerireguleringer/MapServer') or '').rstrip('/')
    if not base_url:
        return None
    params = {
        'bbox': f'{xmin},{ymin},{xmax},{ymax}',
        'bboxSR': '3857',
        'imageSR': '3857',
        'size': f'{int(width)},{int(height)}',
        'format': 'png32',
        'transparent': 'true',
        'layers': 'show:' + ','.join(str(value) for value in layer_ids),
        'dpi': '96',
        'f': 'image',
    }
    try:
        timeout = float(os.getenv('KV_PORTAL_MAP_EXPORT_TIMEOUT', '3.0') or '3.0')
    except Exception:
        timeout = 3.0
    try:
        response = requests.get(base_url + '/export', params=params, timeout=timeout, headers={'User-Agent': 'KV-Kontroll/1.8.27'})
        response.raise_for_status()
        img = PILImage.open(io.BytesIO(response.content)).convert('RGBA')
        if img.size != (width, height):
            img = img.resize((width, height))
        return img
    except Exception:
        return None


def _generate_tile_overview_map_image(case_row: Dict[str, Any], output_dir: Path, radius_km: float = 50.0, zoom: int = 10) -> dict[str, Any] | None:
    if PILImage is None or ImageDraw is None:
        return None
    try:
        lat = float(case_row.get('latitude'))
        lng = float(case_row.get('longitude'))
    except Exception:
        return None
    output_dir.mkdir(parents=True, exist_ok=True)
    width, height = 1200, 820
    cx, cy = _latlng_to_world_px(lat, lng, zoom)
    min_x = cx - width / 2
    min_y = cy - height / 2
    max_x = cx + width / 2
    max_y = cy + height / 2
    min_tx, max_tx = int(min_x // 256), int(max_x // 256)
    min_ty, max_ty = int(min_y // 256), int(max_y // 256)

    base = PILImage.new('RGBA', (width, height), '#f3f6fa')
    fetched = 0
    for tx in range(min_tx, max_tx + 1):
        for ty in range(min_ty, max_ty + 1):
            tile = _fetch_osm_tile(zoom, tx, ty)
            if tile is None:
                continue
            fetched += 1
            px = int(tx * 256 - min_x)
            py = int(ty * 256 - min_y)
            base.alpha_composite(tile, (px, py))
    portal_overlay = _overview_arcgis_export_overlay(case_row, min_x, min_y, max_x, max_y, zoom, width, height)
    if fetched == 0 and portal_overlay is None:
        return None
    if portal_overlay is not None:
        try:
            base.alpha_composite(portal_overlay, (0, 0))
        except Exception:
            pass

    overlay = PILImage.new('RGBA', (width, height), (255, 255, 255, 0))
    draw = ImageDraw.Draw(overlay)
    bbox = _overview_bbox(lat, lng, radius_km=radius_km)
    for shape in _collect_overview_shapes(case_row, bbox):
        rgba = shape.get('color') or '#24527b'
        try:
            color = tuple(int(rgba.lstrip('#')[i:i+2], 16) for i in (0, 2, 4))
        except Exception:
            color = (36, 82, 123)
        fill = color + (26,)
        outline = color + (220,)
        for ring in shape.get('rings') or []:
            pts = []
            for pt in ring:
                wx, wy = _latlng_to_world_px(pt[1], pt[0], zoom)
                pts.append((int(wx - min_x), int(wy - min_y)))
            if len(pts) >= 3:
                draw.polygon(pts, outline=outline, fill=fill)

    marker_x, marker_y = int(cx - min_x), int(cy - min_y)
    lng_delta = radius_km / max(35.0, 111.0 * math.cos(math.radians(lat)))
    edge_x, _ = _latlng_to_world_px(lat, lng + lng_delta, zoom)
    pixel_r = max(20, int(abs(edge_x - cx)))
    draw.ellipse((marker_x - pixel_r, marker_y - pixel_r, marker_x + pixel_r, marker_y + pixel_r), outline=(36, 82, 123, 180), width=3)
    draw.ellipse((marker_x - 8, marker_y - 8, marker_x + 8, marker_y + 8), fill=(193, 18, 31, 255), outline=(255, 255, 255, 255), width=2)

    out = PILImage.alpha_composite(base, overlay)
    draw2 = ImageDraw.Draw(out)
    draw2.rounded_rectangle((18, 18, 1182, 84), radius=16, fill=(255, 255, 255, 235), outline=(180, 194, 209, 255))
    title = f"Oversiktskart - {case_row.get('case_number') or 'sak'}"
    place = str(case_row.get('location_name') or case_row.get('area_name') or '').strip()
    status = str(case_row.get('area_status') or '').strip()
    subtitle = f"Kontrollposisjon: {lat:.6f}, {lng:.6f} · radius ca. {int(radius_km)} km"
    if place or status:
        subtitle += f" · {place or status}" if not (place and status) else f" · {place} ({status})"
    draw2.text((34, 28), title, fill=(16, 39, 61, 255))
    draw2.text((34, 50), subtitle, fill=(56, 80, 106, 255))
    draw2.rounded_rectangle((885, 96, 1170, 184), radius=14, fill=(255,255,255,230), outline=(180,194,209,255))
    draw2.text((904, 108), 'Tegnforklaring', fill=(16,39,61,255))
    legend = [((36,82,123), f'Radius ca. {int(round(radius_km))} km'), ((193,18,31), 'Kontrollposisjon'), ((244,162,97), 'Frednings-/reguleringsområde'), ((230,57,70), 'Stengt / forbudsområde')]
    for idx, (col, label) in enumerate(legend):
        y = 132 + idx * 18
        draw2.rectangle((904, y + 4, 918, y + 14), fill=col + (255,), outline=col + (255,))
        draw2.text((926, y), label, fill=(51,72,92,255))
    draw2.rounded_rectangle((18, 776, 470, 804), radius=10, fill=(255,255,255,225), outline=(180,194,209,255))
    draw2.text((30, 784), 'Kartbakgrunn © OpenStreetMap-bidragsytere', fill=(66, 82, 100, 255))

    radius_label = str(int(round(radius_km))).replace(' ', '_')
    outpath = output_dir / f"{str(case_row.get('case_number') or 'sak').replace(' ', '_')}_overview_map_{radius_label}km.png"
    out.convert('RGB').save(outpath)
    return {
        'filename': outpath.name,
        'original_filename': outpath.name,
        'caption': _map_caption_for_radius_1_8_21(radius_km) if '_map_caption_for_radius_1_8_21' in globals() else 'Oversiktskart av kontrollposisjon',
        'finding_key': 'oversiktskart',
        'law_text': str(case_row.get('area_status') or case_row.get('area_name') or '').strip(),
        'violation_reason': '',
        'created_at': datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC'),
        'generated_path': str(outpath),
        'preview_url': (f"/cases/{case_row.get('id')}/generated/{outpath.name}" if case_row.get('id') is not None else None),
    }


def _generate_overview_map_image(case_row: Dict[str, Any], output_dir: Path, radius_km: float = 50.0) -> dict[str, Any] | None:
    use_tile_first = str(os.getenv('KV_USE_TILE_OVERVIEW_MAP', '1') or '1').strip().lower() in {'1', 'true', 'yes', 'on'}
    if use_tile_first:
        tile_map = _generate_tile_overview_map_image(case_row, output_dir, radius_km=radius_km)
        if tile_map is not None:
            return tile_map
        return _generate_vector_overview_map_image(case_row, output_dir, radius_km=radius_km)
    vector_map = _generate_vector_overview_map_image(case_row, output_dir, radius_km=radius_km)
    if vector_map is not None:
        return vector_map
    return _generate_tile_overview_map_image(case_row, output_dir, radius_km=radius_km)


def _styles():
    styles = getSampleStyleSheet()
    styles.add(ParagraphStyle(name='Small', fontSize=8, leading=10))
    styles.add(ParagraphStyle(name='Section', fontSize=15, leading=18, spaceAfter=8, spaceBefore=8))
    styles.add(ParagraphStyle(name='BodyTall', fontSize=10, leading=14, spaceBefore=2, spaceAfter=6))
    styles.add(ParagraphStyle(name='MonoSmall', fontName='Courier', fontSize=8, leading=10))
    styles.add(ParagraphStyle(name='MetaTitle', fontSize=11, leading=13, textColor=colors.HexColor('#0f2740'), spaceBefore=6, spaceAfter=4))
    return styles



def _utm_from_lat_lng(lat_value: Any, lng_value: Any) -> str:
    """Returner koordinat som DMS for rapportvisning.

    Funksjonsnavnet beholdes for bakoverkompatibilitet med resten av PDF-koden.
    """
    try:
        lat = float(str(lat_value).replace(',', '.'))
        lon = float(str(lng_value).replace(',', '.'))
    except Exception:
        return ''
    if not (-90 <= lat <= 90 and -180 <= lon <= 180):
        return ''

    def _dms(value: float, positive: str, negative: str) -> str:
        prefix = positive if value >= 0 else negative
        absolute = abs(value)
        degrees = int(absolute)
        minutes_float = (absolute - degrees) * 60
        minutes = int(minutes_float)
        seconds = round((minutes_float - minutes) * 60)
        if seconds >= 60:
            seconds = 0
            minutes += 1
        if minutes >= 60:
            minutes = 0
            degrees += 1
        return f"{prefix} {degrees}° {minutes}' {seconds}\""

    return f"{_dms(lat, 'N', 'S')} {_dms(lon, 'Ø', 'V')}"


def _case_utm(case_row: Dict[str, Any]) -> str:
    if case_row.get('latitude') is None or case_row.get('longitude') is None:
        return ''
    return _utm_from_lat_lng(case_row.get('latitude'), case_row.get('longitude'))

def _fmt_value(value: Any) -> str:
    if value is None:
        return '-'
    if isinstance(value, float):
        return f'{value:.6f}'
    text = str(value).strip()
    return text if text else '-'


def _fmt_datetime(value: str | None) -> str:
    if not value:
        return '-'
    raw = str(value).strip()
    for fmt in ('%Y-%m-%dT%H:%M:%SZ', '%Y-%m-%dT%H:%M', '%Y-%m-%d %H:%M', '%Y-%m-%d'):
        try:
            dt = datetime.strptime(raw, fmt)
            return dt.strftime('%d.%m.%Y %H:%M') if 'H' in fmt else dt.strftime('%d.%m.%Y')
        except ValueError:
            continue
    return raw


def _area_status_value(case_row: Dict[str, Any]) -> str:
    status = str(case_row.get('area_status') or '').strip()
    return '' if status.lower() in {'', 'ingen treff', 'normalt område'} else status


def _area_name_value(case_row: Dict[str, Any]) -> str:
    if not _area_status_value(case_row):
        return ''
    return str(case_row.get('area_name') or '').strip()


def _relevant_area_text(case_row: Dict[str, Any]) -> str:
    status = _area_status_value(case_row)
    if not status:
        return ''
    area_name = _area_name_value(case_row)
    species = str(case_row.get('species') or case_row.get('fishery_type') or '').strip()
    gear_type = str(case_row.get('gear_type') or '').strip()
    try:
        rec = rules.recommend_area_violation(
            area_status=status,
            area_name=area_name,
            species=species,
            gear_type=gear_type,
            notes=str(case_row.get('area_notes') or '').strip(),
        )
    except Exception:
        rec = None
    if not rec:
        return ''
    return area_name or status


def _reportable_findings(findings: list[Dict[str, Any]]) -> list[Dict[str, Any]]:
    out: list[Dict[str, Any]] = []
    for item in findings:
        status = str(item.get('status') or '').strip().lower()
        if status == 'ikke relevant':
            continue
        out.append(item)
    return out


def _measurement_summary(item: Dict[str, Any]) -> str:
    rows = item.get('measurements') or []
    if not isinstance(rows, list) or not rows:
        return ''
    parts: list[str] = []
    for idx, row in enumerate(rows, start=1):
        if not isinstance(row, dict):
            continue
        ref = str(row.get('seizure_ref') or row.get('reference') or f'Måling {idx}').strip()
        length = str(row.get('length_cm') or '').strip()
        delta_text = str(row.get('delta_text') or '').strip()
        photo = str(row.get('photo_ref') or '').strip()
        position = str(row.get('position') or '').strip()
        note = str(row.get('note') or '').strip()
        bit = f'{ref}: {length} cm' if length else ref
        if delta_text:
            bit += f' – {delta_text}'
        extras = []
        if photo:
            extras.append(f'bildereferanse {photo}')
        if position:
            extras.append(f'posisjon {position}')
        if note:
            extras.append(note)
        if extras:
            bit += ' (' + '; '.join(extras) + ')'
        parts.append(bit)
    return '; '.join(parts)


def _marker_summary(item: Dict[str, Any]) -> str:
    pos = item.get('marker_positions') or {}
    if not isinstance(pos, dict):
        return ''
    parts: list[str] = []
    current = str(pos.get('current') or '').strip()
    start = str(pos.get('start') or '').strip()
    end = str(pos.get('end') or '').strip()
    if current:
        parts.append(f'Kontrollørposisjon: {current}')
    if bool(pos.get('is_linked')) and start:
        parts.append(f'Startposisjon lenke: {start}')
    if bool(pos.get('is_linked')) and end:
        parts.append(f'Sluttposisjon lenke: {end}')
    return ' | '.join(parts)


def _finding_display_note(item: Dict[str, Any]) -> str:
    parts = [str(item.get('notes') or '').strip(), _measurement_summary(item), _marker_summary(item)]
    return ' '.join(part for part in parts if part).strip()


def _story_title(text: str, styles):
    return Paragraph(html.escape(text), styles['Section'])


def _kv_table(rows: list[list[str]], widths: list[float] | None = None) -> Table:
    widths = widths or [5 * cm, 11 * cm]
    sample = getSampleStyleSheet()
    header_style = ParagraphStyle(
        'KVTableHeader',
        parent=sample['BodyText'],
        fontName='Helvetica-Bold',
        fontSize=9,
        leading=11,
        spaceBefore=0,
        spaceAfter=0,
    )
    body_style = ParagraphStyle(
        'KVTableBody',
        parent=sample['BodyText'],
        fontName='Helvetica',
        fontSize=9,
        leading=11,
        spaceBefore=0,
        spaceAfter=0,
    )

    wrapped_rows = []
    for r_idx, row in enumerate(rows):
        wrapped = []
        for c_idx, cell in enumerate(row):
            style = header_style if r_idx == 0 or c_idx == 0 else body_style
            wrapped.append(Paragraph(_format_text_for_pdf(str(cell)), style))
        wrapped_rows.append(wrapped)

    table = Table(wrapped_rows, colWidths=widths)
    table.setStyle(
        TableStyle(
            [
                ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#e8eef6')),
                ('BOX', (0, 0), (-1, -1), 0.5, colors.HexColor('#607d8b')),
                ('INNERGRID', (0, 0), (-1, -1), 0.25, colors.HexColor('#90a4ae')),
                ('VALIGN', (0, 0), (-1, -1), 'TOP'),
                ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
                ('TOPPADDING', (0, 0), (-1, -1), 6),
                ('LEFTPADDING', (0, 0), (-1, -1), 6),
                ('RIGHTPADDING', (0, 0), (-1, -1), 6),
            ]
        )
    )
    return table


def _safe_findings(case_row: Dict[str, Any]) -> list[Dict[str, Any]]:
    raw = case_row.get('findings_json') or '[]'
    try:
        data = json.loads(raw)
        if isinstance(data, list):
            return data
    except Exception:
        pass
    return []


def _safe_sources(case_row: Dict[str, Any]) -> list[Dict[str, Any]]:
    raw = case_row.get('source_snapshot_json') or '[]'
    try:
        data = json.loads(raw)
        if isinstance(data, list):
            return data
    except Exception:
        pass
    return []


def _safe_list_json(raw: Any) -> list[Any]:
    try:
        data = json.loads(raw or '[]')
        if isinstance(data, list):
            return data
    except Exception:
        pass
    return []


def _crew_text(case_row: Dict[str, Any]) -> str:
    crew = _safe_list_json(case_row.get('crew_json'))
    if not crew:
        return '-'
    parts = []
    for row in crew:
        name = str((row or {}).get('name') or '').strip()
        role = str((row or {}).get('role') or '').strip()
        if name or role:
            parts.append(' / '.join([x for x in [name, role] if x]))
    return '; '.join(parts) if parts else '-'


def _external_text(case_row: Dict[str, Any]) -> str:
    items = [str(x).strip() for x in _safe_list_json(case_row.get('external_actors_json')) if str(x).strip()]
    return '; '.join(items) if items else '-'


def _non_empty(*values: Any) -> list[str]:
    items: list[str] = []
    for value in values:
        text = str(value or '').strip()
        if text:
            items.append(text)
    return items


def _format_text_for_pdf(text: str) -> str:
    safe = html.escape(text or '')
    return safe.replace('\n', '<br/>')


def _case_basis_label(case_row: Dict[str, Any]) -> str:
    return CASE_BASIS_LABELS.get((case_row.get('case_basis') or '').strip(), 'Patruljeobservasjon')


def _avvik_findings(findings: list[Dict[str, Any]]) -> list[Dict[str, Any]]:
    return [item for item in _reportable_findings(findings) if str(item.get('status') or '').lower() == 'avvik']


def _collect_legal_refs(findings: list[Dict[str, Any]], sources: list[Dict[str, Any]]) -> list[str]:
    refs: list[str] = []
    seen: set[str] = set()

    def add(ref: str) -> None:
        cleaned = ref.strip()
        if cleaned and cleaned not in seen:
            seen.add(cleaned)
            refs.append(cleaned)

    relevant = _avvik_findings(findings) or _reportable_findings(findings)
    for item in relevant:
        bits = _non_empty(item.get('source_name'), item.get('source_ref'))
        if bits:
            add(' - '.join(bits))
    for source in sources:
        bits = _non_empty(source.get('name'), source.get('ref'))
        if bits:
            add(' - '.join(bits))
    return refs


def _ref_payload(item: Dict[str, Any]) -> Dict[str, str]:
    return {
        'name': str(item.get('law_name') or item.get('source_name') or '').strip(),
        'ref': str(item.get('section') or item.get('source_ref') or '').strip(),
        'law_text': str(item.get('law_text') or item.get('help_text') or '').strip(),
    }



def _finding_map(findings: list[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    out: Dict[str, Dict[str, Any]] = {}
    for item in findings:
        key = str(item.get('key') or '').strip()
        if key and key not in out:
            out[key] = item
    return out



def _merge_ref_rows(rows: list[Dict[str, str]]) -> list[Dict[str, str]]:
    out: list[Dict[str, str]] = []
    seen: set[tuple[str, str, str]] = set()
    for row in rows:
        key = (row.get('name', ''), row.get('ref', ''), row.get('law_text', ''))
        if key in seen:
            continue
        seen.add(key)
        out.append(row)
    return out



def _gather_refs(findings: list[Dict[str, Any]], *keys: str) -> list[Dict[str, str]]:
    mapping = _finding_map(findings)
    rows: list[Dict[str, str]] = []
    for key in keys:
        item = mapping.get(key)
        if item:
            rows.append(_ref_payload(item))
    return _merge_ref_rows(rows)



def _finding_note(item: Dict[str, Any]) -> str:
    return _finding_display_note(item)



def _measurement_violation_modes(item: Dict[str, Any]) -> set[str]:
    modes: set[str] = set()
    rows = item.get('measurements') or []
    if not isinstance(rows, list):
        return modes
    for row in rows:
        if not isinstance(row, dict):
            continue
        state = str(row.get('measurement_state') or '').strip().lower()
        if state in {'under_min', 'over_max'}:
            modes.add(state)
    return modes


def _offence_from_finding(case_row: Dict[str, Any], item: Dict[str, Any], findings: list[Dict[str, Any]]) -> Dict[str, Any]:
    key = str(item.get('key') or '').strip().lower()
    subject = str(case_row.get('suspect_name') or 'Ukjent gjerningsperson').strip()
    when = _fmt_datetime(case_row.get('start_time'))
    location = _location_line(case_row)
    area_name = str(case_row.get('area_name') or case_row.get('area_status') or _location_line(case_row)).strip()
    gear = str(case_row.get('gear_type') or 'redskap').strip().lower()
    species = str(case_row.get('species') or case_row.get('fishery_type') or 'fiske').strip().lower()
    note = _finding_note(item)

    title = (item.get('label') or item.get('key') or 'Lovbrudd').strip()
    allegation = f'{subject} anmeldes for mulig brudd på {title.lower()} den {when} ved {location}.'
    ref_keys = [str(item.get('key') or '').strip()]
    group = key or title.lower()

    if key in {'hummer_minstemal'}:
        group = 'hummer_minstemal'
        title = 'Fangst og oppbevaring av hummer under minstemål'
        allegation = f'{subject} anmeldes for å ha fangstet og oppbevart hummer under minstemål den {when} ved {location}.'
        ref_keys = ['hummer_minstemal', 'hummer_gjenutsetting']
    elif key in {'hummer_maksimalmal'}:
        group = 'hummer_maksimalmal'
        title = 'Fangst og oppbevaring av hummer på eller over maksimalmål'
        allegation = f'{subject} anmeldes for å ha fangstet og oppbevart hummer på eller over maksimalmål den {when} ved {location}.'
        ref_keys = ['hummer_maksimalmal', 'hummer_gjenutsetting']
    elif key in {'hummer_lengdekrav'}:
        modes = _measurement_violation_modes(item)
        group = 'hummer_lengdekrav'
        title = 'Fangst og oppbevaring av hummer utenfor tillatt lengdekrav'
        allegation = f'{subject} anmeldes for å ha fangstet og oppbevart hummer i strid med gjeldende lengdekrav den {when} ved {location}.'
        if modes == {'under_min'}:
            group = 'hummer_minstemal'
            title = 'Fangst og oppbevaring av hummer under minstemål'
            allegation = f'{subject} anmeldes for å ha fangstet og oppbevart hummer under minstemål den {when} ved {location}.'
        elif modes == {'over_max'}:
            group = 'hummer_maksimalmal'
            title = 'Fangst og oppbevaring av hummer på eller over maksimalmål'
            allegation = f'{subject} anmeldes for å ha fangstet og oppbevart hummer på eller over maksimalmål den {when} ved {location}.'
        ref_keys = ['hummer_lengdekrav', 'hummer_minstemal', 'hummer_maksimalmal', 'hummer_gjenutsetting']
    elif key in {'hummer_rogn'}:
        group = 'hummer_rogn'
        title = 'Fangst og oppbevaring av rognhummer'
        allegation = f'{subject} anmeldes for å ha fangstet og oppbevart hummer som bar utvendig rogn den {when} ved {location}.'
        ref_keys = ['hummer_rogn', 'hummer_gjenutsetting']
    elif key in {'hummer_merking', 'vak_merking', 'merking_redskap', 'redskap_merket', 'merket_redskap'}:
        group = 'vak_merking'
        title = 'Fiske med redskap uten merking på vak'
        allegation = f'{subject} anmeldes for å ha satt eller brukt redskap der vak/blåse ikke var merket i samsvar med regelverket den {when} ved {location}.'
        ref_keys = ['vak_merking', 'hummer_merking']
    elif key == 'teiner_ruser_merking_rekreasjon':
        group = 'redskap_merking'
        title = 'Fiske med redskap som ikke er merket'
        allegation = f'{subject} anmeldes for å ha satt eller brukt teine eller ruse som ikke var merket med navn og adresse i samsvar med regelverket den {when} ved {location}.'
        ref_keys = ['teiner_ruser_merking_rekreasjon']
    elif key in {'hummer_fluktapning', 'hummer_flukt', 'fluktapning'}:
        group = 'hummer_fluktapning'
        title = 'Fiske med hummerteine uten påbudt fluktåpning'
        allegation = f'{subject} anmeldes for å ha satt eller brukt hummerteine uten påbudt fluktåpning den {when} ved {location}.'
        ref_keys = ['hummer_fluktapning']
    elif key in {'hummer_ratentrad', 'bomullstrad', 'råtnetråd', 'ratentrad'}:
        group = 'hummer_ratentrad'
        title = 'Fiske med hummerteine uten påbudt rømningshull / råtnetråd'
        allegation = f'{subject} anmeldes for å ha satt eller brukt hummerteine uten påbudt rømningshull eller nedbrytbart materiale den {when} ved {location}.'
        ref_keys = ['hummer_ratentrad']
    elif key in {'krabbe_fluktapning_fritid', 'krabbe_fluktapning_komm'}:
        group = 'krabbe_fluktapning'
        title = 'Fiske med krabbeteine uten påbudt fluktåpning'
        allegation = f'{subject} anmeldes for å ha satt eller brukt krabbeteine uten fluktåpning i samsvar med regelverket den {when} ved {location}.'
        ref_keys = [key]
    elif key == 'krabbe_ratentrad':
        group = 'krabbe_ratentrad'
        title = 'Fiske med teine uten påbudt rømningshull'
        allegation = f'{subject} anmeldes for å ha satt eller brukt teine uten påbudt rømningshull eller nedbrytbart materiale den {when} ved {location}.'
        ref_keys = ['krabbe_ratentrad']
    elif key == 'ruse_forbud_periode':
        group = 'ruse_forbud'
        title = 'Fiske med ruse i forbudsperiode'
        allegation = f'{subject} anmeldes for å ha satt eller brukt ruse i forbudsperioden den {when} ved {location}.'
        ref_keys = ['ruse_forbud_periode']
    elif key == 'hummerdeltakernummer':
        group = 'hummer_deltakernummer'
        title = 'Fiske etter hummer uten gyldig deltakernummer'
        allegation = f'{subject} anmeldes for å ha høstet eller forsøkt å høste hummer uten gyldig påmelding og deltakernummer den {when} ved {location}.'
        ref_keys = ['hummerdeltakernummer']
    elif key == 'samleteine_merking':
        group = 'samleteine_merking'
        title = 'Oppbevaring av hummer i sanketeine / samleteine uten korrekt merking'
        allegation = f'{subject} anmeldes for å ha oppbevart hummer i sanketeine eller samleteine som ikke var merket i samsvar med regelverket den {when} ved {location}.'
        ref_keys = ['samleteine_merking', 'hummer_merking']
    elif key == 'hummer_oppbevaring_desember':
        group = 'hummer_oppbevaring_desember'
        title = 'Oppbevaring av hummer i desember uten påkrevd innrapportering'
        allegation = f'{subject} anmeldes for å ha oppbevart hummer i sjøen i desember uten at oppbevaringen var meldt inn i samsvar med regelverket den {when} ved {location}.'
        ref_keys = ['hummer_oppbevaring_desember']
    elif key.startswith('minstemal_') and species:
        group = key
        title = f'Fangst og oppbevaring av {species} under minstemål'
        allegation = f'{subject} anmeldes for å ha fangstet eller oppbevart {species} under minstemål den {when} ved {location}.'
        ref_keys = [key]
    elif key in {'hummer_antall_teiner_fritid', 'hummer_antall_teiner_komm'}:
        group = 'hummer_antall_teiner'
        title = 'Bruk av for mange hummerteiner'
        allegation = f'{subject} anmeldes for å ha satt eller brukt flere hummerteiner enn tillatt den {when} ved {location}.'
        ref_keys = [key]
    elif key == 'hummer_periode':
        group = 'hummer_periode'
        title = 'Fiske etter hummer i strid med periodebestemmelsene'
        allegation = f'{subject} anmeldes for å ha satt eller brukt hummerredskap i strid med periodebestemmelsene den {when} ved {location}.'
        ref_keys = ['hummer_periode']
    elif key == 'hummer_fredningsomrade_redskap':
        group = 'hummer_fredningsomrade'
        title = f'Fiske med {gear} i hummerfredningsområde'
        allegation = f'{subject} anmeldes for å ha satt eller brukt {gear} i hummerfredningsområdet {area_name} den {when} ved {location}.'
        ref_keys = ['hummer_fredningsomrade_redskap']
    elif key in {'stengt_omrade_status', 'omrade_generisk', 'omrade'}:
        group = 'stengt_omrade'
        title = f'Fiske med {gear} i stengt område'
        allegation = f'{subject} anmeldes for å ha satt eller brukt {gear} i stengt eller forbudsregulert område ({area_name}) den {when} ved {location}.'
        ref_keys = ['stengt_omrade_status']
    elif key == 'fredningsomrade_status':
        group = 'fredningsomrade'
        title = f'Fiske med {gear} i fredningsområde'
        allegation = f'{subject} anmeldes for å ha satt eller brukt {gear} i fredningsområde ({area_name}) den {when} ved {location}.'
        ref_keys = ['fredningsomrade_status']
    elif key == 'maksimalmal_omrade':
        group = 'maksimalmal_omrade'
        title = 'Fiske i maksimalmålområde for hummer'
        allegation = f'{subject} anmeldes for å ha fisket etter hummer i maksimalmålområde uten å følge områdets regler den {when} ved {location}.'
        ref_keys = ['maksimalmal_omrade', 'hummer_lengdekrav', 'hummer_maksimalmal']
    elif key == 'garn_line_merke_utenfor_grunnlinjene':
        group = 'merking_utenfor_grunnlinjene'
        title = f'Mangelfull endemerking av {gear}'
        allegation = f'{subject} anmeldes for å ha satt eller brukt {gear} uten påbudt merking utenfor grunnlinjene den {when} ved {location}.'
        ref_keys = ['garn_line_merke_utenfor_grunnlinjene']
    elif key == 'omradekrav':
        group = 'omradekrav'
        title = f'Fiske i område med særregler'
        allegation = f'{subject} anmeldes for mulig brudd på områdets særregler ved bruk av {gear} til {species} den {when} ved {location}.'
        ref_keys = ['omradekrav']

    refs = _gather_refs(findings, *list(dict.fromkeys(ref_keys + [key])))
    if not refs:
        refs = [_ref_payload(item)]
    detail_lines = []
    if note:
        detail_lines.append(note)
    if case_row.get('latitude') is not None and case_row.get('longitude') is not None:
        detail_lines.append(f'Kontrollposisjon: {_fmt_value(case_row.get("latitude"))}, {_fmt_value(case_row.get("longitude"))}.')
    details = ' '.join([line for line in detail_lines if line]).strip()
    return {'group': group, 'title': title, 'allegation': allegation, 'refs': refs, 'details': details, 'key': key}



def _offence_blocks(case_row: Dict[str, Any], findings: list[Dict[str, Any]]) -> list[Dict[str, Any]]:
    offences: list[Dict[str, Any]] = []
    seen: Dict[str, Dict[str, Any]] = {}
    for item in _avvik_findings(findings):
        block = _offence_from_finding(case_row, item, findings)
        group = block['group']
        if group in seen:
            current = seen[group]
            if block.get('details') and block['details'] not in current.get('details', ''):
                current['details'] = ' '.join([part for part in [current.get('details', ''), block['details']] if part]).strip()
            current['refs'] = _merge_ref_rows(list(current.get('refs') or []) + list(block.get('refs') or []))
            continue
        offences.append(block)
        seen[group] = block
    return offences



def _offence_title(case_row: Dict[str, Any], findings: list[Dict[str, Any]]) -> str:
    offences = _offence_blocks(case_row, findings)
    species = (case_row.get('species') or case_row.get('fishery_type') or 'fiske').strip().lower()
    if not offences:
        return f'Kontroll av {species or "fiske"}'
    if len(offences) == 1:
        return offences[0]['title']
    return f'Flere forhold ved kontroll av {species or "fiske"}'


def _primary_document_title(case_row: Dict[str, Any], findings: list[Dict[str, Any]]) -> str:
    return 'Anmeldelse' if _offence_blocks(case_row, findings) else 'Kontrollrapport'



def _selected_control_reason(case_row: Dict[str, Any], findings: list[Dict[str, Any]]) -> str:
    explicit = str(case_row.get('basis_details') or '').strip()
    if explicit:
        return explicit
    return build_control_reason(case_row, findings)



def _clean_generated_phrase(value: Any) -> str:
    text = re.sub(r'\s+', ' ', str(value or '')).strip()
    if not text:
        return ''
    text = re.sub(r'\s*/\s*', ', ', text)
    text = re.sub(r'\s+,', ',', text)
    text = re.sub(r'\(\s+', '(', text)
    text = re.sub(r'\s+\)', ')', text)
    return text.strip()


def _sentenceize(value: Any) -> str:
    text = _clean_generated_phrase(value).strip(' ;')
    if not text:
        return ''
    if text and text[0].islower():
        text = text[0].upper() + text[1:]
    if text[-1] not in '.!?':
        text += '.'
    return text




def _normalize_area_generated_note(note: Any, case_row: Dict[str, Any], item: Dict[str, Any]) -> str:
    clean = _clean_generated_phrase(note)
    area_name = _clean_generated_phrase(_area_name_value(case_row) or item.get('area_name') or item.get('name') or item.get('label') or '')
    area_status = _clean_generated_phrase(_area_status_value(case_row) or item.get('area_status') or item.get('status') or '')
    gear_text = _clean_generated_phrase(case_row.get('gear_type') or item.get('gear_type') or 'redskapet') or 'redskapet'

    if clean:
        clean = re.sub(r'^Ved kontrollstedet ble .*? kontrollert(?: der det befant seg)? i [^.]+\.??\s*', '', clean, flags=re.IGNORECASE)
        clean = re.sub(r'^Posisjonen ligger i [^.]+\.??\s*', '', clean, flags=re.IGNORECASE)
        clean = re.sub('^Valgt redskap \\(([^)]+)\\) er ikke blant redskapene som er tillatt i omr\u00e5det\\.?', 'F\u00f8lgende redskap er ikke tillatt i dette omr\u00e5det: \\1.', clean, flags=re.IGNORECASE)
        clean = re.sub('^Valgt redskap \\(([^)]+)\\) m\u00e5 vurderes som ulovlig eller s\u00e6rskilt regulert i omr\u00e5det\\.?', 'F\u00f8lgende redskap er forbudt eller s\u00e6rskilt regulert i dette omr\u00e5det: \\1.', clean, flags=re.IGNORECASE)
        clean = re.sub('^Dette redskapet er ikke tillatt i hummerfredningsomr\u00e5det\\.?', 'F\u00f8lgende redskap er ikke tillatt i hummerfredningsomr\u00e5det: ' + gear_text.lower() + '.', clean, flags=re.IGNORECASE)
        clean = re.sub('^Omr\u00e5det er registrert som ([^.]+)\\.?', 'Omr\u00e5det er registrert som \\1.', clean, flags=re.IGNORECASE)
        clean = re.sub('^For dette omr\u00e5det gjaldt f\u00f8lgende reguleringer og begrensninger:\\s*', '', clean, flags=re.IGNORECASE)
        clean = re.sub('^Kontroller at valgt redskap er tillatt i omr\u00e5det\\.?', 'Det m\u00e5 kontrolleres om valgt redskap er tillatt i omr\u00e5det.', clean, flags=re.IGNORECASE)
        clean = _sentenceize(clean)

    parts: list[str] = [f'Ved kontrollstedet ble f\u00f8lgende redskap observert og kontrollert: {gear_text.lower()}.']
    if area_name and area_status:
        parts.append(f'Kontrollstedet ligger innenfor {area_name}, registrert som {area_status}.')
    elif area_name:
        parts.append(f'Kontrollstedet ligger innenfor {area_name}.')
    elif area_status:
        parts.append(f'Omr\u00e5det er registrert som {area_status}.')
    if clean:
        parts.append(clean)
    else:
        parts.append('I dette omr\u00e5det gjelder s\u00e6rskilte forbud eller begrensninger som m\u00e5 vurderes opp mot valgt art, redskap og aktivitet.')
    return ' '.join(part.strip() for part in parts if part and part.strip()).replace(' .', '.')

def _dedupe_preserve(values: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for value in values:
        cleaned = _clean_generated_phrase(value).strip()
        if not cleaned:
            continue
        key = re.sub(r'[\s\.;,:]+$', '', cleaned.lower())
        if key in seen:
            continue
        seen.add(key)
        out.append(cleaned)
    return out


def _natural_join(values: list[str]) -> str:
    items = _dedupe_preserve([_clean_generated_phrase(value).rstrip('.') for value in values])
    if not items:
        return ''
    if len(items) == 1:
        return items[0]
    if len(items) == 2:
        return f'{items[0]} og {items[1]}'
    return ', '.join(items[:-1]) + ' og ' + items[-1]


def _gear_description(gear_kind: str, gear_ref: str) -> str:
    kind = _clean_generated_phrase(gear_kind).lower()
    ref = _clean_generated_phrase(gear_ref)
    if kind and ref:
        return f'{kind} med intern referanse {ref}'
    if kind:
        return kind
    if ref:
        return f'redskap med intern referanse {ref}'
    return 'redskap'


def _append_point_detail(container: list[str], value: Any) -> None:
    sentence = _sentenceize(value)
    if sentence:
        container.append(sentence)


def _finding_seizure_refs(item: Dict[str, Any]) -> list[str]:
    refs: list[str] = []
    for row in _deviation_rows(item):
        ref = _clean_generated_phrase(row.get('seizure_ref') or '')
        if ref and ref not in refs:
            refs.append(ref)
    rows = item.get('measurements') or []
    if isinstance(rows, list):
        for row in rows:
            if not isinstance(row, dict):
                continue
            ref = _clean_generated_phrase(row.get('seizure_ref') or row.get('reference') or '')
            if ref and ref not in refs:
                refs.append(ref)
    return refs


def _structured_case_points(case_row: Dict[str, Any], findings: list[Dict[str, Any]]) -> list[str]:
    seizure_groups: dict[str, Dict[str, Any]] = {}
    generic_groups: list[Dict[str, Any]] = []
    area_keys = {
        'hummer_fredningsomrade_redskap',
        'stengt_omrade_status',
        'fredningsomrade_status',
        'maksimalmal_omrade',
        'regulert_omrade',
    }

    def get_group(ref: str) -> Dict[str, Any]:
        if ref not in seizure_groups:
            seizure_groups[ref] = {
                'seizure_ref': ref,
                'gear_kind': '',
                'gear_ref': '',
                'facts': [],
                'offence_titles': [],
                'has_photo': False,
            }
        return seizure_groups[ref]

    for item in _avvik_findings(findings):
        offence = _offence_from_finding(case_row, item, findings)
        item_key = str(item.get('key') or '').strip().lower()
        is_area_item = item_key in area_keys
        shared_note_raw = str((item.get('summary_text') if is_area_item else '') or item.get('notes') or item.get('summary_text') or '').strip()
        shared_note = _normalize_area_generated_note(shared_note_raw, case_row, item) if is_area_item else shared_note_raw
        attached = False

        for row in _deviation_rows(item):
            ref = _clean_generated_phrase(row.get('seizure_ref') or '')
            if not ref:
                continue
            attached = True
            group = get_group(ref)
            if not group['gear_kind'] and str(row.get('gear_kind') or '').strip():
                group['gear_kind'] = str(row.get('gear_kind') or '').strip()
            if not group['gear_ref'] and str(row.get('gear_ref') or '').strip():
                group['gear_ref'] = str(row.get('gear_ref') or '').strip()
            _append_point_detail(group['facts'], row.get('violation') or item.get('label') or item.get('key') or 'Registrert avvik')
            _append_point_detail(group['facts'], shared_note)
            _append_point_detail(group['facts'], row.get('note'))
            if str(row.get('photo_ref') or '').strip():
                group['has_photo'] = True
            if offence.get('title'):
                group['offence_titles'].append(str(offence['title']).strip())

        measurements = item.get('measurements') or []
        if isinstance(measurements, list):
            for idx, row in enumerate(measurements, start=1):
                if not isinstance(row, dict):
                    continue
                ref = _clean_generated_phrase(row.get('seizure_ref') or row.get('reference') or f'{str(item.get("key") or "MALING").upper()}-{idx:02d}')
                attached = True
                group = get_group(ref)
                if not group['gear_kind']:
                    group['gear_kind'] = 'lengdemålt fangst'
                length = _clean_generated_phrase(row.get('length_cm') or '')
                delta_text = _clean_generated_phrase(row.get('delta_text') or '')
                violation_text = _clean_generated_phrase(row.get('violation_text') or '')
                if violation_text:
                    _append_point_detail(group['facts'], violation_text)
                elif length and delta_text:
                    _append_point_detail(group['facts'], f'Kontrollmåling viste {length} cm. {delta_text}')
                elif length:
                    _append_point_detail(group['facts'], f'Kontrollmåling viste {length} cm')
                _append_point_detail(group['facts'], shared_note)
                _append_point_detail(group['facts'], row.get('note'))
                if str(row.get('photo_ref') or '').strip():
                    group['has_photo'] = True
                if offence.get('title'):
                    group['offence_titles'].append(str(offence['title']).strip())

        if attached:
            continue

        generic_facts: list[str] = []
        generic_display = shared_note or _finding_display_note(item) or item.get('label') or item.get('key') or 'Registrert avvik'
        _append_point_detail(generic_facts, generic_display)
        if is_area_item:
            detailed_note = ''
            if detailed_note and detailed_note.strip() != str(generic_display).strip():
                _append_point_detail(generic_facts, detailed_note)
        generic_groups.append({
            'facts': generic_facts,
            'offence_titles': [str(offence.get('title') or '').strip()] if offence.get('title') else [],
        })

    points: list[str] = []
    for group in seizure_groups.values():
        facts = _dedupe_preserve(group['facts'])
        offence_titles = _dedupe_preserve(group['offence_titles'])
        ref = _clean_generated_phrase(group.get('seizure_ref') or '')
        gear_desc = _gear_description(str(group.get('gear_kind') or case_row.get('gear_type') or ''), str(group.get('gear_ref') or ''))
        sentences: list[str] = []
        if ref:
            sentences.append(_sentenceize(f'Beslag nummer {ref} gjaldt {gear_desc}'))
        else:
            sentences.append(_sentenceize(f'Beslaget gjaldt {gear_desc}'))
        if facts:
            sentences.append(_sentenceize('Beslaget hadde følgende avvik'))
            sentences.extend(_sentenceize(fact) for fact in facts)
        else:
            sentences.append(_sentenceize('Det ble registrert avvik ved kontrollen'))
        if offence_titles:
            offence_text = _natural_join([title.lower() for title in offence_titles])
            sentences.append(_sentenceize(f'Forholdet danner grunnlag for anmeldelse for {offence_text}'))
        if group.get('has_photo'):
            sentences.append(_sentenceize('Det er sikret bildebevis knyttet til beslaget'))
        points.append(' '.join(sentence for sentence in sentences if sentence).strip())

    for group in generic_groups:
        facts = _dedupe_preserve(group.get('facts') or [])
        offence_titles = _dedupe_preserve(group.get('offence_titles') or [])
        sentences = [_sentenceize(fact) for fact in facts]
        if not sentences:
            sentences = [_sentenceize('Det ble registrert avvik ved kontrollen')]
        if offence_titles:
            offence_text = _natural_join([title.lower() for title in offence_titles])
            sentences.append(_sentenceize(f'Forholdet danner grunnlag for anmeldelse for {offence_text}'))
        points.append(' '.join(sentence for sentence in sentences if sentence).strip())
    return points


def build_summary(case_row: Dict[str, Any], findings: list[Dict[str, Any]]) -> str:
    if (case_row.get('summary') or '').strip():
        return str(case_row.get('summary') or '').strip()

    subject = _clean_generated_phrase(case_row.get('suspect_name') or 'kontrollert person') or 'kontrollert person'
    when = _fmt_datetime(case_row.get('start_time'))
    location = _location_line(case_row)
    control_reason = _selected_control_reason(case_row, findings)
    points = _structured_case_points(case_row, findings)

    if not points:
        lines = [
            'Oppsummering',
            '',
            f'Kontroll av {subject} ble gjennomført den {when} ved {location}.',
        ]
        if control_reason:
            lines.append(f"Patruljeformål og begrunnelse: {_clean_generated_phrase(control_reason).rstrip('.')} .".replace(' .', '.'))
        lines.append('Det ble ikke registrert avvik i kontrollpunktene som danner grunnlag for anmeldelse.')
        return '\n'.join(lines).strip()

    lines: list[str] = [
        'Anmeldelsesutkast',
        '',
        '1. Kontrollgrunnlag',
        f'Kontrollen ble gjennomført den {when} ved {location}.',
    ]
    if control_reason:
        lines.append(f"Patruljeformål og begrunnelse: {_clean_generated_phrase(control_reason).rstrip('.')} .".replace(' .', '.'))
    lines.extend(['', '2. Registrerte avvik og forhold som anmeldes'])
    for idx, point in enumerate(points, start=1):
        lines.append(f'{idx}. {point}')
    return '\n'.join(lines).strip()

def _service_unit(case_row: Dict[str, Any]) -> str:
    for key in ('service_unit', 'tjenestested'):
        value = str(case_row.get(key) or '').strip()
        if value and value.lower() not in {'kystvaktpatrulje', 'kv patrulje'}:
            return value
    return 'Minfiskerikontroll'


def _basis_opening_phrase(case_row: Dict[str, Any]) -> str:
    unit = _service_unit(case_row)
    return f'Kontrollen ble gjennomført av {unit}'


def build_control_reason(case_row: Dict[str, Any], findings: list[Dict[str, Any]]) -> str:
    basis = (case_row.get('case_basis') or 'patruljeobservasjon').strip()
    theme = _control_theme(case_row) or 'fiskerikontroll'
    area_context = _relevant_area_text(case_row)
    area_text = f' i {area_context}' if area_context else ''
    opening = _basis_opening_phrase(case_row)

    if basis == 'tips':
        return f'{opening} kontroll etter mottatte opplysninger med fokus på {theme.lower()}{area_text}. Formålet var å verifisere opplysningene gjennom stedlig kontroll, posisjonssjekk, dokumentasjon og gjennomgang av relevante sjekkpunkter. Opplysninger fra tipset er i denne teksten holdt adskilt fra det som senere ble observert og kontrollert.'
    if basis == 'anmeldelse':
        return f'{opening} kontroll som oppfølging av registrert anmeldelse rettet mot {theme.lower()}{area_text}. Formålet var å kontrollere faktum, sikre bevis og avklare om det forelå brudd på gjeldende regelverk. Tekstutkastet er skrevet kortfattet og i en notoritetsskapende stil.'
    if basis == 'annen_omstendighet':
        return f'{opening} kontroll på grunnlag av annen omstendighet rettet mot {theme.lower()}{area_text}. Formålet var å avklare faktum, identifisere relevante personer og kontrollobjekt og kontrollere relevante lovkrav.'
    if any(item.get('key') in {'redskap_merket', 'garnlengde', 'antall_teiner', 'antall_ruser', 'antall_angler', 'line_merket', 'garnomraade', 'faststaende_redskap'} for item in findings):
        focus = 'kontroll av faststående fiskeredskap, merking, posisjon, fangst og oppbevaring'
    else:
        focus = 'kontroll av redskap, område, fangst og dokumentasjon'
    return f'{opening} kontroll med fokus på {focus} knyttet til {theme.lower()}{area_text}. Kontrollgrunnlaget bygger på egen observasjon og planlagt kontrollvirksomhet.'


def build_notes_draft(case_row: Dict[str, Any], findings: list[Dict[str, Any]]) -> str:
    avvik = _avvik_findings(findings)
    control_reason = _selected_control_reason(case_row, findings)
    lines = []
    if control_reason:
        lines.append(f'Patruljeformål / begrunnelse: {control_reason}')
        lines.append('')
    lines.extend([
        f"Kontrollen ble gjennomført ved {_location_line(case_row)}.",
        f"Kontrolltema: {_control_theme(case_row) or 'ikke angitt'}.",
        'Det ble kontrollert identitet, redskap, område, fangst/oppbevaring og dokumentasjon i den grad dette var relevant for valgt art og redskap.',
    ])
    if avvik:
        lines.append('Følgende faktiske avvik eller lovbrudd er registrert i kontrollpunktene:')
        for idx, item in enumerate(avvik, start=1):
            label = (item.get('label') or item.get('key') or f'Avvik {idx}').strip()
            note = (_finding_note(item) or 'Registrert av kontrollør.').strip()
            lines.append(f'{idx}. {label}: {note}')
    else:
        lines.append('Det er foreløpig ikke registrert konkrete avvik eller lovbrudd i kontrollpunktene.')
    lines.extend(['', 'Tidligere registrerte saker eller redskap på samme person/fartøy tas ikke med i dette utkastet.'])
    return '\n'.join(lines).strip()


def build_text_drafts(case_row: Dict[str, Any], findings: list[Dict[str, Any]]) -> Dict[str, str]:
    return {
        'summary': build_summary(case_row, findings),
        'basis_details': _selected_control_reason(case_row, findings),
        'notes': build_notes_draft(case_row, findings),
        'complaint_preview': _build_short_complaint(case_row, findings, []),
    }


def _location_line(case_row: Dict[str, Any]) -> str:
    bits = _non_empty(case_row.get('location_name'), _area_name_value(case_row))
    if case_row.get('latitude') is not None and case_row.get('longitude') is not None:
        bits.append(_case_utm(case_row) or 'DMS ikke beregnet')
    return ', '.join(bits) if bits else 'ikke oppgitt sted'


def _control_theme(case_row: Dict[str, Any]) -> str:
    return ' / '.join(_non_empty(case_row.get('control_type'), case_row.get('species') or case_row.get('fishery_type'), case_row.get('gear_type')))


def _render_ref_block(ref: Dict[str, str]) -> list[str]:
    rows = []
    head = ' - '.join([part for part in [ref.get('name', ''), ref.get('ref', '')] if part]).strip()
    if head:
        rows.append(head)
    if ref.get('law_text'):
        rows.append(ref['law_text'])
    return rows




def _build_short_complaint(case_row: Dict[str, Any], findings: list[Dict[str, Any]], sources: list[Dict[str, Any]]) -> str:
    override = str(case_row.get('complaint_override') or '').strip()
    if override:
        return override
    subject = _clean_generated_phrase(case_row.get('suspect_name') or 'kontrollert person') or 'kontrollert person'
    when = _fmt_datetime(case_row.get('start_time'))
    location = _location_line(case_row)
    control_reason = _selected_control_reason(case_row, findings)
    points = _structured_case_points(case_row, findings)
    if not points:
        title = _offence_title(case_row, findings)
        lines = [
            f'Kontrollrapport – {title}',
            '',
            f'Kontroll av {subject} ble gjennomført den {when} ved {location}.',
        ]
        if control_reason:
            lines.append(f"Patruljeformål og begrunnelse: {_clean_generated_phrase(control_reason).rstrip('.')} .".replace(' .', '.'))
        lines.append('Det ble ikke registrert avvik i rapporterbare kontrollpunkter i saken.')
        refs = _collect_legal_refs(findings, sources)
        if refs:
            lines.extend(['', 'Relevante kontrollhjemler:'])
            lines.extend([f'- {ref}' for ref in refs])
        return '\n'.join(lines).strip()

    lines: list[str] = [
        'Kort anmeldelsesutkast',
        '',
        f'Det inngis anmeldelse mot {subject} på grunnlag av kontroll gjennomført den {when} ved {location}.',
    ]
    if control_reason:
        lines.append(f"Patruljeformål og begrunnelse: {_clean_generated_phrase(control_reason).rstrip('.')} .".replace(' .', '.'))
    lines.extend(['', 'Registrerte avvik og forhold som anmeldes:'])
    for idx, point in enumerate(points, start=1):
        lines.append(f'{idx}. {point}')
    return '\n'.join(lines).strip()

def _build_own_report(case_row: Dict[str, Any], findings: list[Dict[str, Any]]) -> str:
    override = str(case_row.get('own_report_override') or '').strip()
    if override:
        return override
    basis = (case_row.get('case_basis') or 'patruljeobservasjon').strip()
    when = _fmt_datetime(case_row.get('start_time'))
    investigator = case_row.get('investigator_name') or 'ukjent etterforsker'
    witness = case_row.get('witness_name') or 'ikke oppgitt vitne'
    crew_text = _crew_text(case_row)
    external_text = _external_text(case_row)
    subject = case_row.get('suspect_name') or 'ukjent person'
    location = _location_line(case_row)
    control_theme = _control_theme(case_row) or 'ukjent kontrolltema'
    avvik = _avvik_findings(findings)
    checklist = ', '.join(item.get('label') or item.get('key') or 'punkt' for item in findings[:6])

    lines: list[str] = []
    if basis == 'tips':
        lines.append(f"Den {when} mottok enheten tips om mulig regelbrudd knyttet til {control_theme.lower()}.")
        if (case_row.get('basis_source_name') or '').strip():
            lines.append(f"Opplysninger registrert i saken: {str(case_row.get('basis_source_name')).strip()}.")
        if (case_row.get('basis_details') or '').strip():
            lines.append(f"Tipset gikk ut på: {str(case_row.get('basis_details')).strip()}.")
        lines.append(f"På bakgrunn av tipset ble det iverksatt kontroll ved {location}.")
    elif basis == 'anmeldelse':
        lines.append(f"Den {when} ble forholdet registrert som anmeldelse knyttet til {control_theme.lower()}.")
        if (case_row.get('basis_source_name') or '').strip():
            lines.append(f"Anmeldelsen ble registrert med anmelder/kilde: {str(case_row.get('basis_source_name')).strip()}.")
        if (case_row.get('basis_details') or '').strip():
            lines.append(f"Det anmeldte forholdet ble oppsummert slik ved registrering: {str(case_row.get('basis_details')).strip()}.")
        lines.append(f"Det ble deretter gjennomført kontroll ved {location}.")
    elif basis == 'annen_omstendighet':
        lines.append(f"Den {when} ble saken opprettet på grunnlag av annen omstendighet knyttet til {control_theme.lower()}.")
        if (case_row.get('basis_details') or '').strip():
            lines.append(f"Bakgrunnen for iverksettingen var: {str(case_row.get('basis_details')).strip()}.")
        lines.append(f"Kontroll ble gjennomført ved {location}.")
    else:
        lines.append(f"Den {when} gjennomførte {investigator} patrulje/kontroll ved {location} i forbindelse med {control_theme.lower()}.")
        lines.append(f"Vitne/medfølgende personell registrert i saken: {witness}.")
        if crew_text != '-':
            lines.append(f"Registrert patruljeteam / roller: {crew_text}.")
        if external_text != '-':
            lines.append(f"Eksterne aktører i saken: {external_text}.")
        if (case_row.get('basis_details') or '').strip():
            lines.append(f"Formål med patruljen: {str(case_row.get('basis_details')).strip()}.")

    if checklist:
        lines.append(f"Kontrollen var rettet mot følgende sjekkpunkter: {checklist}.")

    lines.append(f"Under kontrollen ble {subject} kontrollert.")
    if avvik:
        lines.append('Det ble registrert følgende avvik eller funn:')
        for idx, item in enumerate(avvik, start=1):
            label = (item.get('label') or item.get('key') or f'Avvik {idx}').strip()
            note = (_finding_note(item) or 'Registrert av kontrollør.').strip()
            lines.append(f"{idx}. {label}. {note}")
    else:
        lines.append('Det ble ikke registrert avvik i sjekkpunktene på tidspunktet for denne rapporten.')

    if (case_row.get('notes') or '').strip():
        lines.extend(['', 'Utfyllende notater fra kontrollør:', str(case_row.get('notes')).strip()])
    return '\n'.join(lines).strip()


def _build_interview_report(case_row: Dict[str, Any]) -> str:
    override = str(case_row.get('interview_report_override') or '').strip()
    if override:
        return override
    entries = [entry for entry in _safe_list_json(case_row.get('interview_sessions_json')) if isinstance(entry, dict)]
    if entries:
        lines: list[str] = ['Avhør / forklaring', '']
        for idx, entry in enumerate(entries, start=1):
            name = str(entry.get('name') or case_row.get('suspect_name') or f'Avhørt {idx}').strip()
            role = str(entry.get('role') or 'Avhørt').strip()
            method = str(entry.get('method') or 'ikke oppgitt').strip()
            place = str(entry.get('place') or case_row.get('location_name') or '').strip()
            start = _fmt_datetime(entry.get('start') or case_row.get('start_time'))
            end = _fmt_datetime(entry.get('end') or case_row.get('end_time'))
            transcript = str(entry.get('transcript') or '').strip()
            summary = str(entry.get('summary') or '').strip()
            lines.extend([
                f'Avhør {idx}',
                f'Avhørt: {name} ({role})',
                f'Sted / metode: {method}' + (f' - {place}' if place else ''),
                f'Start: {start}   Slutt: {end}',
                'Gjort kjent med saken, retten til ikke å forklare seg og retten til forsvarer.',
                ''
            ])
            if summary:
                lines.extend(['Sammendrag:', summary, ''])
            lines.extend(['Forklaring:', transcript or 'Ingen registrert forklaring i saken ennå.', ''])
        return '\n'.join(lines).strip()
    subject = case_row.get('suspect_name') or 'Avhørt person'
    when = _fmt_datetime(case_row.get('start_time'))
    investigator = case_row.get('investigator_name') or 'ukjent etterforsker'
    lines = [
        'Avhør / forklaring',
        '',
        f"Avhøret gjelder: {subject}.",
        f"Registrert av: {investigator}.",
        f"Tidsreferanse for saken: {when}.",
        '',
        'Avhørte ble gjort kjent med saken, retten til ikke å forklare seg og retten til forsvarer.',
        '',
        'Fri forklaring (sammendrag):',
        str(case_row.get('hearing_text') or 'Ingen registrert forklaring i saken ennå.').strip(),
    ]
    return '\n'.join(lines).strip()


def _build_seizure_report(case_row: Dict[str, Any], evidence_rows: list[Dict[str, Any]]) -> str:
    override = str(case_row.get('seizure_report_override') or '').strip()
    if override:
        return override
    visible_rows = [item for item in evidence_rows if str(item.get('finding_key') or '') != 'oversiktskart']
    lines = [
        'Rapport om ransaking / beslag / bevis',
        '',
        f"Grunnlag: {_offence_title(case_row, _safe_findings(case_row))}",
        f"Tid og sted: {_fmt_datetime(case_row.get('start_time'))}, {_location_line(case_row)}.",
        f"Ledet av: {case_row.get('investigator_name') or 'ukjent etterforsker'}.",
        f"Vitne: {case_row.get('witness_name') or 'ikke oppgitt'}.",
        '',
        'Sikrede vedlegg/bevis:',
    ]
    if visible_rows:
        for idx, item in enumerate(visible_rows, start=1):
            base = str(item.get('caption') or item.get('original_filename') or item.get('filename') or '').strip()
            law = str(item.get('law_text') or '').strip()
            reason = str(item.get('violation_reason') or '').strip()
            finding_key = str(item.get('finding_key') or '').strip()
            extra = '; '.join([x for x in [finding_key, reason] if x])
            if extra:
                base = f"{base} ({extra})"
            lines.append(f"{idx}. {base}.")
            if law:
                lines.append(f"   Hjemmel / lovtekst: {law}")
    else:
        lines.append('Ingen egne bilag eller bilder registrert i saken.')
    if (case_row.get('seizure_notes') or '').strip():
        lines.extend(['', 'Merknader:', str(case_row.get('seizure_notes')).strip()])
    return '\n'.join(lines).strip()

def _build_illustration_texts(evidence_rows: list[Dict[str, Any]]) -> list[str]:
    if not evidence_rows:
        return ['Ingen illustrasjoner registrert i saken.']
    texts: list[str] = []
    for idx, item in enumerate(evidence_rows, start=1):
        label = (item.get('caption') or item.get('original_filename') or f'Illustrasjon {idx}').strip()
        reason = str(item.get('violation_reason') or '').strip()
        law = str(item.get('law_text') or '').strip()
        if str(item.get('finding_key') or '') == 'oversiktskart':
            texts.append(f"Illustrasjon {idx}: Oversiktskart med kontrollposisjon. {reason}".strip())
            continue
        parts = [f"Illustrasjon {idx}: {label}"]
        if reason:
            parts.append(reason)
        if law:
            parts.append(f"Hjemmel: {law}")
        texts.append(' - '.join(parts))
    return texts


def build_case_packet(case_row: Dict[str, Any], evidence_rows: Iterable[Dict[str, Any]]) -> Dict[str, Any]:
    findings = [dict(item, display_notes=_finding_display_note(item)) for item in _safe_findings(case_row)]
    sources = _safe_sources(case_row)
    all_evidence_rows = list(evidence_rows)
    audio_rows = [dict(item) for item in all_evidence_rows if str(item.get('mime_type') or '').startswith('audio/')]
    image_rows = [dict(item) for item in all_evidence_rows if not str(item.get('mime_type') or '').startswith('audio/')]
    try:
        overview_item = _generate_overview_map_image(case_row, GENERATED_DIR)
    except Exception:
        overview_item = None
    if overview_item:
        image_rows = [overview_item] + image_rows
    summary = build_summary(case_row, findings)
    legal_refs = _collect_legal_refs(findings, sources)
    short_complaint = _build_short_complaint(case_row, findings, sources)
    own_report = _build_own_report(case_row, findings)
    interview_report = _build_interview_report(case_row)
    seizure_report = _build_seizure_report(case_row, image_rows)
    illustration_texts = _build_illustration_texts(image_rows)

    primary_document_title = _primary_document_title(case_row, findings)
    has_offences = bool(_offence_blocks(case_row, findings))
    documents = [
        {'number': '01', 'title': 'Dokumentliste'},
        {'number': '02', 'title': primary_document_title},
        {'number': '03', 'title': f"Egenrapport: {case_row.get('investigator_name') or 'kontrollør'}"},
        {'number': '04', 'title': f"Avhør / forklaring: {case_row.get('suspect_name') or 'mistenkte'}"},
        {'number': '05', 'title': 'Rapport om ransaking / beslag'},
        {'number': '06', 'title': 'Illustrasjonsmappe'},
    ]
    return {
        'documents': documents,
        'primary_document_title': primary_document_title,
        'has_offences': has_offences,
        'title': _offence_title(case_row, findings),
        'summary': summary,
        'short_complaint': short_complaint,
        'own_report': own_report,
        'interview_report': interview_report,
        'seizure_report': seizure_report,
        'illustration_texts': illustration_texts,
        'legal_refs': legal_refs,
        'findings': findings,
        'sources': sources,
        'evidence': [dict(item, preview_url=item.get('preview_url') or (f"/cases/{case_row.get('id')}/evidence/{item.get('id')}/file" if case_row.get('id') is not None and item.get('id') is not None else None)) for item in list(image_rows)],
        'audio_files': [dict(item, preview_url=(f"/cases/{case_row.get('id')}/evidence/{item.get('id')}/file" if case_row.get('id') is not None and item.get('id') is not None else None)) for item in list(audio_rows)],
        'interview_entries': [entry for entry in _safe_list_json(case_row.get('interview_sessions_json')) if isinstance(entry, dict)],
        'notes': case_row.get('notes') or 'Ingen utfyllende egenrapport registrert.',
        'hearing_text': case_row.get('hearing_text') or 'Ingen avhørstekst registrert.',
        'seizure_text': case_row.get('seizure_notes') or 'Ikke oppgitt.',
        'meta_rows': [row for row in [
            ('Saksnummer', _fmt_value(case_row.get('case_number'))),
            ('Registrert', _fmt_datetime(case_row.get('created_at'))),
            ('Oppdatert', _fmt_datetime(case_row.get('updated_at'))),
            ('Grunnlag for iverksetting', _case_basis_label(case_row)),
            ('Etterforsker', _fmt_value(case_row.get('investigator_name'))),
            ('Anmelder', _fmt_value(case_row.get('complainant_name'))),
            ('Observatør/vitne', _fmt_value(case_row.get('witness_name'))),
            ('Signatur anmelder', _fmt_value(case_row.get('complainant_signature'))),
            ('Signatur vitne', _fmt_value(case_row.get('witness_signature'))),
            ('Signatur etterforsker', _fmt_value(case_row.get('investigator_signature'))),
            ('Patruljeteam / roller', _crew_text(case_row)),
            ('Eksterne aktører', _external_text(case_row)),
            ('Kontrolltype', _fmt_value(case_row.get('control_type'))),
            ('Art / fiskeri', f"{_fmt_value(case_row.get('species'))} / {_fmt_value(case_row.get('fishery_type'))}"),
            ('Redskap', _fmt_value(case_row.get('gear_type'))),
            ('Lokasjon', _fmt_value(case_row.get('location_name'))),
            ('Område', ' - '.join([part for part in [_area_status_value(case_row), _area_name_value(case_row)] if part])),
            ('Posisjon', f"{_fmt_value(case_row.get('latitude'))}, {_fmt_value(case_row.get('longitude'))}"),
            ('Mistenkt / ansvarlig', _fmt_value(case_row.get('suspect_name'))),
            ('Mobil', _fmt_value(case_row.get('suspect_phone'))),
            ('Adresse', _fmt_value(case_row.get('suspect_address'))),
            ('Fødselsdato', _fmt_value(case_row.get('suspect_birthdate'))),
            ('Hummerdeltakernr', _fmt_value(case_row.get('hummer_participant_no'))),
            ('Sist registrert hummerregister', _fmt_value(case_row.get('hummer_last_registered') or case_row.get('hummer_participant_status'))),
            ('Fartøysnavn', _fmt_value(case_row.get('vessel_name'))),
            ('Fiskerimerke', _fmt_value(case_row.get('vessel_reg'))),
            ('Radiokallesignal', _fmt_value(case_row.get('radio_call_sign'))),
            ('Tidsrom', f"{_fmt_datetime(case_row.get('start_time'))} - {_fmt_datetime(case_row.get('end_time'))}"),
                        ('Grunnlagsdetaljer', _fmt_value(case_row.get('basis_details'))),
                    ] if str(row[1]).strip() not in {'', '-'}],
    }


def build_case_pdf(case_row: Dict[str, Any], evidence_rows: Iterable[Dict[str, Any]], output_dir: Path) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    filename = f"{case_row['case_number'].replace(' ', '_')}.pdf"
    outpath = output_dir / filename
    styles = _styles()
    packet = build_case_packet(case_row, evidence_rows)
    findings = packet['findings']
    sources = packet['sources']
    evidence_rows = packet['evidence']

    doc = SimpleDocTemplate(
        str(outpath),
        pagesize=A4,
        leftMargin=1.5 * cm,
        rightMargin=1.5 * cm,
        topMargin=1.2 * cm,
        bottomMargin=1.2 * cm,
        title=f"Anmeldelsespakke {case_row['case_number']}",
        author=case_row.get('investigator_name') or 'Minfiskerikontroll',
    )
    story: List[Any] = []

    story.append(Paragraph('Minfiskerikontroll - dokumentpakke', styles['Title']))
    story.append(Paragraph(html.escape(packet['title']), styles['Heading2']))
    story.append(Paragraph(f"Saksnummer: {html.escape(case_row['case_number'])}", styles['MetaTitle']))
    story.append(Spacer(1, 0.2 * cm))
    story.append(_story_title('Dokumentliste', styles))
    docs = [['Dok.nr', 'Dokument']] + [[doc['number'], doc['title']] for doc in packet['documents']]
    story.append(_kv_table(docs, widths=[2.2 * cm, 13.8 * cm]))
    story.append(Spacer(1, 0.35 * cm))
    story.append(_kv_table([['Felt', 'Verdi']] + [[key, value] for key, value in packet['meta_rows'][:8]], widths=[5.5 * cm, 10.5 * cm]))

    story.append(PageBreak())
    story.append(_story_title('Anmeldelse', styles))
    story.append(_kv_table([['Felt', 'Verdi']] + [[key, value] for key, value in packet['meta_rows']], widths=[5.5 * cm, 10.5 * cm]))
    story.append(Spacer(1, 0.2 * cm))
    story.append(Paragraph('Beskrivelse av det anmeldte forhold', styles['Heading3']))
    story.append(Paragraph(_format_text_for_pdf(packet['short_complaint']), styles['BodyTall']))
    story.append(Spacer(1, 0.2 * cm))
    story.append(Paragraph('Aktuelle sjekkpunkter og avvik', styles['Heading3']))
    if findings:
        finding_rows = [['Punkt', 'Status', 'Notat / rettskilde']]
        for item in findings:
            finding_rows.append([
                _fmt_value(item.get('label')),
                _fmt_value(item.get('status')),
                _fmt_value(item.get('notes') or item.get('source_ref') or item.get('source_name')),
            ])
        story.append(_kv_table(finding_rows, widths=[5.8 * cm, 2.4 * cm, 7.8 * cm]))
    else:
        story.append(Paragraph('Ingen sjekkpunkter registrert i denne saken.', styles['BodyTall']))

    story.append(PageBreak())
    story.append(_story_title('Egenrapport', styles))
    story.append(Paragraph(_format_text_for_pdf(packet['own_report']), styles['BodyTall']))

    story.append(PageBreak())
    story.append(_story_title('Avhør / forklaring', styles))
    story.append(Paragraph(_format_text_for_pdf(packet['interview_report']), styles['BodyTall']))

    story.append(PageBreak())
    story.append(_story_title('Rapport om ransaking / beslag', styles))
    story.append(Paragraph(_format_text_for_pdf(packet['seizure_report']), styles['BodyTall']))

    story.append(PageBreak())
    story.append(_story_title('Illustrasjonsmappe', styles))
    for idx, caption in enumerate(packet['illustration_texts'], start=1):
        story.append(Paragraph(html.escape(caption), styles['Heading4']))
        if idx <= len(evidence_rows):
            item = evidence_rows[idx - 1]
            image_path = Path(str(item.get('generated_path') or '')) if item.get('generated_path') else (UPLOAD_DIR / str(item.get('filename') or ''))
            if image_path.exists():
                try:
                    img = Image(str(image_path))
                    img._restrictSize(15.5 * cm, 10 * cm)
                    story.append(img)
                except Exception:
                    story.append(Paragraph(f"Kunne ikke vise bildefil: {html.escape(image_path.name)}", styles['Small']))
        story.append(Spacer(1, 0.25 * cm))
    if not evidence_rows:
        story.append(Paragraph('Ingen bilder eller vedlegg registrert.', styles['BodyTall']))

    doc.build(story)
    return outpath

# --- v13 sample-aligned packet renderer ---
from reportlab.pdfgen import canvas as rl_canvas
from reportlab.lib.utils import ImageReader, simpleSplit

_TEMPLATE_DIR = BASE_DIR / 'app' / 'pdf_templates'
_TEMPLATE_W = 1241.0
_TEMPLATE_H = 1754.0
_PAGE_W, _PAGE_H = A4
_PX_X = _PAGE_W / _TEMPLATE_W
_PX_Y = _PAGE_H / _TEMPLATE_H


def _ppt_x(px: float) -> float:
    return float(px) * _PX_X


def _ppt_y(py_from_top: float) -> float:
    return _PAGE_H - float(py_from_top) * _PX_Y


def _pt_rect(l: float, t: float, r: float, b: float) -> tuple[float, float, float, float]:
    x = _ppt_x(l)
    y = _PAGE_H - float(b) * _PX_Y
    w = _ppt_x(r - l)
    h = float(b - t) * _PX_Y
    return x, y, w, h


@lru_cache(maxsize=32)
def _template_image_reader(template_name: str) -> ImageReader:
    return ImageReader(str(_TEMPLATE_DIR / template_name))


def _draw_template(c: rl_canvas.Canvas, template_name: str) -> None:
    path = _TEMPLATE_DIR / template_name
    if path.exists():
        c.drawImage(_template_image_reader(template_name), 0, 0, width=_PAGE_W, height=_PAGE_H, preserveAspectRatio=False, mask='auto')


def _fill_box_px(c: rl_canvas.Canvas, l: float, t: float, r: float, b: float, fill=colors.white) -> None:
    x, y, w, h = _pt_rect(l, t, r, b)
    c.saveState()
    c.setFillColor(fill)
    c.setStrokeColor(fill)
    c.rect(x, y, w, h, fill=1, stroke=0)
    c.restoreState()


def _stroke_box_px(c: rl_canvas.Canvas, l: float, t: float, r: float, b: float, stroke=colors.black, width: float = 0.9) -> None:
    x, y, w, h = _pt_rect(l, t, r, b)
    c.saveState()
    c.setStrokeColor(stroke)
    c.setLineWidth(width)
    c.rect(x, y, w, h, fill=0, stroke=1)
    c.restoreState()


def _line_px(c: rl_canvas.Canvas, x1: float, y1: float, x2: float, y2: float, width: float = 0.8) -> None:
    c.saveState()
    c.setLineWidth(width)
    c.line(_ppt_x(x1), _ppt_y(y1), _ppt_x(x2), _ppt_y(y2))
    c.restoreState()


def _font(name: str = 'Helvetica', size: float = 8.5) -> tuple[str, float]:
    return name, size


def _wrap_text(text: str, font_name: str, font_size: float, width_pt: float) -> list[str]:
    lines: list[str] = []
    normalized = str(text or '').replace('\r\n', '\n').replace('\r', '\n')
    for para in normalized.split('\n'):
        para = para.rstrip()
        if not para:
            lines.append('')
            continue
        wrapped = simpleSplit(para, font_name, font_size, max(8.0, width_pt))
        lines.extend(wrapped or [''])
    return lines


def _split_text_for_box(text: str, font_name: str, font_size: float, leading: float, width_pt: float, height_pt: float) -> tuple[str, str]:
    lines = _wrap_text(text, font_name, font_size, width_pt)
    max_lines = max(1, int(height_pt / max(leading, 1.0)))
    used = lines[:max_lines]
    rest = lines[max_lines:]
    def join_lines(items: list[str]) -> str:
        out: list[str] = []
        prev_blank = False
        for item in items:
            if item == '':
                if not prev_blank:
                    out.append('')
                prev_blank = True
            else:
                out.append(item)
                prev_blank = False
        return '\n'.join(out).strip('\n')
    return join_lines(used), join_lines(rest)


def _draw_text_px(
    c: rl_canvas.Canvas,
    text: str,
    l: float,
    t: float,
    r: float,
    b: float,
    font_name: str = 'Helvetica',
    font_size: float = 8.5,
    leading: float | None = None,
    color=colors.black,
    align: str = 'left',
    valign: str = 'top',
) -> str:
    x, y, w, h = _pt_rect(l, t, r, b)
    leading = leading or (font_size + 1.6)
    fit, rest = _split_text_for_box(text, font_name, font_size, leading, w - 4, h - 4)
    lines = fit.split('\n') if fit else []
    if not lines:
        return text
    total_h = len(lines) * leading
    if valign == 'middle':
        cur_y = y + h - (h - total_h) / 2 - font_size
    else:
        cur_y = y + h - font_size - 2
    c.saveState()
    c.setFont(font_name, font_size)
    c.setFillColor(color)
    for line in lines:
        line = line.rstrip('\n')
        if align == 'center':
            tx = x + w / 2.0
            c.drawCentredString(tx, cur_y, line)
        elif align == 'right':
            tx = x + w - 2
            c.drawRightString(tx, cur_y, line)
        else:
            tx = x + 2
            c.drawString(tx, cur_y, line)
        cur_y -= leading
    c.restoreState()
    return rest


def _draw_label_value(
    c: rl_canvas.Canvas,
    l: float,
    t: float,
    r: float,
    b: float,
    label: str,
    value: str,
    label_size: float = 6.5,
    value_size: float = 8.6,
    align: str = 'left',
    valign: str = 'top',
) -> None:
    _stroke_box_px(c, l, t, r, b)
    _draw_text_px(c, label, l + 2, t + 1, r - 2, t + 14, font_name='Helvetica-Bold', font_size=label_size, leading=label_size + 1)
    _draw_text_px(c, value, l + 2, t + 13, r - 2, b - 2, font_name='Helvetica', font_size=value_size, leading=value_size + 1.5, align=align, valign=valign)


def _draw_section_caption(c: rl_canvas.Canvas, l: float, t: float, r: float, b: float, title: str) -> None:
    _stroke_box_px(c, l, t, r, b)
    _draw_text_px(c, title, l + 3, t + 4, r - 3, b - 3, font_name='Helvetica-Bold', font_size=8.5, leading=10)




def _case_post_place(case_row: Dict[str, Any]) -> str:
    explicit = str(case_row.get('suspect_post_place') or '').strip()
    if explicit:
        return explicit
    address = str(case_row.get('suspect_address') or '').strip()
    if ',' in address:
        parts = [part.strip() for part in address.split(',') if part.strip()]
        if len(parts) >= 2:
            return parts[-1]
    match = re.search(r'(\d{4}\s+[A-Za-zÆØÅæøå\- ]+)$', address)
    if match:
        return match.group(1).strip()
    return ''

def _fmt_datetime_packet(value: str | None) -> str:
    base = _fmt_datetime(value)
    return f'{base} CET' if base and base != '-' and 'CET' not in base else base


def _doc_writer(case_row: Dict[str, Any], doc_no: str) -> str:
    if doc_no == '01':
        return 'Autogenerert'
    if doc_no in {'02', '06'}:
        return str(case_row.get('complainant_name') or case_row.get('investigator_name') or 'Autogenerert')
    return str(case_row.get('investigator_name') or 'Autogenerert')


def _header_meta_box(c: rl_canvas.Canvas, case_row: Dict[str, Any], doc_no: str, page_no: int, page_count: int) -> None:
    # redraw the variable header cells while keeping the sample title/logo styling
    _fill_box_px(c, 118, 243, 382, 298)
    _fill_box_px(c, 382, 243, 808, 298)
    _fill_box_px(c, 808, 116, 1129, 298)

    _stroke_box_px(c, 118, 243, 382, 298)
    _stroke_box_px(c, 382, 243, 808, 298)
    _stroke_box_px(c, 808, 116, 1129, 298)

    # date / writer cells
    _draw_text_px(c, 'Dato kl.', 124, 247, 240, 259, font_name='Helvetica-Bold', font_size=6.4)
    _draw_text_px(c, _fmt_datetime_packet(case_row.get('updated_at') or case_row.get('created_at')), 124, 262, 376, 294, font_name='Helvetica', font_size=8.2)
    _draw_text_px(c, 'Skrevet av', 388, 247, 500, 259, font_name='Helvetica-Bold', font_size=6.4)
    _draw_text_px(c, _doc_writer(case_row, doc_no), 388, 262, 802, 294, font_name='Helvetica', font_size=8.2)

    # right metadata grid similar to samples
    for yy in (146, 180, 212, 245):
        _line_px(c, 808, yy, 1129, yy)
    for xx in (975, 1018):
        _line_px(c, xx, 116, xx, 245)
    _line_px(c, 1043, 212, 1043, 298)

    case_no = str(case_row.get('case_number') or '-').strip()
    page_text = f'Side {page_no} av {page_count}'
    _draw_text_px(c, 'Anm.nr', 814, 121, 972, 133, font_name='Helvetica-Bold', font_size=6.2)
    _draw_text_px(c, 'Dok.nr', 979, 121, 1118, 133, font_name='Helvetica-Bold', font_size=6.2)
    _draw_text_px(c, case_no, 814, 146, 972, 178, font_name='Helvetica', font_size=9, align='center', valign='middle')
    _draw_text_px(c, doc_no, 1018, 146, 1122, 178, font_name='Helvetica-Bold', font_size=10, align='center', valign='middle')
    _draw_text_px(c, 'Dok. løpenummer', 814, 182, 1012, 194, font_name='Helvetica-Bold', font_size=6.2)
    _draw_text_px(c, doc_no, 814, 196, 1012, 210, font_name='Helvetica', font_size=8.5)
    _draw_text_px(c, 'Skrivebeskyttet', 814, 214, 972, 226, font_name='Helvetica-Bold', font_size=6.2)
    _draw_text_px(c, 'Ja' if doc_no != '04' else 'Nei', 814, 228, 972, 242, font_name='Helvetica', font_size=8.5, align='right')
    _draw_text_px(c, 'Side', 979, 214, 1040, 226, font_name='Helvetica-Bold', font_size=6.2)
    _draw_text_px(c, page_text, 1043, 214, 1122, 242, font_name='Helvetica', font_size=8.5, align='center', valign='middle')
    _draw_text_px(c, 'Tjenestested', 814, 247, 970, 259, font_name='Helvetica-Bold', font_size=6.2)
    _draw_text_px(c, _service_unit(case_row), 814, 262, 1120, 294, font_name='Helvetica', font_size=8.5)


def _common_body_frame(c: rl_canvas.Canvas) -> None:
    _fill_box_px(c, 118, 302, 1128, 1666)


def _draw_sak_section(c: rl_canvas.Canvas, case_row: Dict[str, Any], top: float, location_label: str = 'Åsted', include_identity: bool = False) -> float:
    l, mid, r = 118, 808, 1128
    y = top
    _draw_section_caption(c, l, y, r, y + 28, 'Sak')
    y += 28
    # main rows
    row1 = y + 58
    row2 = row1 + 44
    row3 = row2 + 34
    row4 = row3 + 38
    _draw_label_value(c, l, y, mid, row1, 'Anmeldt forhold', _offence_title(case_row, _safe_findings(case_row)))
    _draw_label_value(c, l, row1, 351, row2, 'Fra dato kl.', _fmt_datetime_packet(case_row.get('start_time')))
    _draw_label_value(c, 351, row1, 579, row2, 'Til dato kl.', _fmt_datetime_packet(case_row.get('end_time')))
    _draw_label_value(c, 579, row1, mid, row2, 'Reg. dato', _fmt_datetime_packet(case_row.get('updated_at') or case_row.get('created_at')))
    _draw_label_value(c, l, row2, mid, row3, 'Sone', 'Skagerrak')
    _draw_label_value(c, l, row3, mid, row4, location_label, _fmt_value(case_row.get('location_name') or _area_name_value(case_row)))
    # right block
    _draw_label_value(c, mid, y, r, row1, 'Etterforskningsinstans', '')
    _draw_label_value(c, mid, row1, r, row2, 'Stat. bokstav | Stat. gruppe | Modus | Sone', '')
    _draw_label_value(c, mid, row2, r, row3, 'Påtaleansvarlig', '')
    _draw_label_value(c, mid, row3, r, row4, 'Etterforsker', _fmt_value(case_row.get('investigator_name')))
    y = row4
    if include_identity:
        row5 = y + 38
        _draw_label_value(c, l, y, 579, row5, 'Navn', _fmt_value(case_row.get('suspect_name')))
        _draw_label_value(c, 579, y, 808, row5, 'Fødselsnr', _fmt_value(case_row.get('suspect_birthdate')))
        _draw_label_value(c, 808, y, r, row5, 'Rolle', 'Siktet / Mistenkt')
        y = row5
    return y


def _draw_simple_table(c: rl_canvas.Canvas, l: float, t: float, widths: list[float], row_h: float, headers: list[str], rows: list[list[str]], font_size: float = 8.0) -> float:
    x_positions = [l]
    for w in widths:
        x_positions.append(x_positions[-1] + w)
    total_r = x_positions[-1]
    _stroke_box_px(c, l, t, total_r, t + row_h)
    for idx, head in enumerate(headers):
        _stroke_box_px(c, x_positions[idx], t, x_positions[idx + 1], t + row_h)
        _draw_text_px(c, str(head or ''), x_positions[idx] + 4, t + 5, x_positions[idx + 1] - 4, t + row_h - 5, font_name='Helvetica-Bold', font_size=font_size, leading=font_size + 1.5)
    y = t + row_h
    for row in rows:
        for idx, cell in enumerate(row):
            _stroke_box_px(c, x_positions[idx], y, x_positions[idx + 1], y + row_h)
            _draw_text_px(c, str(cell or ''), x_positions[idx] + 4, y + 5, x_positions[idx + 1] - 4, y + row_h - 5, font_name='Helvetica', font_size=font_size, leading=font_size + 1.5)
        y += row_h
    return y


def _draw_document_list_body(c: rl_canvas.Canvas, case_row: Dict[str, Any], packet: Dict[str, Any]) -> None:
    y = _draw_sak_section(c, case_row, 302, location_label='Åsted', include_identity=True)
    rel_top = y
    _draw_section_caption(c, 118, rel_top, 1128, rel_top + 28, 'Relaterte forhold')
    _draw_simple_table(c, 118, rel_top + 28, [90, 100, 170, 120, 404], 28, ['Sak nr.', 'Dato', 'Anmeldt av', 'Relasjon', 'Anmeldt forhold'], [['', '', '', '', '']], font_size=7.8)
    doc_top = rel_top + 56 + 28
    _draw_section_caption(c, 118, doc_top, 1128, doc_top + 28, 'Dokumenter')
    rows = []
    for idx, item in enumerate(packet['documents'], start=1):
        dt = _fmt_datetime_packet(case_row.get('updated_at') or case_row.get('created_at')) if item['number'] != '01' else 'Autogenerert'
        author = 'Autogenerert' if item['number'] == '01' else _doc_writer(case_row, item['number'])
        rows.append([item['number'], item['title'], dt, author])
    _draw_simple_table(c, 118, doc_top + 28, [65, 460, 180, 305], 27, ['Dok.nr', 'Dokument tittel', 'Dato', 'Skrevet av'], rows, font_size=7.9)


def _person_box(c: rl_canvas.Canvas, title: str, top: float, name: str, address: str, poststed: str, phone: str, relation: str = '', extra_left: str = '', extra_mid: str = '', extra_right: str = '') -> float:
    _draw_section_caption(c, 118, top, 1128, top + 28, title)
    y = top + 28
    _draw_label_value(c, 118, y, 632, y + 40, 'Navn', name, value_size=8.1)
    _draw_label_value(c, 632, y, 850, y + 40, 'Fødselsnr.' if 'Sikt' not in title and 'Mistenk' not in title else 'Kjønn', extra_mid, value_size=8.0)
    _draw_label_value(c, 850, y, 1128, y + 40, 'Tlf. privat' if 'Sikt' not in title and 'Mistenk' not in title else 'Fødselsnr.', phone if 'Sikt' not in title and 'Mistenk' not in title else extra_right, value_size=8.0)
    y += 40
    _draw_label_value(c, 118, y, 580, y + 40, 'Adresse', address, value_size=8.0)
    _draw_label_value(c, 580, y, 850, y + 40, 'Postnr. og sted', poststed, value_size=8.0)
    _draw_label_value(c, 850, y, 1128, y + 40, 'Tilknytning' if 'Sikt' not in title and 'Mistenk' not in title else 'Tlf. privat', relation if 'Sikt' not in title and 'Mistenk' not in title else phone, value_size=8.0)
    y += 40
    _draw_label_value(c, 118, y, 850, y + 40, 'Arbeidsgiver, adresse, postnr. og sted', extra_left, value_size=7.8)
    _draw_label_value(c, 850, y, 1128, y + 40, 'Org.nummer' if 'Sikt' not in title and 'Mistenk' not in title else 'Tlf. arb.giver', extra_right if 'Sikt' not in title and 'Mistenk' not in title else '', value_size=7.8)
    y += 40
    _draw_label_value(c, 118, y, 1128, y + 28, 'Kan treffes på dagtid (jobb/tlf.)', '')
    return y + 28


def _draw_lines_block(c: rl_canvas.Canvas, title: str, top: float, lines: list[str]) -> float:
    _draw_section_caption(c, 118, top, 1128, top + 28, title)
    y = top + 28
    block_height = max(34, 24 + max(1, len(lines)) * 15)
    _stroke_box_px(c, 118, y, 1128, y + block_height)
    _draw_text_px(c, '\n'.join(lines) if lines else '-', 124, y + 6, 1122, y + block_height - 6, font_name='Helvetica', font_size=8.5, leading=10)
    return y + block_height


def _full_ref_rows(case_row: Dict[str, Any]) -> list[Dict[str, str]]:
    findings = _safe_findings(case_row)
    refs: list[Dict[str, str]] = []
    for offence in _offence_blocks(case_row, findings):
        refs.extend(offence.get('refs') or [])
    return _merge_ref_rows(refs)


def _refs_to_text(refs: list[Dict[str, str]]) -> str:
    chunks: list[str] = []
    for ref in refs:
        head = ' - '.join([part for part in [ref.get('name', ''), ref.get('ref', '')] if part]).strip()
        if head:
            chunks.append(head)
        if ref.get('law_text'):
            chunks.append(ref['law_text'])
        chunks.append('')
    return '\n'.join(chunks).strip()


def _draw_complaint_pages(c: rl_canvas.Canvas, case_row: Dict[str, Any], packet: Dict[str, Any]) -> None:
    refs_text = _refs_to_text(_full_ref_rows(case_row))
    desc_text = packet['short_complaint']

    # first page with fixed summary blocks
    remaining_blocks: list[str] = []
    total_pages = 1

    # estimate remainder after first page law box
    law_fit, law_rest = _split_text_for_box(refs_text, 'Helvetica', 7.6, 8.8, _pt_rect(124, 1020, 1122, 1600)[2], _pt_rect(124, 1020, 1122, 1600)[3])
    if law_rest.strip():
        remaining_blocks.append('Aktuelle lovhjemler (forts.)\n' + law_rest.strip())
    if desc_text.strip():
        remaining_blocks.append('Beskrivelse av det anmeldte forhold\n' + desc_text.strip())
    remaining_text = '\n\n'.join([part for part in remaining_blocks if part.strip()])
    continuation_pages: list[str] = []
    if remaining_text.strip():
        box_w = _pt_rect(124, 332, 1122, 1538)[2]
        box_h = _pt_rect(124, 332, 1122, 1538)[3]
        rest = remaining_text
        while rest:
            fit, next_rest = _split_text_for_box(rest, 'Helvetica', 7.8, 9.1, box_w, box_h)
            continuation_pages.append(fit)
            if not next_rest:
                break
            rest = next_rest
    total_pages = 1 + max(1, len(continuation_pages))

    _draw_template(c, 'page-02.png')
    if packet.get('primary_document_title') and packet.get('primary_document_title') != 'Anmeldelse':
        _fill_box_px(c, 382, 116, 808, 243)
        _stroke_box_px(c, 382, 116, 808, 243)
        _draw_text_px(c, str(packet.get('primary_document_title')), 392, 136, 798, 220, font_name='Helvetica-Bold', font_size=24, align='center', valign='middle')
    _header_meta_box(c, case_row, '02', 1, total_pages)
    _common_body_frame(c)
    y = _draw_sak_section(c, case_row, 302, location_label='Nærmeste stedsangivelse', include_identity=False)
    _draw_section_caption(c, 118, y, 1128, y + 28, 'Verger')
    _draw_label_value(c, 118, y + 28, 1128, y + 56, 'Verges type - Navn, adresse, poster. og sted, tlf.', '')
    y += 56
    y = _person_box(c, 'Anmelder', y, _fmt_value(case_row.get('complainant_name') or _service_unit(case_row)), '', '', '', relation='Anmelder', extra_left=_service_unit(case_row), extra_mid='-', extra_right='')
    y = _draw_lines_block(c, 'Etterforskere', y, [_fmt_value(case_row.get('investigator_name'))])
    witness_lines = []
    crew = [str((x or {}).get('name') or '').strip() for x in _safe_list_json(case_row.get('crew_json')) if str((x or {}).get('name') or '').strip()]
    if case_row.get('witness_name'):
        witness_lines.append(str(case_row.get('witness_name')))
    witness_lines.extend([name for name in crew if name != case_row.get('witness_name')])
    y = _draw_lines_block(c, 'Observatør/vitne', y, witness_lines or ['-'])
    externals = [str(x).strip() for x in _safe_list_json(case_row.get('external_actors_json')) if str(x).strip()]
    y = _draw_lines_block(c, 'Andre personer i saken', y, externals or ['-'])
    y = _person_box(c, 'Siktet / Mistenkt', y, _fmt_value(case_row.get('suspect_name')), _fmt_value(case_row.get('suspect_address')), _fmt_value(_case_post_place(case_row)), _fmt_value(case_row.get('suspect_phone')), relation='', extra_left='', extra_mid='Mann', extra_right=_fmt_value(case_row.get('suspect_birthdate')))
    _draw_section_caption(c, 118, y, 1128, y + 28, 'Aktuelle lovhjemler')
    _stroke_box_px(c, 118, y + 28, 1128, 1602)
    _draw_text_px(c, law_fit, 124, y + 36, 1122, 1596, font_name='Helvetica', font_size=7.6, leading=8.8)

    # continuation pages, always at least one with description/signature
    if not continuation_pages:
        continuation_pages = ['Beskrivelse av det anmeldte forhold\n' + desc_text.strip()]
    for idx, page_text in enumerate(continuation_pages, start=2):
        c.showPage()
        _draw_template(c, 'page-03.png')
        _header_meta_box(c, case_row, '02', idx, total_pages)
        _common_body_frame(c)
        _stroke_box_px(c, 118, 302, 1128, 1546)
        _draw_text_px(c, page_text, 124, 312, 1122, 1538, font_name='Helvetica', font_size=7.8, leading=9.1)
        if idx == total_pages:
            _draw_signature_box_v94(c, 118, 1554, 1128, 1616, 'Anmelder / signatur', case_row, 'complainant_signature', case_row.get('complainant_name') or case_row.get('investigator_name'))


def _draw_own_report_pages(c: rl_canvas.Canvas, case_row: Dict[str, Any]) -> None:
    text = _build_own_report(case_row, _safe_findings(case_row))
    pages: list[str] = []
    remaining = text
    box_l, box_t, box_r, box_b = 124, 392, 1122, 1588
    box_w = _pt_rect(box_l, box_t, box_r, box_b)[2]
    box_h = _pt_rect(box_l, box_t, box_r, box_b)[3]
    while True:
        fit, rest = _split_text_for_box(remaining, 'Helvetica', 8.5, 10.2, box_w, box_h)
        pages.append(fit)
        if not rest:
            break
        remaining = rest
    total = len(pages)
    for idx, page_text in enumerate(pages, start=1):
        _draw_template(c, 'page-04.png')
        _header_meta_box(c, case_row, '03', idx, total)
        _common_body_frame(c)
        _draw_sak_section(c, case_row, 302, location_label='Fra dato kl.', include_identity=False)
        _draw_section_caption(c, 118, 372, 1128, 400, 'Forklaring')
        _stroke_box_px(c, 118, 400, 1128, 1596)
        _draw_text_px(c, page_text, 124, 408, 1122, 1588, font_name='Helvetica', font_size=8.5, leading=10.2)
        if idx < total:
            c.showPage()


def _draw_interview_pages(c: rl_canvas.Canvas, case_row: Dict[str, Any]) -> None:
    full_text = _build_interview_report(case_row)
    first_box_l, first_box_t, first_box_r, first_box_b = 124, 560, 1122, 1580
    cont_box_l, cont_box_t, cont_box_r, cont_box_b = 124, 302, 1122, 1580
    pages: list[tuple[str, str]] = []
    fit, rest = _split_text_for_box(full_text, 'Helvetica', 8.4, 10.0, _pt_rect(first_box_l, first_box_t, first_box_r, first_box_b)[2], _pt_rect(first_box_l, first_box_t, first_box_r, first_box_b)[3])
    pages.append(('first', fit))
    remaining = rest
    while remaining:
        fit, rest = _split_text_for_box(remaining, 'Helvetica', 8.4, 10.0, _pt_rect(cont_box_l, cont_box_t, cont_box_r, cont_box_b)[2], _pt_rect(cont_box_l, cont_box_t, cont_box_r, cont_box_b)[3])
        pages.append(('cont', fit))
        remaining = rest
    total = len(pages)
    for idx, (kind, text) in enumerate(pages, start=1):
        _draw_template(c, 'page-05.png' if kind == 'first' else 'page-06.png')
        _header_meta_box(c, case_row, '04', idx, total)
        _common_body_frame(c)
        if kind == 'first':
            # identity / avhør data block
            _draw_sak_section(c, case_row, 302, location_label='Fra dato kl.', include_identity=False)
            top = 372
            _draw_label_value(c, 118, top, 808, top + 112, 'Avhørt', '\n'.join(_non_empty(case_row.get('suspect_name'), case_row.get('suspect_birthdate'), case_row.get('suspect_address'), case_row.get('suspect_phone'))))
            _draw_label_value(c, 808, top, 1128, top + 112, 'Avhør / forklaring', '\n'.join(_non_empty('Sted: ' + _fmt_value(case_row.get('location_name')), 'Start: ' + _fmt_datetime_packet(case_row.get('start_time')), 'Slutt: ' + _fmt_datetime_packet(case_row.get('end_time')), 'Sted: Telefon / på stedet')))
            _draw_section_caption(c, 118, 492, 1128, 520, 'Forklaring')
            _stroke_box_px(c, 118, 520, 1128, 1596)
            _draw_text_px(c, text, 124, 528, 1122, 1588, font_name='Helvetica', font_size=8.4, leading=10.0)
        else:
            _stroke_box_px(c, 118, 302, 1128, 1596)
            _draw_text_px(c, text, 124, 310, 1122, 1588, font_name='Helvetica', font_size=8.4, leading=10.0)
        if idx < total:
            c.showPage()


def _draw_seizure_page(c: rl_canvas.Canvas, case_row: Dict[str, Any], packet: Dict[str, Any], doc_number: str = '05') -> None:
    _draw_template(c, 'page-07.png')
    _header_meta_box(c, case_row, str(doc_number or '05'), 1, 1)
    _common_body_frame(c)
    _draw_sak_section(c, case_row, 302, location_label='Fra dato kl.', include_identity=False)
    y = 372
    _draw_section_caption(c, 118, y, 1128, y + 28, 'Siktede')
    _draw_label_value(c, 118, y + 28, 808, y + 68, 'Navn', _fmt_value(case_row.get('suspect_name')))
    _draw_label_value(c, 808, y + 28, 1128, y + 68, 'Fødselsnr.', _fmt_value(case_row.get('suspect_birthdate')))
    y += 68
    _draw_section_caption(c, 118, y, 1128, y + 28, 'Ransaking/beslag')
    _draw_label_value(c, 118, y + 28, 640, y + 96, 'Grunnlag', _offence_title(case_row, _safe_findings(case_row)))
    _draw_label_value(c, 640, y + 28, 880, y + 96, 'Fra rett/påtalemyndighet', '')
    _draw_label_value(c, 880, y + 28, 1128, y + 96, 'Samtykke gitt av', '')
    _draw_label_value(c, 118, y + 96, 440, y + 140, 'Rans./beslag dato klokkeslett', _fmt_datetime_packet(case_row.get('end_time') or case_row.get('start_time')))
    _draw_label_value(c, 440, y + 96, 808, y + 140, 'Ledet av', _fmt_value(case_row.get('investigator_name')))
    _draw_label_value(c, 808, y + 96, 1128, y + 140, 'Tjenestested', _service_unit(case_row))
    _draw_label_value(c, 118, y + 140, 1128, y + 176, 'Observatør/vitne', _fmt_value(case_row.get('witness_name')))
    _draw_label_value(c, 118, y + 176, 1128, y + 214, 'Andre tilstedeværende under ransaking/beslag', _fmt_value(case_row.get('suspect_name')))
    _draw_label_value(c, 118, y + 214, 640, y + 252, 'Adresse for ransaking/beslag', _fmt_value(case_row.get('location_name')))
    _draw_label_value(c, 640, y + 214, 1128, y + 252, 'Postnr. og sted', _fmt_value(case_row.get('location_name')))
    _draw_label_value(c, 118, y + 252, 1128, y + 316, 'Merknader', _fmt_value(case_row.get('seizure_notes')))
    table_top = y + 316
    _draw_section_caption(c, 118, table_top, 1128, table_top + 28, f'Beslaglagte gjenstander    Beslag journal nr.{_fmt_value(case_row.get("case_number"))}')
    evs = list(packet.get('evidence') or [])
    visible = [e for e in evs if str(e.get('finding_key') or '') != 'oversiktskart']
    row_y = table_top + 28
    cols = [118, 180, 280, 370, 500, 680, 1128]
    headers = ['Løpenr.', 'Lok.besl. Nr / posenr', 'Antall', 'ID', 'Oppbevart', 'Type/Beskrivelse av gjenstander / Hvor funnet']
    for i in range(len(cols) - 1):
        _draw_label_value(c, cols[i], row_y, cols[i + 1], row_y + 34, headers[i], '')
    row_y += 34
    if not visible:
        visible = [{'caption': 'Ingen beslag registrert', 'violation_reason': '', 'law_text': '', 'finding_key': '', 'generated_path': ''}]
    for idx, ev in enumerate(visible[:3], start=1):
        where = ''
        if case_row.get('latitude') is not None and case_row.get('longitude') is not None:
            where = f"{_fmt_value(case_row.get('latitude'))}N {_fmt_value(case_row.get('longitude'))}E"
        values = [str(idx), str(idx), '1', str(idx), 'Oppbevart', f"{ev.get('caption') or 'Bilag'}\n{where}"]
        for i in range(len(cols) - 1):
            _draw_label_value(c, cols[i], row_y, cols[i + 1], row_y + 56, '', values[i], value_size=8.0)
        row_y += 56
    _draw_label_value(c, 118, 1538, 623, 1604, 'Leders underskrift', _fmt_value(case_row.get('investigator_signature') or case_row.get('investigator_name')))
    _draw_label_value(c, 623, 1538, 1128, 1604, 'Observatør/vitnes underskrift', _fmt_value(case_row.get('witness_signature') or case_row.get('witness_name')))


def _image_path_for_evidence(item: Dict[str, Any]) -> Path | None:
    generated = str(item.get('generated_path') or '').strip()
    if generated and Path(generated).exists():
        return Path(generated)
    filename = str(item.get('filename') or '').strip()
    if filename:
        path = UPLOAD_DIR / filename
        if path.exists():
            return path
    return None


def _draw_image_fit(c: rl_canvas.Canvas, path: Path, l: float, t: float, r: float, b: float) -> None:
    x, y, w, h = _pt_rect(l, t, r, b)
    from PIL import Image as _Image
    try:
        with _Image.open(path) as img:
            iw, ih = img.size
        scale = min(w / max(iw, 1), h / max(ih, 1))
        dw = iw * scale
        dh = ih * scale
        dx = x + (w - dw) / 2.0
        dy = y + (h - dh) / 2.0
        c.drawImage(ImageReader(str(path)), dx, dy, width=dw, height=dh, preserveAspectRatio=True, mask='auto')
    except Exception:
        _stroke_box_px(c, l, t, r, b)
        _draw_text_px(c, f'Kunne ikke vise bildefil: {path.name}', l + 4, t + 4, r - 4, b - 4, font_name='Helvetica', font_size=8)


def _draw_illustration_pages(c: rl_canvas.Canvas, case_row: Dict[str, Any], packet: Dict[str, Any], doc_number: str = '06') -> None:
    evidence = list(packet.get('evidence') or [])
    if not evidence:
        evidence = [{'caption': 'Ingen illustrasjoner registrert', 'filename': '', 'generated_path': ''}]
    chunks = [evidence[i:i + 2] for i in range(0, len(evidence), 2)]
    total = len(chunks)
    for idx, chunk in enumerate(chunks, start=1):
        _draw_template(c, 'page-08.png' if idx == 1 else 'page-09.png')
        _header_meta_box(c, case_row, str(doc_number or '06'), idx, total)
        _common_body_frame(c)
        _draw_sak_section(c, case_row, 302, location_label='Fra dato kl.', include_identity=False)
        _draw_section_caption(c, 118, 372, 1128, 400, 'Illustrasjoner')
        slots = [(186, 430, 1060, 960, 975, 1045), (200, 1060, 1045, 1500, 1510, 1582)]
        for slot_idx, item in enumerate(chunk):
            l, t, r, b, ct, cb = slots[min(slot_idx, len(slots) - 1)]
            img_path = _image_path_for_evidence(item)
            if img_path and img_path.exists():
                _draw_image_fit(c, img_path, l, t, r, b)
            else:
                _stroke_box_px(c, l, t, r, b)
                _draw_text_px(c, 'Mangler bildefil', l + 4, t + 4, r - 4, b - 4, font_name='Helvetica', font_size=8.5)
            caption = str(item.get('caption') or item.get('original_filename') or f'Illustrasjon {slot_idx + 1}').strip()
            reason = str(item.get('violation_reason') or '').strip()
            law = str(item.get('law_text') or '').strip()
            cap_text = caption
            if reason:
                cap_text += f'\n{reason}'
            if law:
                cap_text += f'\nHjemmel: {law}'
            _draw_text_px(c, cap_text, 170, ct, 1070, cb, font_name='Helvetica', font_size=7.6, leading=8.8, align='center')
        if idx < total:
            c.showPage()


def build_case_pdf(case_row: Dict[str, Any], evidence_rows: Iterable[Dict[str, Any]], output_dir: Path) -> Path:  # type: ignore[override]
    output_dir.mkdir(parents=True, exist_ok=True)
    filename = f"{str(case_row['case_number']).replace(' ', '_')}.pdf"
    outpath = output_dir / filename
    packet = build_case_packet(case_row, evidence_rows)

    c = rl_canvas.Canvas(str(outpath), pagesize=A4)
    c.setTitle(f"Anmeldelsespakke {case_row['case_number']}")
    c.setAuthor(case_row.get('investigator_name') or 'Minfiskerikontroll')

    # document list
    _draw_template(c, 'page-01.png')
    _header_meta_box(c, case_row, '01', 1, 1)
    _common_body_frame(c)
    _draw_document_list_body(c, case_row, packet)
    c.showPage()

    # complaint
    _draw_complaint_pages(c, case_row, packet)
    c.showPage()

    # own report
    _draw_own_report_pages(c, case_row)
    c.showPage()

    # interview
    _draw_interview_pages(c, case_row)
    c.showPage()

    # seizure
    _draw_seizure_page(c, case_row, packet)
    c.showPage()

    # illustrations
    _draw_illustration_pages(c, case_row, packet)

    c.save()
    return outpath

# --- layout corrections for compact top sections on pages 03-06 ---
def _draw_sak_section_compact(c: rl_canvas.Canvas, case_row: Dict[str, Any], top: float) -> float:
    l, mid, r = 118, 808, 1128
    y = top
    _draw_section_caption(c, l, y, r, y + 28, 'Sak')
    y += 28
    row1 = y + 52
    row2 = row1 + 40
    row3 = row2 + 34
    _draw_label_value(c, l, y, mid, row1, 'Anmeldt forhold', _offence_title(case_row, _safe_findings(case_row)))
    _draw_label_value(c, l, row1, 351, row2, 'Fra dato kl.', _fmt_datetime_packet(case_row.get('start_time')))
    _draw_label_value(c, 351, row1, 579, row2, 'Til dato kl.', _fmt_datetime_packet(case_row.get('end_time')))
    _draw_label_value(c, 579, row1, mid, row2, 'Reg. dato', _fmt_datetime_packet(case_row.get('updated_at') or case_row.get('created_at')))
    _draw_label_value(c, l, row2, mid, row3, 'Sone', 'Skagerrak')
    _draw_label_value(c, mid, y, r, row1, 'Etterforskningsinstans', '')
    _draw_label_value(c, mid, row1, r, row2, 'Stat. gruppe | Modus | Sone', '')
    _draw_label_value(c, mid, row2, r, row3, 'Etterforsker', _fmt_value(case_row.get('investigator_name')))
    return row3


def _draw_own_report_pages(c: rl_canvas.Canvas, case_row: Dict[str, Any]) -> None:  # type: ignore[override]
    text = _build_own_report(case_row, _safe_findings(case_row))
    box_l, box_t, box_r, box_b = 124, 448, 1122, 1588
    box_w = _pt_rect(box_l, box_t, box_r, box_b)[2]
    box_h = _pt_rect(box_l, box_t, box_r, box_b)[3]
    pages: list[str] = []
    remaining = text
    while True:
        fit, rest = _split_text_for_box(remaining, 'Helvetica', 8.5, 10.2, box_w, box_h)
        pages.append(fit)
        if not rest:
            break
        remaining = rest
    total = len(pages)
    for idx, page_text in enumerate(pages, start=1):
        _draw_template(c, 'page-04.png')
        _header_meta_box(c, case_row, '03', idx, total)
        _common_body_frame(c)
        compact_bottom = _draw_sak_section_compact(c, case_row, 302)
        _draw_section_caption(c, 118, compact_bottom + 10, 1128, compact_bottom + 38, 'Forklaring')
        _stroke_box_px(c, 118, compact_bottom + 38, 1128, 1596)
        _draw_text_px(c, page_text, 124, compact_bottom + 46, 1122, 1588, font_name='Helvetica', font_size=8.5, leading=10.2)
        if idx < total:
            c.showPage()


def _draw_interview_pages(c: rl_canvas.Canvas, case_row: Dict[str, Any]) -> None:  # type: ignore[override]
    full_text = _build_interview_report(case_row)
    first_box_l, first_box_t, first_box_r, first_box_b = 124, 610, 1122, 1580
    cont_box_l, cont_box_t, cont_box_r, cont_box_b = 124, 448, 1122, 1580
    pages: list[tuple[str, str]] = []
    fit, rest = _split_text_for_box(full_text, 'Helvetica', 8.4, 10.0, _pt_rect(first_box_l, first_box_t, first_box_r, first_box_b)[2], _pt_rect(first_box_l, first_box_t, first_box_r, first_box_b)[3])
    pages.append(('first', fit))
    remaining = rest
    while remaining:
        fit, rest = _split_text_for_box(remaining, 'Helvetica', 8.4, 10.0, _pt_rect(cont_box_l, cont_box_t, cont_box_r, cont_box_b)[2], _pt_rect(cont_box_l, cont_box_t, cont_box_r, cont_box_b)[3])
        pages.append(('cont', fit))
        remaining = rest
    total = len(pages)
    for idx, (kind, text) in enumerate(pages, start=1):
        _draw_template(c, 'page-05.png' if kind == 'first' else 'page-06.png')
        _header_meta_box(c, case_row, '04', idx, total)
        _common_body_frame(c)
        compact_bottom = _draw_sak_section_compact(c, case_row, 302)
        if kind == 'first':
            top = compact_bottom + 10
            _draw_label_value(c, 118, top, 640, top + 120, 'Avhørt', '\n'.join(_non_empty(case_row.get('suspect_name'), case_row.get('suspect_birthdate'), case_row.get('suspect_address'), case_row.get('suspect_phone'))))
            _draw_label_value(c, 640, top, 1128, top + 120, 'Avhør / forklaring', '\n'.join(_non_empty('Sted: ' + _fmt_value(case_row.get('location_name')), 'Start: ' + _fmt_datetime_packet(case_row.get('start_time')), 'Slutt: ' + _fmt_datetime_packet(case_row.get('end_time')), 'Avhørsmåte: Telefon / på stedet')))
            _draw_section_caption(c, 118, top + 126, 1128, top + 154, 'Forklaring')
            _stroke_box_px(c, 118, top + 154, 1128, 1596)
            _draw_text_px(c, text, 124, top + 162, 1122, 1588, font_name='Helvetica', font_size=8.4, leading=10.0)
        else:
            _stroke_box_px(c, 118, compact_bottom + 10, 1128, 1596)
            _draw_text_px(c, text, 124, compact_bottom + 18, 1122, 1588, font_name='Helvetica', font_size=8.4, leading=10.0)
        if idx < total:
            c.showPage()


def _draw_seizure_page(c: rl_canvas.Canvas, case_row: Dict[str, Any], packet: Dict[str, Any], doc_number: str = '05') -> None:  # type: ignore[override]
    _draw_template(c, 'page-07.png')
    _header_meta_box(c, case_row, str(doc_number or '05'), 1, 1)
    _common_body_frame(c)
    compact_bottom = _draw_sak_section_compact(c, case_row, 302)
    y = compact_bottom + 10
    _draw_section_caption(c, 118, y, 1128, y + 28, 'Siktede')
    _draw_label_value(c, 118, y + 28, 808, y + 68, 'Navn', _fmt_value(case_row.get('suspect_name')))
    _draw_label_value(c, 808, y + 28, 1128, y + 68, 'Fødselsnr.', _fmt_value(case_row.get('suspect_birthdate')))
    y += 68
    _draw_section_caption(c, 118, y, 1128, y + 28, 'Ransaking/beslag')
    _draw_label_value(c, 118, y + 28, 640, y + 96, 'Grunnlag', _offence_title(case_row, _safe_findings(case_row)))
    _draw_label_value(c, 640, y + 28, 890, y + 96, 'Fra rett/påtalemyndighet', '')
    _draw_label_value(c, 890, y + 28, 1128, y + 96, 'Samtykke gitt av', '')
    _draw_label_value(c, 118, y + 96, 440, y + 140, 'Rans./beslag dato klokkeslett', _fmt_datetime_packet(case_row.get('end_time') or case_row.get('start_time')))
    _draw_label_value(c, 440, y + 96, 808, y + 140, 'Ledet av', _fmt_value(case_row.get('investigator_name')))
    _draw_label_value(c, 808, y + 96, 1128, y + 140, 'Tjenestested', _service_unit(case_row))
    _draw_label_value(c, 118, y + 140, 1128, y + 176, 'Observatør/vitne', _fmt_value(case_row.get('witness_name')))
    _draw_label_value(c, 118, y + 176, 1128, y + 214, 'Andre tilstedeværende under ransaking/beslag', _fmt_value(case_row.get('suspect_name')))
    _draw_label_value(c, 118, y + 214, 640, y + 252, 'Adresse for ransaking/beslag', _fmt_value(case_row.get('location_name')))
    _draw_label_value(c, 640, y + 214, 1128, y + 252, 'Postnr. og sted', _fmt_value(case_row.get('location_name')))
    _draw_label_value(c, 118, y + 252, 1128, y + 316, 'Merknader', _fmt_value(case_row.get('seizure_notes')))
    table_top = y + 316
    _draw_section_caption(c, 118, table_top, 1128, table_top + 28, f'Beslaglagte gjenstander    Beslag journal nr.{_fmt_value(case_row.get("case_number"))}')
    evs = list(packet.get('evidence') or [])
    visible = [e for e in evs if str(e.get('finding_key') or '') != 'oversiktskart'] or [{'caption': 'Ingen beslag registrert'}]
    row_y = table_top + 28
    cols = [118, 180, 280, 370, 500, 680, 1128]
    headers = ['Løpenr.', 'Lok.besl. Nr / posenr', 'Antall', 'ID', 'Oppbevart', 'Type/Beskrivelse av gjenstander / Hvor funnet']
    for i in range(len(cols) - 1):
        _draw_label_value(c, cols[i], row_y, cols[i + 1], row_y + 34, headers[i], '')
    row_y += 34
    for idx, ev in enumerate(visible[:3], start=1):
        where = ''
        if case_row.get('latitude') is not None and case_row.get('longitude') is not None:
            where = f"{_fmt_value(case_row.get('latitude'))}N {_fmt_value(case_row.get('longitude'))}E"
        values = [str(idx), str(idx), '1', str(idx), 'Oppbevart', f"{ev.get('caption') or 'Bilag'}\n{where}"]
        for i in range(len(cols) - 1):
            _draw_label_value(c, cols[i], row_y, cols[i + 1], row_y + 56, '', values[i], value_size=8.0)
        row_y += 56
    _draw_label_value(c, 118, 1538, 623, 1604, 'Leders underskrift', _fmt_value(case_row.get('investigator_signature') or case_row.get('investigator_name')))
    _draw_label_value(c, 623, 1538, 1128, 1604, 'Observatør/vitnes underskrift', _fmt_value(case_row.get('witness_signature') or case_row.get('witness_name')))


def _draw_illustration_pages(c: rl_canvas.Canvas, case_row: Dict[str, Any], packet: Dict[str, Any], doc_number: str = '06') -> None:  # type: ignore[override]
    evidence = list(packet.get('evidence') or []) or [{'caption': 'Ingen illustrasjoner registrert', 'filename': '', 'generated_path': ''}]
    chunks = [evidence[i:i + 2] for i in range(0, len(evidence), 2)]
    total = len(chunks)
    for idx, chunk in enumerate(chunks, start=1):
        _draw_template(c, 'page-08.png' if idx == 1 else 'page-09.png')
        _header_meta_box(c, case_row, str(doc_number or '06'), idx, total)
        _common_body_frame(c)
        compact_bottom = _draw_sak_section_compact(c, case_row, 302)
        _draw_section_caption(c, 118, compact_bottom + 10, 1128, compact_bottom + 38, 'Illustrasjoner')
        slots = [(186, compact_bottom + 54, 1060, 960, 975, 1045), (200, 1060, 1045, 1500, 1510, 1582)]
        # second slot top should adapt when compact section changes, keep sample-like spacing
        slots = [(186, compact_bottom + 54, 1060, compact_bottom + 470, compact_bottom + 480, compact_bottom + 560), (200, compact_bottom + 592, 1045, 1500, 1510, 1582)]
        for slot_idx, item in enumerate(chunk):
            l, t, r, b, ct, cb = slots[min(slot_idx, len(slots) - 1)]
            img_path = _image_path_for_evidence(item)
            if img_path and img_path.exists():
                _draw_image_fit(c, img_path, l, t, r, b)
            else:
                _stroke_box_px(c, l, t, r, b)
                _draw_text_px(c, 'Mangler bildefil', l + 4, t + 4, r - 4, b - 4, font_name='Helvetica', font_size=8.5)
            caption = str(item.get('caption') or item.get('original_filename') or f'Illustrasjon {slot_idx + 1}').strip()
            reason = str(item.get('violation_reason') or '').strip()
            law = str(item.get('law_text') or '').strip()
            cap_text = caption
            if reason:
                cap_text += f'\n{reason}'
            if law:
                cap_text += f'\nHjemmel: {law}'
            _draw_text_px(c, cap_text, 170, ct, 1070, cb, font_name='Helvetica', font_size=7.6, leading=8.8, align='center')
        if idx < total:
            c.showPage()


def build_interview_only_pdf(case_row: Dict[str, Any], evidence_rows: Iterable[Dict[str, Any]], output_dir: Path) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    filename = f"{str(case_row['case_number']).replace(' ', '_')}_avhor.pdf"
    outpath = output_dir / filename
    c = rl_canvas.Canvas(str(outpath), pagesize=A4)
    c.setTitle(f"Avhørsrapport {case_row['case_number']}")
    c.setAuthor(case_row.get('investigator_name') or 'Minfiskerikontroll')
    _draw_interview_pages(c, case_row)
    c.save()
    return outpath


# --- v21 overrides: cleaner single-document PDF and richer finding/seizure summaries ---

def _deviation_rows(item: Dict[str, Any]) -> list[Dict[str, Any]]:
    rows = item.get('deviation_units') or []
    if not isinstance(rows, list):
        return []
    out: list[Dict[str, Any]] = []
    for row in rows:
        if isinstance(row, dict):
            out.append(row)
    return out


def _deviation_summary(item: Dict[str, Any]) -> str:
    rows = _deviation_rows(item)
    if not rows:
        return ''
    parts: list[str] = []
    for idx, row in enumerate(rows, start=1):
        seizure_ref = str(row.get('seizure_ref') or '').strip() or f'Beslag {idx}'
        gear_kind = str(row.get('gear_kind') or '').strip()
        gear_ref = str(row.get('gear_ref') or '').strip()
        quantity = str(row.get('quantity') or '').strip()
        position = str(row.get('position') or '').strip()
        violation = str(row.get('violation') or '').strip() or 'registrert avvik'
        photo_ref = str(row.get('photo_ref') or '').strip()
        note = str(row.get('note') or '').strip()
        bit_parts = [seizure_ref]
        if gear_kind:
            bit_parts.append(f'type {gear_kind}')
        if gear_ref:
            bit_parts.append(f'redskap {gear_ref}')
        if quantity:
            bit_parts.append(f'antall {quantity}')
        if position:
            bit_parts.append(f'posisjon {position}')
        bit = ' / '.join(bit_parts) + ': ' + violation
        extras = []
        if photo_ref:
            extras.append(f'bilde {photo_ref}')
        if note:
            extras.append(note)
        if extras:
            bit += ' (' + '; '.join(extras) + ')'
        parts.append(bit)
    return ' '.join(parts).strip()


def _finding_display_note(item: Dict[str, Any]) -> str:  # type: ignore[override]
    parts = [
        str(item.get('notes') or '').strip(),
        str(item.get('auto_note') or '').strip(),
        _measurement_summary(item),
        _marker_summary(item),
        _deviation_summary(item),
    ]
    return ' '.join(part for part in parts if part).strip()


def _finding_note(item: Dict[str, Any]) -> str:  # type: ignore[override]
    return _finding_display_note(item)


def _collect_seizure_rows_from_findings(findings: list[Dict[str, Any]]) -> list[Dict[str, Any]]:
    rows: list[Dict[str, Any]] = []
    for item in findings:
        if str(item.get('status') or '').lower() != 'avvik':
            continue
        finding_key = str(item.get('key') or '').strip()
        caption = str(item.get('label') or item.get('key') or 'Avvik').strip()
        law_text = str(item.get('law_text') or item.get('help_text') or '').strip()
        for idx, row in enumerate(_deviation_rows(item), start=1):
            rows.append({
                'finding_key': finding_key,
                'caption': caption,
                'seizure_ref': str(row.get('seizure_ref') or '').strip() or f'{str(item.get("key") or "AVVIK").upper()}-{idx:02d}',
                'gear_kind': str(row.get('gear_kind') or '').strip(),
                'gear_ref': str(row.get('gear_ref') or '').strip(),
                'quantity': str(row.get('quantity') or '').strip() or '1',
                'position': str(row.get('position') or '').strip(),
                'linked_seizure_ref': str(row.get('linked_seizure_ref') or '').strip(),
                'violation_reason': str(row.get('violation') or '').strip() or _finding_display_note(item),
                'law_text': law_text,
                'note': str(row.get('note') or '').strip(),
                'photo_ref': str(row.get('photo_ref') or '').strip(),
            })
        measurements = item.get('measurements') or []
        if isinstance(measurements, list):
            for idx, row in enumerate(measurements, start=1):
                if not isinstance(row, dict):
                    continue
                seizure_ref = str(row.get('seizure_ref') or row.get('reference') or '').strip() or f'{str(item.get("key") or "MALING").upper()}-M{idx:02d}'
                length = str(row.get('length_cm') or '').strip()
                delta_text = str(row.get('delta_text') or '').strip()
                violation_reason = str(row.get('violation_text') or '').strip()
                if not violation_reason:
                    if length and delta_text:
                        violation_reason = f'Kontrollmålt til {length} cm – {delta_text}.'
                    elif length:
                        violation_reason = f'Kontrollmålt til {length} cm.'
                    else:
                        violation_reason = _finding_display_note(item)
                rows.append({
                    'finding_key': finding_key,
                    'caption': caption,
                    'seizure_ref': seizure_ref,
                    'gear_kind': 'Lengdemåling',
                    'gear_ref': '',
                    'quantity': '1',
                    'position': str(row.get('position') or '').strip(),
                    'linked_seizure_ref': str(row.get('linked_seizure_ref') or '').strip(),
                    'violation_reason': violation_reason,
                    'law_text': law_text,
                    'note': str(row.get('note') or '').strip(),
                    'photo_ref': str(row.get('photo_ref') or '').strip(),
                })
    return rows


def _build_seizure_report(case_row: Dict[str, Any], evidence_rows: list[Dict[str, Any]]) -> str:  # type: ignore[override]
    override = str(case_row.get('seizure_report_override') or '').strip()
    if override:
        return override
    findings = _safe_findings(case_row)
    deviation_rows = _collect_seizure_rows_from_findings(findings)
    visible_rows = [item for item in evidence_rows if str(item.get('finding_key') or '') != 'oversiktskart']
    lines = [
        'Rapport om ransaking / beslag / bevis',
        '',
        f"Grunnlag: {_offence_title(case_row, findings)}",
        f"Tid og sted: {_fmt_datetime(case_row.get('start_time'))}, {_location_line(case_row)}.",
        f"Ledet av: {case_row.get('investigator_name') or 'ukjent etterforsker'}.",
        f"Vitne: {case_row.get('witness_name') or 'ikke oppgitt'}.",
        '',
        'Beslag / registrerte avviksenheter:',
    ]
    if deviation_rows:
        for idx, row in enumerate(deviation_rows, start=1):
            parts = [f"{idx}. {row.get('seizure_ref') or f'Beslag {idx}'}"]
            if row.get('gear_kind'):
                parts.append(f"type {row['gear_kind']}")
            if row.get('gear_ref'):
                parts.append(f"redskap {row['gear_ref']}")
            if row.get('quantity'):
                parts.append(f"antall {row['quantity']}")
            line = ' - '.join(parts) + f": {row.get('violation_reason') or 'registrert avvik'}."
            lines.append(line)
            if row.get('law_text'):
                lines.append(f"   Hjemmel: {row['law_text']}")
            if row.get('note'):
                lines.append(f"   Merknad: {row['note']}")
    else:
        lines.append('Ingen egne beslag-/avviksrader registrert i kontrollpunktene.')
    lines.extend(['', 'Sikrede vedlegg / bilder:'])
    if visible_rows:
        for idx, item in enumerate(visible_rows, start=1):
            base = str(item.get('caption') or item.get('original_filename') or item.get('filename') or '').strip() or f'Bilag {idx}'
            refs = [str(item.get('seizure_ref') or '').strip(), str(item.get('finding_key') or '').strip(), str(item.get('violation_reason') or '').strip()]
            refs = [r for r in refs if r]
            lines.append(f"{idx}. {base}" + (f" ({'; '.join(refs)})" if refs else '') + '.')
            if item.get('law_text'):
                lines.append(f"   Hjemmel / lovtekst: {str(item.get('law_text') or '').strip()}")
    else:
        lines.append('Ingen egne bilag eller bilder registrert i saken.')
    if (case_row.get('seizure_notes') or '').strip():
        lines.extend(['', 'Merknader:', str(case_row.get('seizure_notes')).strip()])
    return '\n'.join(lines).strip()


def _story_styles_v21():
    styles = getSampleStyleSheet()
    return {
        'title': ParagraphStyle('KVTitle', parent=styles['Heading1'], fontName='Helvetica-Bold', fontSize=20, leading=24, spaceAfter=12),
        'subtitle': ParagraphStyle('KVSubTitle', parent=styles['Normal'], fontName='Helvetica', fontSize=10, leading=12, textColor=colors.HexColor('#4b5563'), spaceAfter=8),
        'section': ParagraphStyle('KVSection', parent=styles['Heading2'], fontName='Helvetica-Bold', fontSize=12, leading=14, textColor=colors.HexColor('#111827'), spaceBefore=10, spaceAfter=6),
        'body': ParagraphStyle('KVBody', parent=styles['Normal'], fontName='Helvetica', fontSize=9.2, leading=12, spaceAfter=6),
        'small': ParagraphStyle('KVSmall', parent=styles['Normal'], fontName='Helvetica', fontSize=8, leading=10, textColor=colors.HexColor('#4b5563')),
    }


def _meta_table_v21(rows: list[tuple[str, str]]) -> Table:
    body = [[Paragraph(f'<b>{html.escape(k)}</b>', _story_styles_v21()['body']), Paragraph(_format_text_for_pdf(v), _story_styles_v21()['body'])] for k, v in rows]
    if not body:
        body = [[Paragraph('<b>Ingen metadata</b>', _story_styles_v21()['body']), Paragraph('-', _story_styles_v21()['body'])]]
    tbl = Table(body, colWidths=[5.5 * cm, 11.5 * cm], repeatRows=0)
    tbl.setStyle(TableStyle([
        ('BOX', (0, 0), (-1, -1), 0.6, colors.HexColor('#111827')),
        ('INNERGRID', (0, 0), (-1, -1), 0.35, colors.HexColor('#9ca3af')),
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('BACKGROUND', (0, 0), (0, -1), colors.HexColor('#f3f4f6')),
        ('LEFTPADDING', (0, 0), (-1, -1), 6),
        ('RIGHTPADDING', (0, 0), (-1, -1), 6),
        ('TOPPADDING', (0, 0), (-1, -1), 5),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 5),
    ]))
    return tbl


def _findings_table_v21(findings: list[Dict[str, Any]]) -> Table:
    styles = _story_styles_v21()
    rows: list[list[Any]] = [[Paragraph('<b>Punkt</b>', styles['body']), Paragraph('<b>Status</b>', styles['body']), Paragraph('<b>Detaljer</b>', styles['body'])]]
    for item in _reportable_findings(findings):
        status = str(item.get('status') or '').strip().lower()
        if status == 'ikke relevant':
            continue
        note = _finding_display_note(item) or '-'
        rows.append([
            Paragraph(html.escape(str(item.get('label') or item.get('key') or 'Punkt')), styles['body']),
            Paragraph(html.escape(status or '-'), styles['body']),
            Paragraph(_format_text_for_pdf(note), styles['body']),
        ])
    tbl = Table(rows, colWidths=[5.2 * cm, 2.6 * cm, 9.2 * cm], repeatRows=1)
    tbl.setStyle(TableStyle([
        ('BOX', (0, 0), (-1, -1), 0.6, colors.HexColor('#111827')),
        ('INNERGRID', (0, 0), (-1, -1), 0.35, colors.HexColor('#9ca3af')),
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#e5e7eb')),
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('LEFTPADDING', (0, 0), (-1, -1), 5),
        ('RIGHTPADDING', (0, 0), (-1, -1), 5),
        ('TOPPADDING', (0, 0), (-1, -1), 4),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
    ]))
    return tbl


def _signatures_table_v21(case_row: Dict[str, Any]) -> Table:
    styles = _story_styles_v21()
    rows = [[
        Paragraph('<b>Anmelder</b>', styles['body']),
        Paragraph('<b>Vitne</b>', styles['body']),
        Paragraph('<b>Etterforsker</b>', styles['body'])
    ], [
        Paragraph(_format_text_for_pdf(str(case_row.get('complainant_signature') or case_row.get('complainant_name') or '-')), styles['body']),
        Paragraph(_format_text_for_pdf(str(case_row.get('witness_signature') or case_row.get('witness_name') or '-')), styles['body']),
        Paragraph(_format_text_for_pdf(str(case_row.get('investigator_signature') or case_row.get('investigator_name') or '-')), styles['body']),
    ]]
    tbl = Table(rows, colWidths=[5.7 * cm, 5.7 * cm, 5.7 * cm])
    tbl.setStyle(TableStyle([
        ('BOX', (0, 0), (-1, -1), 0.6, colors.HexColor('#111827')),
        ('INNERGRID', (0, 0), (-1, -1), 0.35, colors.HexColor('#9ca3af')),
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#f3f4f6')),
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('LEFTPADDING', (0, 0), (-1, -1), 6),
        ('RIGHTPADDING', (0, 0), (-1, -1), 6),
        ('TOPPADDING', (0, 0), (-1, -1), 10),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 12),
    ]))
    return tbl


def _header_footer_v21(canvas, doc):
    canvas.saveState()
    canvas.setFont('Helvetica-Bold', 9)
    canvas.drawString(doc.leftMargin, A4[1] - 1.2 * cm, 'Minfiskerikontroll')
    canvas.setFont('Helvetica', 8)
    canvas.drawRightString(A4[0] - doc.rightMargin, A4[1] - 1.2 * cm, f"Anm.nr {str(getattr(doc, '_case_number', ''))}")
    canvas.drawString(doc.leftMargin, 0.9 * cm, f"Dokument generert {datetime.now().strftime('%d.%m.%Y %H:%M')}")
    canvas.drawRightString(A4[0] - doc.rightMargin, 0.9 * cm, f"Side {canvas.getPageNumber()}")
    canvas.restoreState()


def build_case_pdf(case_row: Dict[str, Any], evidence_rows: Iterable[Dict[str, Any]], output_dir: Path) -> Path:  # type: ignore[override]
    output_dir.mkdir(parents=True, exist_ok=True)
    filename = f"{str(case_row['case_number']).replace(' ', '_')}.pdf"
    outpath = output_dir / filename
    packet = build_case_packet(case_row, evidence_rows)
    styles = _story_styles_v21()
    doc = SimpleDocTemplate(str(outpath), pagesize=A4, leftMargin=1.4*cm, rightMargin=1.4*cm, topMargin=2.0*cm, bottomMargin=1.5*cm)
    doc._case_number = case_row.get('case_number') or ''
    story: list[Any] = []

    story.append(Paragraph(html.escape(packet['primary_document_title']), styles['title']))
    story.append(Paragraph(html.escape(packet['title']), styles['subtitle']))
    meta = packet['meta_rows']
    top_rows = meta[:16]
    story.append(_meta_table_v21(top_rows))
    story.append(Spacer(1, 0.3*cm))

    story.append(Paragraph('Beskrivelse', styles['section']))
    story.append(Paragraph(_format_text_for_pdf(packet['short_complaint']), styles['body']))

    story.append(Paragraph('Kontrollpunkter', styles['section']))
    story.append(_findings_table_v21(packet['findings']))

    story.append(Paragraph('Egenrapport', styles['section']))
    story.append(Paragraph(_format_text_for_pdf(packet['own_report']), styles['body']))

    story.append(Paragraph('Avhør / forklaring', styles['section']))
    story.append(Paragraph(_format_text_for_pdf(packet['interview_report']), styles['body']))

    story.append(Paragraph('Rapport om ransaking / beslag', styles['section']))
    story.append(Paragraph(_format_text_for_pdf(packet['seizure_report']), styles['body']))

    if packet.get('audio_files'):
        story.append(Paragraph('Lydvedlegg', styles['section']))
        for idx, item in enumerate(packet['audio_files'], start=1):
            label = str(item.get('original_filename') or item.get('filename') or f'Lyd {idx}').strip()
            story.append(Paragraph(_format_text_for_pdf(f"{idx}. {label}"), styles['body']))

    if packet.get('evidence'):
        story.append(PageBreak())
        story.append(Paragraph('Illustrasjonsrapport', styles['section']))
        for idx, item in enumerate(packet['evidence'], start=1):
            label = str(item.get('caption') or item.get('original_filename') or f'Illustrasjon {idx}').strip()
            refs = [str(item.get('seizure_ref') or '').strip(), str(item.get('violation_reason') or '').strip(), str(item.get('law_text') or '').strip()]
            refs = [r for r in refs if r]
            story.append(Paragraph(_format_text_for_pdf(label + (f" - {' | '.join(refs)}" if refs else '')), styles['body']))
            img_path = _image_path_for_evidence(item)
            if img_path and img_path.exists():
                try:
                    img = Image(str(img_path))
                    img._restrictSize(16.5 * cm, 11.5 * cm)
                    story.append(img)
                except Exception:
                    story.append(Paragraph('Kunne ikke vise bildefil i PDF.', styles['small']))
            story.append(Spacer(1, 0.25*cm))

    story.append(Spacer(1, 0.35*cm))
    story.append(Paragraph('Signaturer', styles['section']))
    story.append(_signatures_table_v21(case_row))

    doc.build(story, onFirstPage=_header_footer_v21, onLaterPages=_header_footer_v21)
    return outpath


def build_interview_only_pdf(case_row: Dict[str, Any], evidence_rows: Iterable[Dict[str, Any]], output_dir: Path) -> Path:  # type: ignore[override]
    output_dir.mkdir(parents=True, exist_ok=True)
    filename = f"{str(case_row['case_number']).replace(' ', '_')}_avhor.pdf"
    outpath = output_dir / filename
    styles = _story_styles_v21()
    doc = SimpleDocTemplate(str(outpath), pagesize=A4, leftMargin=1.4*cm, rightMargin=1.4*cm, topMargin=2.0*cm, bottomMargin=1.5*cm)
    doc._case_number = case_row.get('case_number') or ''
    story: list[Any] = []
    story.append(Paragraph('Avhørsrapport', styles['title']))
    story.append(Paragraph(html.escape(_offence_title(case_row, _safe_findings(case_row))), styles['subtitle']))
    story.append(_meta_table_v21([
        ('Saksnummer', _fmt_value(case_row.get('case_number'))),
        ('Avhørt', _fmt_value(case_row.get('suspect_name'))),
        ('Etterforsker', _fmt_value(case_row.get('investigator_name'))),
        ('Sted', _fmt_value(case_row.get('location_name'))),
        ('Tidsrom', f"{_fmt_datetime(case_row.get('start_time'))} - {_fmt_datetime(case_row.get('end_time'))}"),
        ('Signatur avhørt', _fmt_value(case_row.get('suspect_signature') or case_row.get('suspect_name'))),
    ]))
    story.append(Spacer(1, 0.25*cm))
    story.append(Paragraph(_format_text_for_pdf(_build_interview_report(case_row)), styles['body']))
    doc.build(story, onFirstPage=_header_footer_v21, onLaterPages=_header_footer_v21)
    return outpath

# --- v88: make the police-form/template renderer the primary PDF export again ---
# The simple ReportLab story renderer above is kept only as a safety fallback.  The
# main export must use the form backgrounds in app/pdf_templates so that the
# generated PDF follows the same document order/fields as the attached police forms.
_build_case_pdf_story_fallback_v88 = build_case_pdf
_build_interview_pdf_story_fallback_v88 = build_interview_only_pdf


def _required_template_pages_v88() -> list[str]:
    return [
        'page-01.png',  # Dokumentliste
        'page-02.png',  # Anmeldelse / hoveddokument
        'page-04.png',  # Egenrapport
        'page-05.png',  # Avhor forste side
        'page-06.png',  # Avhor fortsettelse
        'page-07.png',  # Ransaking/beslag
        'page-08.png',  # Illustrasjoner
    ]


def _template_pages_ready_v88() -> bool:
    try:
        return all((_TEMPLATE_DIR / name).exists() for name in _required_template_pages_v88())
    except Exception:
        return False


def _build_case_pdf_template_v88(case_row: Dict[str, Any], evidence_rows: Iterable[Dict[str, Any]], output_dir: Path) -> Path:
    if not _template_pages_ready_v88():
        missing = [name for name in _required_template_pages_v88() if not (_TEMPLATE_DIR / name).exists()]
        raise FileNotFoundError('Mangler PDF-malsider: ' + ', '.join(missing))

    output_dir.mkdir(parents=True, exist_ok=True)
    filename = f"{str(case_row['case_number']).replace(' ', '_')}.pdf"
    outpath = output_dir / filename
    packet = build_case_packet(case_row, evidence_rows)

    c = rl_canvas.Canvas(str(outpath), pagesize=A4)
    c.setTitle(f"Anmeldelsespakke {case_row['case_number']}")
    c.setAuthor(case_row.get('investigator_name') or 'Minfiskerikontroll')

    _draw_template(c, 'page-01.png')
    _header_meta_box(c, case_row, '01', 1, 1)
    _common_body_frame(c)
    _draw_document_list_body(c, case_row, packet)
    c.showPage()

    _draw_complaint_pages(c, case_row, packet)
    c.showPage()

    _draw_own_report_pages(c, case_row)
    c.showPage()

    _draw_interview_pages(c, case_row)
    c.showPage()

    seizure_doc_no = '04' if _interview_not_conducted(case_row) else '05'
    illustration_doc_no = '05' if _interview_not_conducted(case_row) else '06'
    _draw_seizure_page(c, case_row, packet, doc_number=seizure_doc_no)
    c.showPage()

    _draw_illustration_pages(c, case_row, packet, doc_number=illustration_doc_no)

    c.save()
    return outpath


def build_case_pdf(case_row: Dict[str, Any], evidence_rows: Iterable[Dict[str, Any]], output_dir: Path) -> Path:  # type: ignore[override]
    try:
        return _build_case_pdf_template_v88(case_row, evidence_rows, output_dir)
    except Exception:
        # Last-resort fallback: the app should return a PDF instead of a gateway/500
        # error even if a template asset is missing or a field overflows unexpectedly.
        try:
            output_dir.mkdir(parents=True, exist_ok=True)
            broken = output_dir / f"{str(case_row.get('case_number') or 'sak').replace(' ', '_')}.pdf"
            if broken.exists() and broken.stat().st_size == 0:
                broken.unlink()
        except Exception:
            pass
        return _build_case_pdf_story_fallback_v88(case_row, evidence_rows, output_dir)


def _build_interview_only_pdf_template_v88(case_row: Dict[str, Any], evidence_rows: Iterable[Dict[str, Any]], output_dir: Path) -> Path:
    if not (_TEMPLATE_DIR / 'page-05.png').exists():
        raise FileNotFoundError('Mangler PDF-malside: page-05.png')
    output_dir.mkdir(parents=True, exist_ok=True)
    filename = f"{str(case_row['case_number']).replace(' ', '_')}_avhor.pdf"
    outpath = output_dir / filename
    c = rl_canvas.Canvas(str(outpath), pagesize=A4)
    c.setTitle(f"Avhorsrapport {case_row['case_number']}")
    c.setAuthor(case_row.get('investigator_name') or 'Minfiskerikontroll')
    _draw_interview_pages(c, case_row)
    c.save()
    return outpath


def build_interview_only_pdf(case_row: Dict[str, Any], evidence_rows: Iterable[Dict[str, Any]], output_dir: Path) -> Path:  # type: ignore[override]
    try:
        return _build_interview_only_pdf_template_v88(case_row, evidence_rows, output_dir)
    except Exception:
        return _build_interview_pdf_story_fallback_v88(case_row, evidence_rows, output_dir)

# --- v91: interview safeguards, illustration ordering, detailed map and no-empty interview report ---
_build_own_report_before_v91 = _build_own_report
_build_interview_report_before_v91 = _build_interview_report
_build_case_packet_before_v91 = build_case_packet
_build_text_drafts_before_v91 = build_text_drafts
_build_summary_before_v91 = build_summary


def _v91_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    try:
        return int(value or 0) == 1
    except Exception:
        return str(value or '').strip().lower() in {'1', 'true', 'yes', 'on'}


def _interview_not_conducted(case_row: Dict[str, Any]) -> bool:
    return _v91_bool(case_row.get('interview_not_conducted'))


def _interview_not_conducted_reason(case_row: Dict[str, Any]) -> str:
    return str(case_row.get('interview_not_conducted_reason') or 'Ikke fått kontakt med vedkommende.').strip() or 'Ikke fått kontakt med vedkommende.'


def _finding_label_v91(item: Dict[str, Any], idx: int = 0) -> str:
    return str(item.get('label') or item.get('key') or (f'kontrollpunkt {idx}' if idx else 'kontrollpunkt')).strip()


def _build_interview_guidance_v91(case_row: Dict[str, Any], findings: list[Dict[str, Any]]) -> str:
    override = str(case_row.get('interview_guidance_text') or '').strip()
    if override:
        return override
    avvik = [item for item in findings if str(item.get('status') or '').strip().lower() == 'avvik']
    rows: list[str] = [
        'Innledende punkter før forklaring:',
        '- Avklar identitet, rolle og tilknytning til person, fartøy, redskap og kontrollposisjon.',
        '- Forklar kort hva saken gjelder, hvilke observasjoner som er gjort, og hvilke dokumenter/bilder som eventuelt forevises.',
        '- Dersom personen avhøres som mistenkt: noter at vedkommende er gjort kjent med rollen i saken, at forklaring er frivillig, og at vedkommende kan rådføre seg med forsvarer. Noter om orienteringen er forstått.',
        '- La personen forklare seg fritt før konkrete spørsmål om de enkelte avvikene.',
        '',
        'Spørsmål knyttet til registrerte avvik:',
    ]
    if not avvik:
        rows.append('- Ingen avvik er registrert i kontrollpunktene. Vurder om forklaring likevel er nødvendig for å klargjøre faktum.')
    for idx, item in enumerate(avvik, start=1):
        label = _finding_label_v91(item, idx)
        note = str(item.get('notes') or item.get('auto_note') or item.get('summary_text') or '').strip()
        law = str(item.get('law_text') or item.get('help_text') or item.get('source_ref') or '').strip()
        rows.append(f'{idx}. {label}')
        if note:
            rows.append(f'   Observasjon/foreløpig vurdering: {note}')
        if law:
            rows.append(f'   Regel-/hjemmelstekst i saken: {law}')
        rows.extend([
            '   Spørsmål: Forklar din tilknytning til redskapet/aktiviteten og hvem som har satt eller brukt dette.',
            '   Spørsmål: Når og hvor ble redskapet/aktiviteten satt ut eller gjennomført?',
            '   Spørsmål: Hvilke regler, stengte felt, fredningsområder, merkekrav eller tillatelser var du kjent med?',
            '   Spørsmål: Finnes det registrering, tillatelse, kvittering, sporingsdata, bilder eller annen dokumentasjon som bør legges frem?',
        ])
        for dev in item.get('deviation_units') or []:
            if not isinstance(dev, dict):
                continue
            ref = str(dev.get('seizure_ref') or dev.get('gear_ref') or '').strip()
            violation = str(dev.get('violation') or '').strip()
            if ref or violation:
                rows.append(f'   Beslag/ref {ref or "-"}: {violation or "avvik registrert"}. Be om forklaring på eierskap, bruk og hendelsesforløp.')
    rows.extend(['', 'Avslutning:', '- Gå gjennom sammendraget og noter om forklaringen godtas, korrigeres eller nektes signert.', '- Noter om personen ønsker å legge frem dokumentasjon eller komme med merknader.'])
    return '\n'.join(rows).strip()


def _is_ocr_source_evidence(item: Dict[str, Any]) -> bool:
    caption = str(item.get('caption') or item.get('original_filename') or '').strip().lower()
    return caption.startswith('ocr-kilde') or 'ocr' in str(item.get('finding_key') or '').strip().lower()


def _seizure_sort_number(value: Any) -> tuple[int, str]:
    raw = str(value or '').strip()
    # Sort primarily on the running seizure number at the end, e.g.
    # LBHN 26 003-001 or LBHN 26 003 - Måling -001 -> 1.
    match = re.search(r'[- ](\d{1,4})\s*$', raw)
    if not match:
        match = re.search(r'(\d+)', raw)
    if match:
        try:
            return (int(match.group(1)), raw)
        except Exception:
            pass
    return (999999, raw)


def _evidence_manual_order_value(item: Dict[str, Any], fallback_index: int = 0) -> int:
    try:
        value = int(item.get('display_order'))
        if value > 0:
            return value
    except Exception:
        pass
    try:
        value = int(item.get('id'))
        if value > 0:
            return value * 10
    except Exception:
        pass
    raw_date = str(item.get('created_at') or '').strip()
    if raw_date:
        try:
            return 1000000 + int(datetime.fromisoformat(raw_date.replace('Z', '+00:00')).timestamp())
        except Exception:
            pass
    return 900000000 + fallback_index


def _sort_evidence_rows_v91(rows: list[Dict[str, Any]]) -> list[Dict[str, Any]]:
    indexed = [(idx, dict(item)) for idx, item in enumerate(rows or [])]

    def key(pair: tuple[int, Dict[str, Any]]) -> tuple[int, int, str, int]:
        idx, item = pair
        fk = str(item.get('finding_key') or '').strip().lower()
        caption = str(item.get('caption') or '').strip().lower()
        if fk == 'oversiktskart':
            radius_rank = 0 if '50' in caption else 1
            return (0, radius_rank, caption, idx)
        return (1, _evidence_manual_order_value(item, idx), caption, idx)

    return [item for _, item in sorted(indexed, key=key)]


def _build_own_report(case_row: Dict[str, Any], findings: list[Dict[str, Any]]) -> str:  # type: ignore[override]
    if str(case_row.get('own_report_override') or '').strip():
        return str(case_row.get('own_report_override') or '').strip()
    base = _build_own_report_before_v91(case_row, findings)
    formal_intro = 'Rapporten gjelder kontroll utført som ledd i fiskerioppsyn. Formålet var å klarlegge faktum, sikre notoritet rundt observasjoner og dokumentere vurderinger knyttet til etterlevelse av aktuelt regelverk.'
    if formal_intro.lower() not in base.lower():
        base = formal_intro + '\n\n' + base
    if _interview_not_conducted(case_row):
        base += '\n\nAvhør/forklaring er ikke gjennomført. Registrert årsak: ' + _interview_not_conducted_reason(case_row)
    return base.strip()


def _build_interview_report(case_row: Dict[str, Any]) -> str:  # type: ignore[override]
    if _interview_not_conducted(case_row):
        return ''
    return _build_interview_report_before_v91(case_row)


def build_summary(case_row: Dict[str, Any], findings: list[Dict[str, Any]]) -> str:  # type: ignore[override]
    avvik = [item for item in findings if str(item.get('status') or '').strip().lower() == 'avvik']
    when = _fmt_datetime(case_row.get('start_time'))
    location = _location_line(case_row)
    subject = str(case_row.get('suspect_name') or 'kontrollobjektet').strip()
    control_theme = _control_theme(case_row) or 'kontrolltema'
    rows = [
        f'Den {when} ble det gjennomført kontroll ved {location}.',
        f'Kontrollen gjaldt {control_theme.lower()} og omfattet {subject}.',
    ]
    if case_row.get('area_status') or case_row.get('area_name'):
        rows.append(f"Kontrollstedet er registrert i/ved {str(case_row.get('area_name') or case_row.get('location_name') or 'kontrollposisjon').strip()} ({str(case_row.get('area_status') or 'områdestatus ikke angitt').strip()}).")
    if avvik:
        rows.append('Følgende avvik/funn er registrert for videre vurdering:')
        for idx, item in enumerate(avvik, start=1):
            note = str(item.get('notes') or item.get('auto_note') or item.get('summary_text') or '').strip()
            rows.append(f'{idx}. {_finding_label_v91(item, idx)}' + (f' - {note}' if note else '.'))
    else:
        rows.append('Det er ikke registrert avvik i kontrollpunktene på tidspunktet for oppsummeringen.')
    if _interview_not_conducted(case_row):
        rows.append('Avhør/forklaring er ikke gjennomført. Registrert årsak: ' + _interview_not_conducted_reason(case_row))
    return '\n'.join(rows).strip()


def build_text_drafts(case_row: Dict[str, Any], findings: list[Dict[str, Any]]) -> Dict[str, str]:  # type: ignore[override]
    drafts = _build_text_drafts_before_v91(case_row, findings)
    drafts['summary'] = build_summary(case_row, findings)
    if not str(drafts.get('basis_details') or '').strip():
        theme = _control_theme(case_row) or 'aktuelt kontrolltema'
        drafts['basis_details'] = f'Det ble iverksatt fiskerikontroll for å klarlegge faktiske forhold og kontrollere etterlevelse av regelverk knyttet til {theme.lower()}.'
    drafts['notes'] = _build_own_report(case_row, findings)
    return drafts


def _add_v91_map_items(case_row: Dict[str, Any], evidence_rows: list[Dict[str, Any]]) -> list[Dict[str, Any]]:
    maps: list[Dict[str, Any]] = []
    for radius in (50.0, 5.0):
        try:
            item = _generate_overview_map_image(case_row, GENERATED_DIR, radius_km=radius)
            if item:
                if radius <= 10:
                    item['caption'] = f'Nærkart kontrollposisjon (ca. {int(round(radius))} km radius)'
                    item['violation_reason'] = f'Automatisk generert nærkart med mer detaljert utsnitt rundt kontrollstedet i ca. {int(round(radius))} km radius.'
                maps.append(item)
        except Exception:
            continue
    # Remove any map item already inserted by the previous packet builder before replacing order.
    non_maps = [dict(item) for item in evidence_rows if str(item.get('finding_key') or '').strip().lower() != 'oversiktskart']
    return _sort_evidence_rows_v91(maps + non_maps)


def build_case_packet(case_row: Dict[str, Any], evidence_rows: Iterable[Dict[str, Any]]) -> Dict[str, Any]:  # type: ignore[override]
    packet = _build_case_packet_before_v91(case_row, evidence_rows)
    findings = [dict(item, display_notes=_finding_display_note(item)) for item in _safe_findings(case_row)]
    all_evidence_rows = list(evidence_rows)
    audio_rows = [dict(item) for item in all_evidence_rows if str(item.get('mime_type') or '').startswith('audio/')]
    image_rows = [dict(item) for item in all_evidence_rows if not str(item.get('mime_type') or '').startswith('audio/')]
    image_rows = _add_v91_map_items(case_row, image_rows)
    packet['evidence'] = image_rows
    packet['audio_files'] = audio_rows
    packet['illustration_texts'] = _build_illustration_texts(image_rows)
    packet['own_report'] = _build_own_report(case_row, findings)
    packet['interview_not_conducted'] = _interview_not_conducted(case_row)
    packet['interview_not_conducted_reason'] = _interview_not_conducted_reason(case_row)
    packet['interview_guidance'] = ''  # 1.8.23: interne forslag skal ikke inn i anmeldelse/dokumentpakke
    if _interview_not_conducted(case_row):
        packet['interview_report'] = ''
        docs = [dict(doc) for doc in packet.get('documents', []) if 'avhør' not in str(doc.get('title') or '').lower()]
        for idx, doc in enumerate(docs, start=1):
            doc['number'] = f'{idx:02d}'
        packet['documents'] = docs
    else:
        packet['interview_report'] = _build_interview_report(case_row)
    packet['summary'] = build_summary(case_row, findings)
    return packet


def _build_case_pdf_template_v91(case_row: Dict[str, Any], evidence_rows: Iterable[Dict[str, Any]], output_dir: Path) -> Path:
    if not _template_pages_ready_v88():
        missing = [name for name in _required_template_pages_v88() if not (_TEMPLATE_DIR / name).exists()]
        raise FileNotFoundError('Mangler PDF-malsider: ' + ', '.join(missing))
    output_dir.mkdir(parents=True, exist_ok=True)
    filename = f"{str(case_row['case_number']).replace(' ', '_')}.pdf"
    outpath = output_dir / filename
    packet = build_case_packet(case_row, evidence_rows)

    c = rl_canvas.Canvas(str(outpath), pagesize=A4)
    c.setTitle(f"Anmeldelsespakke {case_row['case_number']}")
    c.setAuthor(case_row.get('investigator_name') or 'Minfiskerikontroll')

    _draw_template(c, 'page-01.png')
    _header_meta_box(c, case_row, '01', 1, 1)
    _common_body_frame(c)
    _draw_document_list_body(c, case_row, packet)
    c.showPage()

    _draw_complaint_pages(c, case_row, packet)
    c.showPage()

    _draw_own_report_pages(c, case_row)
    c.showPage()

    if not _interview_not_conducted(case_row):
        _draw_interview_pages(c, case_row)
        c.showPage()

    seizure_doc_no = '04' if _interview_not_conducted(case_row) else '05'
    illustration_doc_no = '05' if _interview_not_conducted(case_row) else '06'
    _draw_seizure_page(c, case_row, packet, doc_number=seizure_doc_no)
    c.showPage()

    _draw_illustration_pages(c, case_row, packet, doc_number=illustration_doc_no)
    c.save()
    return outpath


def build_case_pdf(case_row: Dict[str, Any], evidence_rows: Iterable[Dict[str, Any]], output_dir: Path) -> Path:  # type: ignore[override]
    try:
        return _build_case_pdf_template_v91(case_row, evidence_rows, output_dir)
    except Exception:
        return _build_case_pdf_story_fallback_v88(case_row, evidence_rows, output_dir)


def build_interview_only_pdf(case_row: Dict[str, Any], evidence_rows: Iterable[Dict[str, Any]], output_dir: Path) -> Path:  # type: ignore[override]
    if _interview_not_conducted(case_row):
        output_dir.mkdir(parents=True, exist_ok=True)
        filename = f"{str(case_row['case_number']).replace(' ', '_')}_avhor_ikke_gjennomfort.pdf"
        outpath = output_dir / filename
        doc = SimpleDocTemplate(str(outpath), pagesize=A4, leftMargin=1.6*cm, rightMargin=1.6*cm, topMargin=2.0*cm, bottomMargin=1.5*cm)
        styles = _story_styles_v21()
        story = [Paragraph('Avhør ikke gjennomført', styles['title']), Paragraph(_format_text_for_pdf(_interview_not_conducted_reason(case_row)), styles['body'])]
        doc.build(story, onFirstPage=_header_footer_v21, onLaterPages=_header_footer_v21)
        return outpath
    try:
        return _build_interview_only_pdf_template_v88(case_row, evidence_rows, output_dir)
    except Exception:
        return _build_interview_pdf_story_fallback_v88(case_row, evidence_rows, output_dir)


# ---- v93: formal standard text, seizure rows from form state, signed-by labels ----
_build_case_packet_before_v93 = build_case_packet
_build_text_drafts_before_v93 = build_text_drafts
_build_summary_before_v93 = build_summary
_build_own_report_before_v93 = _build_own_report
_build_seizure_report_before_v93 = _build_seizure_report
_draw_seizure_page_before_v93 = _draw_seizure_page
_build_case_pdf_before_v93 = build_case_pdf
_build_interview_only_pdf_before_v93 = build_interview_only_pdf


def _parse_json_list_v93(raw: Any) -> list[Dict[str, Any]]:
    try:
        data = json.loads(str(raw or '[]'))
        if isinstance(data, list):
            return [row for row in data if isinstance(row, dict)]
    except Exception:
        pass
    return []


def _signature_display_v93(value: Any, fallback_name: Any = '') -> str:
    raw = str(value or '').strip()
    fallback = str(fallback_name or '').strip()
    if not raw:
        return fallback or ''
    try:
        data = json.loads(raw)
        if isinstance(data, dict):
            name = str(data.get('name') or fallback or '').strip()
            signed = str(data.get('signed_at') or '').strip()
            if signed:
                return f'{name or "Signatur"} - elektronisk signert {signed[:19].replace("T", " ")}'
            if name:
                return f'{name} - elektronisk signert'
    except Exception:
        pass
    return raw


def _case_row_signature_labels_v93(case_row: Dict[str, Any]) -> Dict[str, Any]:
    row = dict(case_row)
    for field, name_field in (
        ('complainant_signature', 'complainant_name'),
        ('witness_signature', 'witness_name'),
        ('investigator_signature', 'investigator_name'),
        ('suspect_signature', 'suspect_name'),
    ):
        row[field] = _signature_display_v93(row.get(field), row.get(name_field))
    return row


def _control_subject_v93(case_row: Dict[str, Any]) -> str:
    parts = [case_row.get('control_type'), case_row.get('species') or case_row.get('fishery_type'), case_row.get('gear_type')]
    return ' / '.join([str(x).strip() for x in parts if str(x or '').strip()]) or 'fiskerikontroll'


def build_control_reason(case_row: Dict[str, Any], findings: list[Dict[str, Any]]) -> str:  # type: ignore[override]
    override = str(case_row.get('basis_details') or '').strip()
    # Keep user text only if it does not contain previous unwanted formulae.
    banned = ('anmeldelsesegnet' + ' form', 'tidligere registrerte ' + 'opplysninger i saken', 'kyst' + 'vakten', 'kyst' + 'vakt')
    if override and not any(word in override.lower() for word in banned):
        return override
    when = _fmt_datetime(case_row.get('start_time'))
    location = _location_line(case_row)
    theme = _control_subject_v93(case_row).lower()
    area = str(case_row.get('area_name') or case_row.get('area_status') or '').strip()
    text = f'Den {when} ble det gjennomført stedlig fiskerikontroll ved {location}. Patruljen var rettet mot {theme}. Formålet var å kontrollere observerbare forhold på stedet, herunder kontrollsted, redskap, merking, fangst/oppbevaring, ansvarlig bruker/eier og øvrige kontrollpunkter som var relevante for valgt fiskeri.'
    if area:
        text += f' Kontrollstedet ble vurdert opp mot registrert områdestatus for {area}.'
    return text


def _persons_summary_v93(case_row: Dict[str, Any]) -> list[str]:
    rows: list[str] = []
    if case_row.get('suspect_name'):
        rows.append(f"Mistenkt/kontrollert: {_fmt_value(case_row.get('suspect_name'))}")
    for item in _parse_json_list_v93(case_row.get('persons_json')):
        name = str(item.get('name') or '').strip()
        if not name:
            continue
        role = str(item.get('role') or 'Person').strip()
        phone = str(item.get('phone') or '').strip()
        birth = str(item.get('birthdate') or '').strip()
        relation = str(item.get('relation') or '').strip()
        detail = ', '.join([x for x in [phone, birth, relation] if x])
        rows.append(f'{role}: {name}' + (f' ({detail})' if detail else ''))
    return rows


def _stored_seizure_rows_v93(case_row: Dict[str, Any], findings: list[Dict[str, Any]], evidence_rows: Iterable[Dict[str, Any]]) -> list[Dict[str, Any]]:
    stored = _parse_json_list_v93(case_row.get('seizure_reports_json'))
    generated = _collect_seizure_rows_from_findings(findings)
    result: list[Dict[str, Any]] = []
    by_key: dict[str, Dict[str, Any]] = {}
    for row in stored + generated:
        key = str(row.get('source_key') or row.get('seizure_ref') or row.get('caption') or len(result)).strip()
        if key in by_key:
            by_key[key].update({k: v for k, v in row.items() if v not in (None, '', [])})
        else:
            clone = dict(row)
            by_key[key] = clone
            result.append(clone)
    for ev in evidence_rows or []:
        ref = str((ev or {}).get('seizure_ref') or '').strip()
        if not ref:
            continue
        target = None
        for row in result:
            if str(row.get('seizure_ref') or '').strip() == ref:
                target = row
                break
        if target is None:
            target = {'seizure_ref': ref, 'type': 'Bildebevis', 'description': str((ev or {}).get('caption') or (ev or {}).get('original_filename') or '').strip()}
            result.append(target)
        target.setdefault('evidence_refs', [])
        try:
            target['evidence_refs'].append(str((ev or {}).get('caption') or (ev or {}).get('original_filename') or (ev or {}).get('id') or 'bilde'))
        except Exception:
            pass
    return result


def _build_seizure_report(case_row: Dict[str, Any], evidence_rows: list[Dict[str, Any]]) -> str:  # type: ignore[override]
    rows = _stored_seizure_rows_v93(case_row, _safe_findings(case_row), evidence_rows)
    override = str(case_row.get('seizure_report_override') or '').strip()
    if not rows and not override:
        return 'Det er ikke registrert beslag i saken.'
    lines = ['Beslagsrapport', '', f'Sted/posisjon: {_location_line(case_row)}.', f'Ledet av: {_fmt_value(case_row.get("investigator_name"))}.']
    if rows:
        lines.extend(['', 'Registrerte beslag/bevis:'])
        for idx, row in enumerate(rows, start=1):
            desc = str(row.get('description') or row.get('violation_reason') or row.get('type') or 'Registrert beslag/avvik').strip()
            law = str(row.get('law_text') or '').strip()
            ev = ', '.join([str(x) for x in row.get('evidence_refs') or [] if str(x).strip()])
            lines.append(f'{idx}. {row.get("seizure_ref") or "Beslag"}: {desc}')
            if row.get('quantity'):
                lines.append(f'   Antall: {row.get("quantity")}')
            if row.get('position'):
                lines.append(f'   Posisjon: {row.get("position")}')
            if law:
                lines.append(f'   Hjemmel/kontrollpunkt: {law}')
            if ev:
                lines.append(f'   Tilknyttede bilder: {ev}')
    if override:
        lines.extend(['', 'Utfyllende merknader:', override])
    return '\n'.join(lines).strip()


def build_summary(case_row: Dict[str, Any], findings: list[Dict[str, Any]]) -> str:  # type: ignore[override]
    avvik = [item for item in findings if str(item.get('status') or '').strip().lower() == 'avvik']
    when = _fmt_datetime(case_row.get('start_time'))
    location = _location_line(case_row)
    lines = [
        'Oppsummering / anmeldelsesgrunnlag',
        '',
        f'1. Tid og sted: Den {when} ble det gjennomført kontroll ved {location}.',
        f'2. Kontrolltema: Kontrollen gjaldt {_control_subject_v93(case_row).lower()}.',
        f'3. Patruljeformål: {build_control_reason(case_row, findings)}',
    ]
    people = _persons_summary_v93(case_row)
    if people:
        lines.extend(['', '4. Personer i saken:'])
        for idx, row in enumerate(people, start=1):
            lines.append(f'{idx}. {row}')
    if case_row.get('area_status') or case_row.get('area_name'):
        lines.extend(['', '5. Område/posisjon:'])
        lines.append(f"Kontrollstedet er registrert i/ved {str(case_row.get('area_name') or case_row.get('location_name') or 'kontrollposisjon').strip()} ({str(case_row.get('area_status') or 'områdestatus ikke angitt').strip()}).")
    lines.extend(['', '6. Registrerte kontrollpunkter og avvik:'])
    if avvik:
        for idx, item in enumerate(avvik, start=1):
            note = str(item.get('notes') or item.get('auto_note') or item.get('summary_text') or '').strip()
            lines.append(f'{idx}. {_finding_label_v91(item, idx)}' + (f' - {note}' if note else '.'))
    else:
        lines.append('Det er ikke registrert avvik i kontrollpunktene på tidspunktet for oppsummeringen.')
    seizures = _stored_seizure_rows_v93(case_row, findings, [])
    if seizures:
        lines.extend(['', '7. Beslag/bevis:'])
        for idx, row in enumerate(seizures, start=1):
            lines.append(f'{idx}. {row.get("seizure_ref") or "Beslag"}: {row.get("description") or row.get("violation_reason") or row.get("type") or "registrert beslag/avvik"}.')
    if _interview_not_conducted(case_row):
        lines.extend(['', '8. Avhør/forklaring:'])
        lines.append('Avhør/forklaring er ikke gjennomført. Registrert årsak: ' + _interview_not_conducted_reason(case_row))
    return '\n'.join(lines).strip()


def _build_own_report(case_row: Dict[str, Any], findings: list[Dict[str, Any]]) -> str:  # type: ignore[override]
    override = str(case_row.get('own_report_override') or '').strip()
    if override:
        return override
    lines = [
        'Egenrapport',
        '',
        build_control_reason(case_row, findings),
        '',
        f'Kontrollsted: {_location_line(case_row)}.',
        f'Kontrolltema: {_control_subject_v93(case_row)}.',
    ]
    people = _persons_summary_v93(case_row)
    if people:
        lines.extend(['', 'Personer i saken:'] + [f'- {row}' for row in people])
    avvik = [item for item in findings if str(item.get('status') or '').strip().lower() == 'avvik']
    if avvik:
        lines.extend(['', 'Registrerte funn/avvik:'])
        for idx, item in enumerate(avvik, start=1):
            note = _finding_display_note(item) or str(item.get('summary_text') or '').strip() or 'Registrert i kontrollpunkt.'
            lines.append(f'{idx}. {_finding_label_v91(item, idx)} - {note}')
    else:
        lines.extend(['', 'Det er ikke registrert avvik i kontrollpunktene på tidspunktet for rapportutkastet.'])
    if _interview_not_conducted(case_row):
        lines.extend(['', 'Avhør/forklaring er ikke gjennomført. Registrert årsak: ' + _interview_not_conducted_reason(case_row)])
    return '\n'.join(lines).strip()


def build_text_drafts(case_row: Dict[str, Any], findings: list[Dict[str, Any]]) -> Dict[str, str]:  # type: ignore[override]
    summary_text = build_summary(case_row, findings)
    return {
        'summary': summary_text,
        'basis_details': build_control_reason(case_row, findings),
        'notes': _build_own_report(case_row, findings),
        'complaint_preview': summary_text,
    }


def build_case_packet(case_row: Dict[str, Any], evidence_rows: Iterable[Dict[str, Any]]) -> Dict[str, Any]:  # type: ignore[override]
    all_evidence_rows = list(evidence_rows)
    packet = _build_case_packet_before_v93(case_row, all_evidence_rows)
    findings = [dict(item, display_notes=_finding_display_note(item)) for item in _safe_findings(case_row)]
    seizure_rows = _stored_seizure_rows_v93(case_row, findings, list(packet.get('evidence') or all_evidence_rows))
    packet['summary'] = build_summary(case_row, findings)
    packet['short_complaint'] = packet['summary']
    packet['own_report'] = _build_own_report(case_row, findings)
    packet['seizure_rows'] = seizure_rows
    packet['seizure_report'] = _build_seizure_report(case_row, list(packet.get('evidence') or all_evidence_rows))
    packet['persons'] = _persons_summary_v93(case_row)
    return packet


def _draw_seizure_page(c: rl_canvas.Canvas, case_row: Dict[str, Any], packet: Dict[str, Any], doc_number: str = '05') -> None:  # type: ignore[override]
    _draw_template(c, 'page-07.png')
    _header_meta_box(c, case_row, str(doc_number or '05'), 1, 1)
    _common_body_frame(c)
    compact_bottom = _draw_sak_section_compact(c, case_row, 302)
    y = compact_bottom + 10
    _draw_section_caption(c, 118, y, 1128, y + 28, 'Mistenkt / kontrollert person')
    _draw_label_value(c, 118, y + 28, 808, y + 68, 'Navn', _fmt_value(case_row.get('suspect_name')))
    _draw_label_value(c, 808, y + 28, 1128, y + 68, 'Fødselsnr.', _fmt_value(case_row.get('suspect_birthdate')))
    y += 68
    _draw_section_caption(c, 118, y, 1128, y + 28, 'Beslag / bevis')
    _draw_label_value(c, 118, y + 28, 640, y + 96, 'Grunnlag', _offence_title(case_row, _safe_findings(case_row)))
    _draw_label_value(c, 640, y + 28, 890, y + 96, 'Fra rett/påtalemyndighet', '')
    _draw_label_value(c, 890, y + 28, 1128, y + 96, 'Samtykke gitt av', '')
    _draw_label_value(c, 118, y + 96, 440, y + 140, 'Beslag dato klokkeslett', _fmt_datetime_packet(case_row.get('end_time') or case_row.get('start_time')))
    _draw_label_value(c, 440, y + 96, 808, y + 140, 'Ledet av', _fmt_value(case_row.get('investigator_name')))
    _draw_label_value(c, 808, y + 96, 1128, y + 140, 'Tjenestested', _service_unit(case_row))
    _draw_label_value(c, 118, y + 140, 1128, y + 176, 'Observatør/vitne', _fmt_value(case_row.get('witness_name')))
    _draw_label_value(c, 118, y + 176, 1128, y + 214, 'Andre tilstedeværende', '; '.join(_persons_summary_v93(case_row))[:260])
    _draw_label_value(c, 118, y + 214, 640, y + 252, 'Sted/posisjon', _location_line(case_row))
    _draw_label_value(c, 640, y + 214, 1128, y + 252, 'Område', _fmt_value(case_row.get('area_name') or case_row.get('area_status')))
    _draw_label_value(c, 118, y + 252, 1128, y + 316, 'Merknader', _fmt_value(case_row.get('seizure_notes') or case_row.get('seizure_report_override')))
    table_top = y + 316
    _draw_section_caption(c, 118, table_top, 1128, table_top + 28, f'Beslaglagte gjenstander    Beslag journal nr.{_fmt_value(case_row.get("case_number"))}')
    rows = list(packet.get('seizure_rows') or []) or [{'seizure_ref': 'Ingen beslag registrert', 'quantity': '', 'type': '', 'description': ''}]
    row_y = table_top + 28
    cols = [118, 190, 320, 410, 560, 720, 1128]
    headers = ['Løpenr.', 'Lok.besl. nr', 'Antall', 'ID', 'Oppbevart', 'Type/beskrivelse / hvor funnet']
    for i in range(len(cols) - 1):
        _draw_label_value(c, cols[i], row_y, cols[i + 1], row_y + 34, headers[i], '')
    row_y += 34
    for idx, row in enumerate(rows[:5], start=1):
        where = str(row.get('position') or '').strip()
        if not where and case_row.get('latitude') is not None and case_row.get('longitude') is not None:
            where = _case_utm(case_row) or 'DMS ikke beregnet'
        desc = str(row.get('description') or row.get('violation_reason') or row.get('caption') or row.get('type') or '').strip()
        if row.get('law_text'):
            desc += '\n' + str(row.get('law_text')).strip()[:180]
        if where:
            desc += '\nSted: ' + where
        values = [str(idx), str(row.get('seizure_ref') or idx), str(row.get('quantity') or '1'), str(idx), 'Oppbevart', desc]
        for i in range(len(cols) - 1):
            _draw_label_value(c, cols[i], row_y, cols[i + 1], row_y + 64, '', values[i], value_size=7.7)
        row_y += 64
        if row_y > 1490:
            break
    _draw_label_value(c, 118, 1538, 623, 1604, 'Leders underskrift', _signature_display_v93(case_row.get('investigator_signature'), case_row.get('investigator_name')))
    _draw_label_value(c, 623, 1538, 1128, 1604, 'Observatør/vitnes underskrift', _signature_display_v93(case_row.get('witness_signature'), case_row.get('witness_name')))


def build_case_pdf(case_row: Dict[str, Any], evidence_rows: Iterable[Dict[str, Any]], output_dir: Path) -> Path:  # type: ignore[override]
    return _build_case_pdf_before_v93(_case_row_signature_labels_v93(case_row), evidence_rows, output_dir)


def build_interview_only_pdf(case_row: Dict[str, Any], evidence_rows: Iterable[Dict[str, Any]], output_dir: Path) -> Path:  # type: ignore[override]
    return _build_interview_only_pdf_before_v93(_case_row_signature_labels_v93(case_row), evidence_rows, output_dir)

# ---- v94: draw touch signatures and keep visible report fields focused ----
def _signature_parts_v94(value: Any, fallback_name: Any = '') -> tuple[str, str]:
    raw = str(value or '').strip()
    fallback = str(fallback_name or '').strip()
    if not raw:
        return (fallback + ' - ikke signert') if fallback else 'Ikke signert', ''
    try:
        data = json.loads(raw)
        if isinstance(data, dict):
            name = str(data.get('name') or fallback or 'Signatur').strip()
            signed_at = str(data.get('signed_at') or '').strip()
            image = str(data.get('image') or '').strip()
            display = f'{name} - elektronisk signert'
            if signed_at:
                display += ' ' + _fmt_datetime(signed_at)
            return display, image
    except Exception:
        pass
    return raw, ''


def _case_row_signature_labels_v94(case_row: Dict[str, Any]) -> Dict[str, Any]:
    row = dict(case_row)
    mapping = {
        'complainant_signature': 'complainant_name',
        'witness_signature': 'witness_name',
        'investigator_signature': 'investigator_name',
        'suspect_signature': 'suspect_name',
    }
    for field, name_field in mapping.items():
        display, image = _signature_parts_v94(row.get(field), row.get(name_field))
        row[field] = display
        if image:
            row[field + '_image'] = image
    return row


def _draw_signature_image_fit_v94(c: rl_canvas.Canvas, image_data: Any, l: float, t: float, r: float, b: float) -> bool:
    raw = str(image_data or '').strip()
    if not raw:
        return False
    try:
        import base64
        if ',' in raw and raw.lower().startswith('data:image'):
            raw = raw.split(',', 1)[1]
        blob = base64.b64decode(raw, validate=False)
        reader = ImageReader(io.BytesIO(blob))
        iw, ih = reader.getSize()
        if not iw or not ih:
            return False
        x, y, w, h = _pt_rect(l, t, r, b)
        pad = 4
        w = max(1, w - 2 * pad)
        h = max(1, h - 2 * pad)
        scale = min(w / float(iw), h / float(ih))
        dw, dh = float(iw) * scale, float(ih) * scale
        dx = x + pad + (w - dw) / 2.0
        dy = y + pad + (h - dh) / 2.0
        c.drawImage(reader, dx, dy, width=dw, height=dh, preserveAspectRatio=True, mask='auto')
        return True
    except Exception:
        return False


def _draw_signature_box_v94(
    c: rl_canvas.Canvas,
    l: float,
    t: float,
    r: float,
    b: float,
    label: str,
    case_row: Dict[str, Any],
    field: str,
    fallback_name: Any = '',
) -> None:
    display, parsed_image = _signature_parts_v94(case_row.get(field), fallback_name)
    image_data = case_row.get(field + '_image') or parsed_image
    _stroke_box_px(c, l, t, r, b)
    _draw_text_px(c, label, l + 2, t + 1, r - 2, t + 15, font_name='Helvetica-Bold', font_size=6.8, leading=7.6)
    _draw_text_px(c, display, l + 2, t + 15, r - 2, t + 30, font_name='Helvetica', font_size=7.2, leading=8.0)
    if image_data:
        _draw_signature_image_fit_v94(c, image_data, l + 8, t + 31, r - 8, b - 6)


def _draw_interview_pages(c: rl_canvas.Canvas, case_row: Dict[str, Any]) -> None:  # type: ignore[override]
    full_text = _build_interview_report(case_row)
    first_box_l, first_box_t, first_box_r, first_box_b = 124, 610, 1122, 1478
    cont_box_l, cont_box_t, cont_box_r, cont_box_b = 124, 448, 1122, 1478
    pages: list[tuple[str, str]] = []
    fit, rest = _split_text_for_box(full_text, 'Helvetica', 8.4, 10.0, _pt_rect(first_box_l, first_box_t, first_box_r, first_box_b)[2], _pt_rect(first_box_l, first_box_t, first_box_r, first_box_b)[3])
    pages.append(('first', fit))
    remaining = rest
    while remaining:
        fit, rest = _split_text_for_box(remaining, 'Helvetica', 8.4, 10.0, _pt_rect(cont_box_l, cont_box_t, cont_box_r, cont_box_b)[2], _pt_rect(cont_box_l, cont_box_t, cont_box_r, cont_box_b)[3])
        pages.append(('cont', fit))
        remaining = rest
    total = len(pages)
    for idx, (kind, text) in enumerate(pages, start=1):
        _draw_template(c, 'page-05.png' if kind == 'first' else 'page-06.png')
        _header_meta_box(c, case_row, '04', idx, total)
        _common_body_frame(c)
        compact_bottom = _draw_sak_section_compact(c, case_row, 302)
        if kind == 'first':
            top = compact_bottom + 10
            _draw_label_value(c, 118, top, 640, top + 120, 'Avhørt', '\n'.join(_non_empty(case_row.get('suspect_name'), case_row.get('suspect_birthdate'), case_row.get('suspect_address'), case_row.get('suspect_phone'))))
            _draw_label_value(c, 640, top, 1128, top + 120, 'Avhør / forklaring', '\n'.join(_non_empty('Sted: ' + _fmt_value(case_row.get('location_name')), 'Start: ' + _fmt_datetime_packet(case_row.get('start_time')), 'Slutt: ' + _fmt_datetime_packet(case_row.get('end_time')), 'Avhørsmåte: Telefon / på stedet')))
            _draw_section_caption(c, 118, top + 126, 1128, top + 154, 'Forklaring')
            _stroke_box_px(c, 118, top + 154, 1128, 1488)
            _draw_text_px(c, text, 124, top + 162, 1122, 1480, font_name='Helvetica', font_size=8.4, leading=10.0)
        else:
            _stroke_box_px(c, 118, compact_bottom + 10, 1128, 1488)
            _draw_text_px(c, text, 124, compact_bottom + 18, 1122, 1480, font_name='Helvetica', font_size=8.4, leading=10.0)
        if idx == total:
            _draw_signature_box_v94(c, 118, 1502, 623, 1604, 'Avhørtes signatur', case_row, 'suspect_signature', case_row.get('suspect_name'))
            _draw_signature_box_v94(c, 623, 1502, 1128, 1604, 'Etterforskers signatur', case_row, 'investigator_signature', case_row.get('investigator_name'))
        if idx < total:
            c.showPage()


def _draw_seizure_page(c: rl_canvas.Canvas, case_row: Dict[str, Any], packet: Dict[str, Any], doc_number: str = '05') -> None:  # type: ignore[override]
    _draw_template(c, 'page-07.png')
    _header_meta_box(c, case_row, str(doc_number or '05'), 1, 1)
    _common_body_frame(c)
    compact_bottom = _draw_sak_section_compact(c, case_row, 302)
    y = compact_bottom + 10
    _draw_section_caption(c, 118, y, 1128, y + 28, 'Mistenkt / kontrollert person')
    _draw_label_value(c, 118, y + 28, 808, y + 68, 'Navn', _fmt_value(case_row.get('suspect_name')))
    _draw_label_value(c, 808, y + 28, 1128, y + 68, 'Fødselsnr.', _fmt_value(case_row.get('suspect_birthdate')))
    y += 68
    _draw_section_caption(c, 118, y, 1128, y + 28, 'Beslag / bevis')
    _draw_label_value(c, 118, y + 28, 640, y + 96, 'Grunnlag', _offence_title(case_row, _safe_findings(case_row)))
    _draw_label_value(c, 640, y + 28, 890, y + 96, 'Fra rett/påtalemyndighet', '')
    _draw_label_value(c, 890, y + 28, 1128, y + 96, 'Samtykke gitt av', '')
    _draw_label_value(c, 118, y + 96, 440, y + 140, 'Beslag dato klokkeslett', _fmt_datetime_packet(case_row.get('end_time') or case_row.get('start_time')))
    _draw_label_value(c, 440, y + 96, 808, y + 140, 'Ledet av', _fmt_value(case_row.get('investigator_name')))
    _draw_label_value(c, 808, y + 96, 1128, y + 140, 'Tjenestested', _service_unit(case_row))
    _draw_label_value(c, 118, y + 140, 1128, y + 176, 'Observatør/vitne', _fmt_value(case_row.get('witness_name')))
    _draw_label_value(c, 118, y + 176, 1128, y + 214, 'Andre tilstedeværende', '; '.join(_persons_summary_v93(case_row))[:260])
    _draw_label_value(c, 118, y + 214, 640, y + 252, 'Sted/posisjon', _location_line(case_row))
    _draw_label_value(c, 640, y + 214, 1128, y + 252, 'Område', _fmt_value(case_row.get('area_name') or case_row.get('area_status')))
    _draw_label_value(c, 118, y + 252, 1128, y + 316, 'Merknader', _fmt_value(case_row.get('seizure_notes') or case_row.get('seizure_report_override')))
    table_top = y + 316
    _draw_section_caption(c, 118, table_top, 1128, table_top + 28, f'Beslaglagte gjenstander    Beslag journal nr.{_fmt_value(case_row.get("case_number"))}')
    rows = list(packet.get('seizure_rows') or []) or [{'seizure_ref': 'Ingen beslag registrert', 'quantity': '', 'type': '', 'description': ''}]
    row_y = table_top + 28
    cols = [118, 190, 320, 410, 560, 720, 1128]
    headers = ['Løpenr.', 'Lok.besl. nr', 'Antall', 'ID', 'Oppbevart', 'Type/beskrivelse / hvor funnet']
    for i in range(len(cols) - 1):
        _draw_label_value(c, cols[i], row_y, cols[i + 1], row_y + 34, headers[i], '')
    row_y += 34
    for idx, row in enumerate(rows[:5], start=1):
        where = str(row.get('position') or '').strip()
        if not where and case_row.get('latitude') is not None and case_row.get('longitude') is not None:
            where = _case_utm(case_row) or 'DMS ikke beregnet'
        desc = str(row.get('description') or row.get('violation_reason') or row.get('caption') or row.get('type') or '').strip()
        if row.get('law_text'):
            desc += '\n' + str(row.get('law_text')).strip()[:180]
        if where:
            desc += '\nSted: ' + where
        values = [str(idx), str(row.get('seizure_ref') or idx), str(row.get('quantity') or '1'), str(idx), 'Oppbevart', desc]
        for i in range(len(cols) - 1):
            _draw_label_value(c, cols[i], row_y, cols[i + 1], row_y + 64, '', values[i], value_size=7.7)
        row_y += 64
        if row_y > 1490:
            break
    _draw_signature_box_v94(c, 118, 1538, 623, 1604, 'Leders underskrift', case_row, 'investigator_signature', case_row.get('investigator_name'))
    _draw_signature_box_v94(c, 623, 1538, 1128, 1604, 'Observatør/vitnes underskrift', case_row, 'witness_signature', case_row.get('witness_name'))


def build_case_pdf(case_row: Dict[str, Any], evidence_rows: Iterable[Dict[str, Any]], output_dir: Path) -> Path:  # type: ignore[override]
    return _build_case_pdf_before_v93(_case_row_signature_labels_v94(case_row), evidence_rows, output_dir)


def build_interview_only_pdf(case_row: Dict[str, Any], evidence_rows: Iterable[Dict[str, Any]], output_dir: Path) -> Path:  # type: ignore[override]
    return _build_interview_only_pdf_before_v93(_case_row_signature_labels_v94(case_row), evidence_rows, output_dir)

# ---- 1.8.7: tekstmaler tilpasset straffesakshåndbok, IKV-eksempler og KREATIV avhørsstruktur ----
_build_case_packet_before_1_7 = build_case_packet
_build_text_drafts_before_1_7 = build_text_drafts
_build_interview_guidance_before_1_7 = _build_interview_guidance_v91


_LOCATION_FALLBACK_1_7 = 'kontrollstedet'


def _first_clean_1_7(*values: Any) -> str:
    for value in values:
        text = str(value or '').strip()
        if text and text != '-':
            return re.sub(r'\s+', ' ', text)
    return ''


def _nearest_place_for_text_1_7(case_row: Dict[str, Any]) -> str:
    """Returner samme stedsgrunnlag som feltet Nærmeste sted så langt data finnes."""
    place = _first_clean_1_7(case_row.get('location_name'))
    if place:
        # Eldre klienter kan ha sendt "sted - område - koordinat". Standardtekst skal bruke sted.
        place = re.split(r'\s+-\s+', place, maxsplit=1)[0].strip()
        if not re.search(r'\b(?:utm|dms|\d{1,2}\s*[°]|[NSØE]\s*\d)', place, flags=re.IGNORECASE):
            return place
    return ''


def _place_phrase_1_7(case_row: Dict[str, Any]) -> str:
    return _nearest_place_for_text_1_7(case_row) or _LOCATION_FALLBACK_1_7


def _where_line_1_7(case_row: Dict[str, Any], *, include_coordinates: bool = True) -> str:
    bits: list[str] = []
    place = _nearest_place_for_text_1_7(case_row)
    if place:
        bits.append(place)
    if include_coordinates and case_row.get('latitude') is not None and case_row.get('longitude') is not None:
        coord = _case_utm(case_row)
        if coord:
            bits.append(coord)
    return ', '.join(bits) if bits else _LOCATION_FALLBACK_1_7


def _topic_1_7(case_row: Dict[str, Any]) -> str:
    return ' / '.join(_non_empty(case_row.get('control_type'), case_row.get('species') or case_row.get('fishery_type'), case_row.get('gear_type'))) or 'fiskerikontroll'


def _clean_standard_text_1_7(text: Any, case_row: Dict[str, Any] | None = None) -> str:
    raw = str(text or '').replace('\r', '\n')
    lines = [re.sub(r'[ \t]+', ' ', line).strip() for line in raw.split('\n')]
    cleaned = '\n'.join(lines).strip()
    if not cleaned:
        return ''
    place = _place_phrase_1_7(case_row or {})
    replacements = [
        (r'\bi aktuelt kontrollområde\b', 'ved ' + place),
        (r'\bved registrert kontrollposisjon\b', 'ved ' + place),
        (r'\bved kontrollposisjonen\b', 'ved ' + place),
        (r'\bved kontrollposisjon\b', 'ved ' + place),
        (r'\bkontrollposisjonen\b', place),
        (r'\bkontrollposisjon\b', place),
    ]
    for pattern, repl in replacements:
        cleaned = re.sub(pattern, repl, cleaned, flags=re.IGNORECASE)
    cleaned = cleaned.replace('ved ved ', 'ved ')
    cleaned = cleaned.replace(' ,', ',').replace(' .', '.').replace(' :', ':')
    cleaned = '\n'.join(re.sub(r'[ \t]+', ' ', line).strip() for line in cleaned.split('\n')).strip()
    return cleaned


def _sentence_1_7(text: Any) -> str:
    cleaned = _clean_generated_phrase(text)
    cleaned = re.sub(r'\s+', ' ', cleaned).strip()
    if not cleaned:
        return ''
    if not re.search(r'[.!?]$', cleaned):
        cleaned += '.'
    return cleaned


def _avvik_1_7(findings: list[Dict[str, Any]]) -> list[Dict[str, Any]]:
    return [item for item in findings if str(item.get('status') or '').strip().lower() == 'avvik']


def _finding_note_1_7(item: Dict[str, Any]) -> str:
    return _first_clean_1_7(item.get('notes'), item.get('auto_note'), item.get('summary_text'), item.get('display_notes'))


def _finding_refs_1_7(item: Dict[str, Any]) -> str:
    parts = _non_empty(item.get('source_name'), item.get('source_ref'))
    if not parts:
        parts = _non_empty(item.get('law_name'), item.get('section'))
    return ' - '.join(parts)


def _format_findings_1_7(findings: list[Dict[str, Any]], *, prefix: str = '') -> list[str]:
    avvik = _avvik_1_7(findings)
    if not avvik:
        return [prefix + 'Det er ikke registrert avvik i kontrollpunktene på tidspunktet for tekstutkastet.']
    rows: list[str] = []
    for idx, item in enumerate(avvik, start=1):
        label = _finding_label_v91(item, idx)
        note = _finding_note_1_7(item)
        ref = _finding_refs_1_7(item)
        line = f'{idx}. {label}'
        if note:
            line += f' - {note}'
        if ref:
            line += f' ({ref})'
        rows.append(prefix + _sentence_1_7(line))
    return rows


def _seizure_rows_1_7(case_row: Dict[str, Any], findings: list[Dict[str, Any]]) -> list[Dict[str, Any]]:
    try:
        return _stored_seizure_rows_v93(case_row, findings, [])
    except Exception:
        return _parse_json_list_v93(case_row.get('seizure_reports_json'))


def _seizure_lines_1_7(case_row: Dict[str, Any], findings: list[Dict[str, Any]]) -> list[str]:
    rows = _seizure_rows_1_7(case_row, findings)
    if not rows:
        return ['Det er ikke registrert beslag i saken.']
    lines: list[str] = []
    for idx, row in enumerate(rows, start=1):
        ref = _first_clean_1_7(row.get('seizure_ref'), row.get('gear_ref'), f'Beslag {idx}')
        desc = _first_clean_1_7(row.get('description'), row.get('violation_reason'), row.get('type'), 'registrert beslag/avvik')
        qty = _first_clean_1_7(row.get('quantity'))
        pos = _first_clean_1_7(row.get('position'))
        pieces = [f'{idx}. {ref}: {desc}']
        if qty:
            pieces.append(f'antall {qty}')
        if pos:
            pieces.append(f'posisjon {pos}')
        lines.append(_sentence_1_7('; '.join(pieces)))
    return lines


def _rights_text_1_7() -> list[str]:
    return [
        'Gjør kjent hva saken gjelder og hvilket forhold personen avhøres om.',
        'Gjør kjent retten til ikke å forklare seg for Kystvakten/politiet.',
        'Gjør kjent retten til forsvarer på ethvert trinn, også under Kystvaktens avhør.',
        'Avklar behov for tolk og noter om rettighetene er forstått.',
        'Orienter om at en uforbeholden tilståelse kan få betydning ved straffeutmålingen.',
        'Orienter om at falsk anklage eller uriktig forklaring som kan medføre straffeforfølgelse av en annen person, er straffbart.',
    ]


def build_control_reason(case_row: Dict[str, Any], findings: list[Dict[str, Any]]) -> str:  # type: ignore[override]
    override = str(case_row.get('basis_details') or '').strip()
    banned = (
        'anmeldelsesegnet' + ' form',
        'tidligere registrerte ' + 'opplysninger i saken',
        'i aktuelt kontrollområde',
        'ved kontrollposisjonen',
        'ved registrert kontrollposisjon',
    )
    if override and not any(word in override.lower() for word in banned):
        return _clean_standard_text_1_7(override, case_row)
    when = _fmt_datetime(case_row.get('start_time'))
    place = _place_phrase_1_7(case_row)
    topic = _topic_1_7(case_row).lower()
    area = _first_clean_1_7(case_row.get('area_name'), case_row.get('area_status'))
    basis = str(case_row.get('case_basis') or 'patruljeobservasjon').strip().lower()
    lines = [
        f'Den {when} ble det gjennomført stedlig fiskerikontroll ved {place}.',
        f'Kontrollen gjaldt {topic}.',
        'Formålet var å kontrollere faktiske forhold på stedet, herunder redskap, merking, fangst eller oppbevaring, ansvarlig bruker/eier og øvrige kontrollpunkter som var relevante for valgt fiskeri.',
    ]
    if basis == 'tips':
        source = _first_clean_1_7(case_row.get('basis_source_name'))
        if source:
            lines.append(f'Kontrollen ble iverksatt på bakgrunn av tips eller opplysninger fra {source}.')
        else:
            lines.append('Kontrollen ble iverksatt på bakgrunn av tips eller opplysninger registrert i saken.')
    elif basis == 'anmeldelse':
        lines.append('Kontrollen ble gjennomført som oppfølging av et registrert forhold, med sikte på å klarlegge faktum og sikre notoritet rundt observasjoner og bevis.')
    elif basis == 'annen_omstendighet':
        lines.append('Kontrollen ble iverksatt på bakgrunn av øvrige opplysninger registrert i saken.')
    if area and area.lower() not in {'ingen treff', 'ikke oppgitt'}:
        lines.append(f'Kontrollstedet ble vurdert opp mot registrerte verne- eller reguleringsområder: {area}.')
    return _clean_standard_text_1_7(' '.join(lines), case_row)


def build_summary(case_row: Dict[str, Any], findings: list[Dict[str, Any]]) -> str:  # type: ignore[override]
    when = _fmt_datetime(case_row.get('start_time'))
    where = _where_line_1_7(case_row)
    topic = _topic_1_7(case_row)
    subject = _first_clean_1_7(case_row.get('suspect_name'), case_row.get('vessel_name'), 'kontrollobjektet')
    area = _first_clean_1_7(case_row.get('area_name'), case_row.get('area_status'))
    lines = [
        'Oppsummering / anmeldelsesgrunnlag',
        '',
        '1. Tid, sted og kontrolltema',
        f'Den {when} ble det gjennomført kontroll ved {where}. Kontrollen gjaldt {topic.lower()} og omfattet {subject}.',
    ]
    if area and area.lower() not in {'ingen treff', 'ikke oppgitt'}:
        lines.append(f'Kontrollstedet er vurdert mot registrert områdestatus/verneområde: {area}.')
    lines.extend([
        '',
        '2. Bakgrunn og gjennomføring',
        build_control_reason(case_row, findings),
        '',
        '3. Registrerte funn og avvik',
    ])
    lines.extend(_format_findings_1_7(findings))
    lines.extend(['', '4. Beslag, bildebevis og dokumentasjon'])
    lines.extend(_seizure_lines_1_7(case_row, findings))
    if _interview_not_conducted(case_row):
        lines.extend(['', '5. Avhør/forklaring', 'Avhør/forklaring er ikke gjennomført. Registrert årsak: ' + _interview_not_conducted_reason(case_row)])
    else:
        has_interviews = bool(_safe_list_json(case_row.get('interview_sessions_json')) or str(case_row.get('hearing_text') or '').strip())
        lines.extend(['', '5. Avhør/forklaring', 'Avhør/forklaring er registrert i saken.' if has_interviews else 'Avhør/forklaring er ikke ferdigstilt i tekstfeltet ennå.'])
    lines.extend([
        '',
        '6. Dokumentgrunnlag',
        'Utkastet beskriver faktum, kontrollobservasjoner, beslag/bildebevis og forklaringer slik de er registrert i saken. Endelig vurdering av skyld og reaksjon ligger til påtalemyndigheten.',
    ])
    return _clean_standard_text_1_7('\n'.join(lines), case_row)


def _build_short_complaint(case_row: Dict[str, Any], findings: list[Dict[str, Any]], sources: list[Dict[str, Any]]) -> str:  # type: ignore[override]
    override = str(case_row.get('complaint_override') or '').strip()
    if override:
        return _clean_standard_text_1_7(override, case_row)
    subject = _first_clean_1_7(case_row.get('suspect_name'), 'kontrollobjektet')
    when = _fmt_datetime(case_row.get('start_time'))
    where = _where_line_1_7(case_row)
    topic = _topic_1_7(case_row)
    offences = _offence_blocks(case_row, findings)
    lines: list[str] = ['Anmeldelse', '']
    if offences:
        lines.append(f'{subject} anmeldes for mulig brudd på regelverket avdekket under kontroll den {when} ved {where}. Forholdet gjelder {topic.lower()}.')
    else:
        lines.append(f'Kontroll av {subject} ble gjennomført den {when} ved {where}. Det er ikke registrert avvik som danner grunnlag for anmeldelse i kontrollpunktene på tidspunktet for utkastet.')
    lines.extend(['', 'Faktisk grunnlag:'])
    if offences:
        for idx, block in enumerate(offences, start=1):
            allegation = _sentence_1_7(block.get('allegation'))
            details = _sentence_1_7(block.get('details'))
            lines.append(f'{idx}. {allegation}' + (f' {details}' if details else ''))
    else:
        lines.append(_sentence_1_7(build_control_reason(case_row, findings)))
    refs: list[str] = []
    seen: set[str] = set()
    for block in offences:
        for ref in block.get('refs') or []:
            label = ' - '.join([part for part in [str(ref.get('name') or '').strip(), str(ref.get('ref') or '').strip()] if part])
            if label and label not in seen:
                seen.add(label)
                refs.append(label)
    for ref in _collect_legal_refs(findings, sources):
        if ref and ref not in seen:
            seen.add(ref)
            refs.append(ref)
    if refs:
        lines.extend(['', 'Aktuelt regelgrunnlag:'])
        lines.extend([f'- {ref}' for ref in refs[:8]])
    lines.extend(['', 'Bevissituasjon og dokumenter:'])
    lines.append('Anmeldelsen bygger på registrerte kontrollpunkter, egenrapport, beslagsrapport, fotomappe/illustrasjonsrapport og eventuell avhørsrapport.')
    seizure_lines = _seizure_lines_1_7(case_row, findings)
    if seizure_lines and 'ikke registrert beslag' not in seizure_lines[0].lower():
        lines.extend(seizure_lines)
    if _interview_not_conducted(case_row):
        lines.append('Avhør/forklaring er ikke gjennomført. Registrert årsak: ' + _interview_not_conducted_reason(case_row))
    else:
        lines.append('Eventuelle forklaringer er gjengitt i avhørsrapport/sammendrag og må leses sammen med øvrige bevis.')
    return _clean_standard_text_1_7('\n'.join(lines), case_row)


def _build_own_report(case_row: Dict[str, Any], findings: list[Dict[str, Any]]) -> str:  # type: ignore[override]
    override = str(case_row.get('own_report_override') or '').strip()
    if override:
        return _clean_standard_text_1_7(override, case_row)
    when = _fmt_datetime(case_row.get('start_time'))
    where = _where_line_1_7(case_row)
    investigator = _first_clean_1_7(case_row.get('investigator_name'), 'kontrollør')
    subject = _first_clean_1_7(case_row.get('suspect_name'), case_row.get('vessel_name'), 'kontrollobjektet')
    topic = _topic_1_7(case_row)
    crew = _crew_text(case_row)
    external = _external_text(case_row)
    lines = [
        'Egenrapport',
        '',
        'Kort egenrapport med faktiske observasjoner og tiltak.',
        '',
        f'Den {when} gjennomførte {investigator} kontroll ved {where}. Kontrollen gjaldt {topic.lower()}.',
    ]
    if crew and crew != '-':
        lines.append(f'Patruljeteam/medfølgende observatører: {crew}.')
    if external and external != '-':
        lines.append(f'Eksterne aktører/opplysningskilder registrert i saken: {external}.')
    lines.append(f'Under kontrollen ble {subject} kontrollert.')
    basis_text = build_control_reason(case_row, findings)
    if basis_text:
        lines.extend(['', 'Bakgrunn/formål:', basis_text])
    lines.extend(['', 'Observasjoner og funn:'])
    lines.extend(_format_findings_1_7(findings))
    lines.extend(['', 'Beslag og bevis:'])
    lines.extend(_seizure_lines_1_7(case_row, findings))
    notes = str(case_row.get('notes') or '').strip()
    if notes:
        lines.extend(['', 'Utfyllende notater fra kontrollør:', notes])
    if _interview_not_conducted(case_row):
        lines.extend(['', 'Avhør/forklaring:', 'Avhør/forklaring er ikke gjennomført. Registrert årsak: ' + _interview_not_conducted_reason(case_row)])
    return _clean_standard_text_1_7('\n'.join(lines), case_row)


def _build_interview_guidance_v91(case_row: Dict[str, Any], findings: list[Dict[str, Any]]) -> str:  # type: ignore[override]
    override = str(case_row.get('interview_guidance_text') or '').strip()
    if override:
        return _clean_standard_text_1_7(override, case_row)
    avvik = _avvik_1_7(findings)
    subject = _first_clean_1_7(case_row.get('suspect_name'), 'mistenkte/siktede')
    topic = _topic_1_7(case_row)
    where = _where_line_1_7(case_row)
    rows: list[str] = [
        'KREATIV-basert avhørsdisposisjon',
        '',
        '1. Forberedelser',
        f'- Avklar bevistema for {topic.lower()} ved {where}.',
        '- Gjør klar aktuelle bilder, kart, beslag, målinger og dokumenter som kan forevises ved behov.',
        '- Avklar hypoteser og hvilke objektive opplysninger som både taler for og mot mulig lovbrudd.',
        '',
        '2. Kontaktetablering og formalia',
        f'- Start lydopptak og noter tid, sted/metode, avhører og hvem som avhøres ({subject}).',
    ]
    rows.extend(['- ' + item for item in _rights_text_1_7()])
    rows.extend([
        '',
        '3. Fri forklaring',
        '- Be personen forklare med egne ord hva som skjedde, hvilken rolle vedkommende hadde, og hva vedkommende mener er relevant for saken.',
        '- La forklaringen komme før detaljerte kontrollspørsmål og før eventuell bevispresentasjon.',
        '',
        '4. Sondering / tema for kontrollpunkt',
    ])
    if not avvik:
        rows.append('- Ingen avvik er registrert. Vurder likevel spørsmål om identitet, eierskap, ansvar for redskap/fangst og kontrollsted dersom forklaring er nødvendig.')
    for idx, item in enumerate(avvik, start=1):
        label = _finding_label_v91(item, idx)
        note = _finding_note_1_7(item)
        ref = _finding_refs_1_7(item)
        rows.append(f'Lenke {idx}: {label}')
        if note:
            rows.append(f'- Observasjon som skal avklares: {note}')
        if ref:
            rows.append(f'- Aktuelt regelgrunnlag i saken: {ref}')
        rows.extend([
            '- Forklar tilknytning til redskap, fangst, fartøy, person eller aktivitet.',
            '- Forklar når, hvor og av hvem redskapet ble satt, brukt, røktet eller tatt opp.',
            '- Forklar hvilken kunnskap vedkommende hadde om område, fredning, redskapskrav, merkekrav, minstemål/maksimalmål eller andre relevante regler.',
            '- Avklar om det finnes kvittering, tillatelse, bilder, sporingsdata, vitner eller annen dokumentasjon som bør sikres.',
        ])
        for dev in item.get('deviation_units') or []:
            if isinstance(dev, dict):
                ref_no = _first_clean_1_7(dev.get('seizure_ref'), dev.get('gear_ref'))
                violation = _first_clean_1_7(dev.get('violation'))
                if ref_no or violation:
                    rows.append(f'- Beslag/ref {ref_no or "-"}: {violation or "avvik registrert"}. Avklar eierskap, bruk og hendelsesforløp.')
    rows.extend([
        '',
        '5. Avslutning',
        '- Spør om det er etterforskingsskritt, dokumentasjon eller personer den avhørte mener Kystvakten bør følge opp.',
        '- Gå gjennom sammendraget og noter om forklaringen godtas, korrigeres eller ikke ønskes signert.',
        '- Avklar straffeskyld bare der dette er naturlig og etter at saken/faktum er gjennomgått.',
        '- Avklar samtykke til fortsatt beslag og eventuell inndragning der dette er aktuelt.',
        '',
        '6. Evaluering',
        '- Noter kort om avhøret fulgte planen, om nye opplysninger må kontrolleres, og om det er behov for supplerende bevis eller avhør.',
    ])
    return _clean_standard_text_1_7('\n'.join(rows), case_row)


def _build_interview_report(case_row: Dict[str, Any]) -> str:  # type: ignore[override]
    if _interview_not_conducted(case_row):
        return ''
    override = str(case_row.get('interview_report_override') or '').strip()
    if override:
        return _clean_standard_text_1_7(override, case_row)
    entries = [entry for entry in _safe_list_json(case_row.get('interview_sessions_json')) if isinstance(entry, dict)]
    if not entries:
        hearing = str(case_row.get('hearing_text') or '').strip()
        subject = _first_clean_1_7(case_row.get('suspect_name'), 'avhørt person')
        entries = [{'name': subject, 'role': 'Mistenkt', 'method': 'Ikke oppgitt', 'place': _place_phrase_1_7(case_row), 'start': case_row.get('start_time'), 'end': case_row.get('end_time'), 'summary': hearing, 'transcript': ''}]
    lines: list[str] = ['Avhørsrapport', '']
    for idx, entry in enumerate(entries, start=1):
        name = _first_clean_1_7(entry.get('name'), case_row.get('suspect_name'), f'Avhørt {idx}')
        role = _first_clean_1_7(entry.get('role'), 'Mistenkt')
        method = _first_clean_1_7(entry.get('method'), 'ikke oppgitt')
        place = _first_clean_1_7(entry.get('place'), _place_phrase_1_7(case_row))
        start = _fmt_datetime(entry.get('start') or case_row.get('start_time'))
        end = _fmt_datetime(entry.get('end') or case_row.get('end_time'))
        summary = str(entry.get('summary') or '').strip()
        transcript = str(entry.get('transcript') or '').strip()
        lines.extend([
            f'Avhør {idx}',
            f'Avhørt: {name} ({role})',
            f'Sted/metode: {place} - {method}',
            f'Tid: {start} - {end}',
            'Informasjon og rettigheter: Avhørte er gjort kjent med hva saken gjelder, retten til ikke å forklare seg, retten til forsvarer, eventuell rett/bruk av tolk og ansvar for uriktig forklaring som kan ramme andre.',
            '',
            'Fri forklaring / sammendrag:',
            summary or transcript or 'Ingen registrert forklaring i saken ennå.',
            '',
        ])
        if transcript and summary and transcript != summary:
            lines.extend(['Utfyllende transkripsjon/notat:', transcript, ''])
        lines.extend([
            'Avslutning:',
            'Avhørte er gitt anledning til å komme med rettelser, tillegg og opplysninger om videre etterforskingsskritt.',
            '',
        ])
    return _clean_standard_text_1_7('\n'.join(lines), case_row)


def build_text_drafts(case_row: Dict[str, Any], findings: list[Dict[str, Any]]) -> Dict[str, str]:  # type: ignore[override]
    summary_text = build_summary(case_row, findings)
    return {
        'summary': summary_text,
        'basis_details': build_control_reason(case_row, findings),
        'notes': _build_own_report(case_row, findings),
        'complaint_preview': _build_short_complaint(case_row, findings, _safe_sources(case_row)),
        'source_label': 'straffesaksmal 1.8.7',
    }


def _ensure_evidence_preview_urls_1_8_15(case_row: Dict[str, Any], rows: Iterable[Dict[str, Any]]) -> list[Dict[str, Any]]:
    case_id = case_row.get('id')
    result: list[Dict[str, Any]] = []
    for item in rows or []:
        if not isinstance(item, dict):
            continue
        clone = dict(item)
        if not clone.get('preview_url') and case_id is not None and clone.get('id') is not None:
            clone['preview_url'] = f"/cases/{case_id}/evidence/{clone.get('id')}/file"
        result.append(clone)
    return result


def build_case_packet(case_row: Dict[str, Any], evidence_rows: Iterable[Dict[str, Any]]) -> Dict[str, Any]:  # type: ignore[override]
    evidence_rows = list(evidence_rows)
    packet = _build_case_packet_before_1_7(case_row, evidence_rows)
    packet['evidence'] = _ensure_evidence_preview_urls_1_8_15(case_row, packet.get('evidence') or [])
    packet['audio_files'] = _ensure_evidence_preview_urls_1_8_15(case_row, packet.get('audio_files') or [])
    findings = [dict(item, display_notes=_finding_display_note(item)) for item in _safe_findings(case_row)]
    sources = _safe_sources(case_row)
    packet['summary'] = build_summary(case_row, findings)
    packet['short_complaint'] = _build_short_complaint(case_row, findings, sources)
    packet['own_report'] = _build_own_report(case_row, findings)
    packet['interview_guidance'] = ''  # 1.8.23: interne forslag skal ikke inn i anmeldelse/dokumentpakke
    if _interview_not_conducted(case_row):
        packet['interview_report'] = ''
        packet['interview_not_conducted'] = True
        packet['interview_not_conducted_reason'] = _interview_not_conducted_reason(case_row)
    else:
        packet['interview_report'] = _build_interview_report(case_row)
    packet['seizure_report'] = _build_seizure_report(case_row, list(packet.get('evidence') or evidence_rows))
    return packet

# ---- 1.8.23: concise reports, empty interview when not conducted, cleaner illustrations ----
_build_case_packet_before_1_8_21 = build_case_packet
_build_case_pdf_before_1_8_21 = build_case_pdf
_build_interview_only_pdf_before_1_8_21 = build_interview_only_pdf


def _has_interview_report_content_1_8_21(case_row: Dict[str, Any]) -> bool:
    if _interview_not_conducted(case_row):
        return False
    if str(case_row.get('interview_report_override') or '').strip():
        return True
    if str(case_row.get('hearing_text') or '').strip():
        return True
    for entry in _safe_list_json(case_row.get('interview_sessions_json')):
        if not isinstance(entry, dict):
            continue
        summary = str(entry.get('summary') or entry.get('sammendrag') or '').strip()
        transcript = str(entry.get('transcript') or entry.get('text') or entry.get('tekst') or '').strip()
        notes = str(entry.get('notes') or entry.get('notater') or '').strip()
        if summary or transcript or notes:
            return True
    return False


def _registered_avvik_ref_rows_1_8_21(case_row: Dict[str, Any], findings: list[Dict[str, Any]] | None = None) -> list[Dict[str, str]]:
    rows: list[Dict[str, str]] = []
    for offence in _offence_blocks(case_row, findings if findings is not None else _safe_findings(case_row)):
        for ref in offence.get('refs') or []:
            if isinstance(ref, dict):
                rows.append({
                    'name': str(ref.get('name') or '').strip(),
                    'ref': str(ref.get('ref') or '').strip(),
                    'law_text': str(ref.get('law_text') or '').strip(),
                })
    return _merge_ref_rows(rows)


def _full_ref_rows(case_row: Dict[str, Any]) -> list[Dict[str, str]]:  # type: ignore[override]
    return _registered_avvik_ref_rows_1_8_21(case_row)


def _strip_generated_report_noise_1_8_21(value: Any) -> str:
    text = re.sub(r'\s+', ' ', str(value or '')).strip()
    if not text:
        return ''
    lowered = text.lower()
    banned = [
        'rapporten beskriver faktiske observasjoner',
        'beslag og bevis:',
        'utfyllende notater fra kontrollør: egenrapport',
        'teksten er utformet for å sikre notoritet',
    ]
    if any(part in lowered for part in banned):
        return ''
    return text


def _shorten_sentence_1_8_21(value: Any, limit: int = 180) -> str:
    text = re.sub(r'\s+', ' ', str(value or '')).strip()
    if len(text) <= limit:
        return text
    cut = text[:limit].rsplit(' ', 1)[0].rstrip(' ,.;:')
    return cut + '…'


def _build_short_complaint(case_row: Dict[str, Any], findings: list[Dict[str, Any]], sources: list[Dict[str, Any]]) -> str:  # type: ignore[override]
    override = str(case_row.get('complaint_override') or '').strip()
    if override:
        return _clean_standard_text_1_7(override, case_row)
    subject = _first_clean_1_7(case_row.get('suspect_name'), case_row.get('vessel_name'), 'kontrollobjektet')
    when = _fmt_datetime(case_row.get('start_time'))
    where = _where_line_1_7(case_row)
    topic = _topic_1_7(case_row)
    offences = _offence_blocks(case_row, findings)
    lines: list[str] = ['Anmeldelse', '']
    if offences:
        lines.append(f'{subject} anmeldes for mulige brudd på fiskeriregelverket avdekket under kontroll den {when} ved {where}. Kontrolltema var {topic.lower()}.')
    else:
        lines.append(f'Det ble gjennomført kontroll av {subject} den {when} ved {where}. Det er ikke registrert avvik som danner grunnlag for anmeldelse i kontrollpunktene på tidspunktet for utkastet.')
    lines.extend(['', 'Faktisk grunnlag:'])
    if offences:
        for idx, block in enumerate(offences, start=1):
            allegation = _sentence_1_7(block.get('allegation'))
            details = _sentence_1_7(block.get('details'))
            line = allegation
            if details and details.lower() not in allegation.lower():
                line += ' ' + details
            lines.append(f'{idx}. {_shorten_sentence_1_8_21(line, 360)}')
    else:
        lines.append(_sentence_1_7(build_control_reason(case_row, findings)))
    refs = _registered_avvik_ref_rows_1_8_21(case_row, findings)
    if refs:
        lines.extend(['', 'Aktuelle lovhjemler:'])
        for ref in refs[:10]:
            head = ' - '.join([part for part in [ref.get('name', ''), ref.get('ref', '')] if part]).strip()
            if head:
                lines.append(f'- {head}')
            if ref.get('law_text'):
                lines.append('  ' + _shorten_sentence_1_8_21(ref.get('law_text'), 260))
    lines.extend(['', 'Bevissituasjon:'])
    lines.append('Det vises til egenrapport, beslagsrapport, illustrasjonsmappe/fotomappe og øvrige dokumenter i saken. Bilder og beslag er knyttet til registrerte avvik der dette er angitt.')
    if _has_interview_report_content_1_8_21(case_row):
        lines.append('Avhør/forklaring fremgår av egen avhørsrapport.')
    return _clean_standard_text_1_7('\n'.join(lines), case_row)


def _format_avvik_lines_1_8_21(findings: list[Dict[str, Any]]) -> list[str]:
    avvik = _avvik_1_7(findings)
    if not avvik:
        return ['Det ble ikke registrert avvik i kontrollpunktene på tidspunktet rapporten ble laget.']
    rows: list[str] = []
    for idx, item in enumerate(avvik, start=1):
        label = _finding_label_v91(item, idx)
        note = _first_clean_1_7(item.get('notes'), item.get('auto_note'), item.get('display_notes'), item.get('summary_text'))
        ref = _finding_refs_1_7(item)
        line = f'{idx}. {label}'
        if note:
            line += f' - {_shorten_sentence_1_8_21(note, 220)}'
        if ref:
            line += f' ({_shorten_sentence_1_8_21(ref, 160)})'
        rows.append(_sentence_1_7(line))
    return rows


def _build_own_report(case_row: Dict[str, Any], findings: list[Dict[str, Any]]) -> str:  # type: ignore[override]
    override = str(case_row.get('own_report_override') or '').strip()
    if override:
        return _clean_standard_text_1_7(override, case_row)
    when = _fmt_datetime(case_row.get('start_time'))
    where = _where_line_1_7(case_row)
    investigator = _first_clean_1_7(case_row.get('investigator_name'), 'kontrollør')
    subject = _first_clean_1_7(case_row.get('suspect_name'), case_row.get('vessel_name'), 'kontrollobjektet')
    topic = _topic_1_7(case_row)
    crew = _crew_text(case_row)
    external = _external_text(case_row)
    lines: list[str] = [
        'Egenrapport',
        '',
        '1. Tid, sted og oppdrag',
        f'Den {when} gjennomførte {investigator} fiskerikontroll ved {where}. Kontrolltema var {topic.lower()}.',
        f'Kontrollen gjaldt {subject}.',
    ]
    if crew and crew != '-':
        lines.append(f'Patruljeteam/observatører: {crew}.')
    if external and external != '-':
        lines.append(f'Eksterne aktører/opplysningskilder: {external}.')
    basis_text = build_control_reason(case_row, findings)
    if basis_text:
        lines.extend(['', '2. Bakgrunn', _shorten_sentence_1_8_21(basis_text, 700)])
    lines.extend(['', '3. Observasjoner og funn'])
    lines.extend(_format_avvik_lines_1_8_21(findings))
    lines.extend(['', '4. Tiltak og dokumentasjon'])
    lines.append('Registrerte beslag og bildebevis er ført i beslagsrapport og illustrasjonsmappe/fotomappe. Rapporten gjengir ikke beslagslisten på nytt.')
    if _has_interview_report_content_1_8_21(case_row):
        lines.append('Avhør/forklaring er protokollert i egen avhørsrapport.')
    elif _interview_not_conducted(case_row):
        lines.append('Avhør/forklaring er ikke gjennomført. Registrert årsak: ' + _interview_not_conducted_reason(case_row))
    notes = _strip_generated_report_noise_1_8_21(case_row.get('notes'))
    if notes:
        lines.extend(['', '5. Kontrollørs merknad', _shorten_sentence_1_8_21(notes, 700)])
    return _clean_standard_text_1_7('\n'.join(lines), case_row)


def _build_interview_report(case_row: Dict[str, Any]) -> str:  # type: ignore[override]
    if not _has_interview_report_content_1_8_21(case_row):
        return ''
    override = str(case_row.get('interview_report_override') or '').strip()
    if override:
        return _clean_standard_text_1_7(override, case_row)
    entries = [entry for entry in _safe_list_json(case_row.get('interview_sessions_json')) if isinstance(entry, dict)]
    hearing = str(case_row.get('hearing_text') or '').strip()
    if not entries and hearing:
        entries = [{
            'name': _first_clean_1_7(case_row.get('suspect_name'), 'avhørt person'),
            'role': 'Mistenkt',
            'method': 'Ikke oppgitt',
            'place': _place_phrase_1_7(case_row),
            'start': case_row.get('start_time'),
            'end': case_row.get('end_time'),
            'summary': hearing,
            'transcript': '',
        }]
    lines: list[str] = ['Avhørsrapport', '']
    used = 0
    for entry in entries:
        summary = str(entry.get('summary') or entry.get('sammendrag') or '').strip()
        transcript = str(entry.get('transcript') or entry.get('text') or entry.get('tekst') or '').strip()
        notes = str(entry.get('notes') or entry.get('notater') or '').strip()
        body = summary or transcript or notes
        if not body:
            continue
        used += 1
        name = _first_clean_1_7(entry.get('name'), case_row.get('suspect_name'), f'Avhørt {used}')
        role = _first_clean_1_7(entry.get('role'), 'Mistenkt')
        method = _first_clean_1_7(entry.get('method'), 'ikke oppgitt')
        place = _first_clean_1_7(entry.get('place'), _place_phrase_1_7(case_row))
        start = _fmt_datetime(entry.get('start') or case_row.get('start_time'))
        end = _fmt_datetime(entry.get('end') or case_row.get('end_time'))
        lines.extend([
            f'Avhør {used}',
            f'Avhørt: {name} ({role})',
            f'Sted/metode: {place} - {method}',
            f'Tid: {start} - {end}',
            '',
            'Forklaring / sammendrag:',
            body,
            '',
        ])
        if transcript and summary and transcript != summary:
            lines.extend(['Utfyllende transkripsjon/notat:', transcript, ''])
    if used == 0:
        return ''
    return _clean_standard_text_1_7('\n'.join(lines), case_row)


def _extract_latlng_from_position_1_8_21(value: Any) -> tuple[float, float] | None:
    text = str(value or '').strip()
    if not text:
        return None
    dec = re.search(r'(-?\d{1,2}[\.,]\d+)\s*[,;/ ]+\s*(-?\d{1,3}[\.,]\d+)', text)
    if dec:
        try:
            lat = float(dec.group(1).replace(',', '.'))
            lng = float(dec.group(2).replace(',', '.'))
            if -90 <= lat <= 90 and -180 <= lng <= 180:
                return lat, lng
        except Exception:
            pass
    dms_re = re.compile(
        r'([NS])\s*(\d{1,2})[^0-9]+(\d{1,2})[^0-9]+(\d{1,2}(?:[\.,]\d+)?)\D+'
        r'([ØOEWV])\s*(\d{1,3})[^0-9]+(\d{1,2})[^0-9]+(\d{1,2}(?:[\.,]\d+)?)',
        re.IGNORECASE,
    )
    match = dms_re.search(text.replace('ø', 'Ø'))
    if match:
        try:
            lat = float(match.group(2)) + float(match.group(3)) / 60.0 + float(match.group(4).replace(',', '.')) / 3600.0
            lng = float(match.group(6)) + float(match.group(7)) / 60.0 + float(match.group(8).replace(',', '.')) / 3600.0
            if match.group(1).upper() == 'S':
                lat = -lat
            if match.group(5).upper() in {'W', 'V'}:
                lng = -lng
            if -90 <= lat <= 90 and -180 <= lng <= 180:
                return lat, lng
        except Exception:
            pass
    return None


def _deviation_positions_1_8_21(case_row: Dict[str, Any], findings: list[Dict[str, Any]]) -> list[tuple[float, float, str]]:
    rows: list[tuple[float, float, str]] = []
    seen: set[str] = set()
    def add_from_text(text: Any, label: str) -> None:
        parsed = _extract_latlng_from_position_1_8_21(text)
        if not parsed:
            return
        key = f'{parsed[0]:.6f},{parsed[1]:.6f}'
        if key in seen:
            return
        seen.add(key)
        rows.append((parsed[0], parsed[1], label))
    for idx, row in enumerate(_seizure_rows_1_7(case_row, findings), start=1):
        add_from_text(row.get('position'), f'Avvik {idx}')
    for item in findings:
        if str(item.get('status') or '').strip().lower() != 'avvik':
            continue
        for collection_name in ('deviation_units', 'measurements'):
            collection = item.get(collection_name) or []
            if not isinstance(collection, list):
                continue
            for row in collection:
                if isinstance(row, dict):
                    add_from_text(row.get('position') or row.get('coord_text') or row.get('coordinates'), f'Avvik {len(rows) + 1}')
    return rows[:12]


def _annotate_overview_map_1_8_21(item: Dict[str, Any], case_row: Dict[str, Any], radius_km: float, zoom: int | None = None) -> Dict[str, Any]:
    if PILImage is None or ImageDraw is None:
        return item
    path = Path(str(item.get('generated_path') or ''))
    if not path.exists():
        return item
    try:
        lat = float(case_row.get('latitude'))
        lng = float(case_row.get('longitude'))
    except Exception:
        return item
    findings = _safe_findings(case_row)
    positions = _deviation_positions_1_8_21(case_row, findings)
    if not positions or radius_km > 5.1:
        return item
    try:
        img = PILImage.open(path).convert('RGBA')
        draw = ImageDraw.Draw(img)
        width, height = img.size
        if zoom is not None:
            cx, cy = _latlng_to_world_px(lat, lng, zoom)
            min_x = cx - width / 2
            min_y = cy - height / 2
            def project(point_lat: float, point_lng: float) -> tuple[int, int]:
                wx, wy = _latlng_to_world_px(point_lat, point_lng, zoom)
                return int(wx - min_x), int(wy - min_y)
        else:
            bbox = _overview_bbox(lat, lng, radius_km=radius_km)
            def project(point_lat: float, point_lng: float) -> tuple[int, int]:
                return _project_point(point_lng, point_lat, bbox, width, height)
        for idx, (point_lat, point_lng, label) in enumerate(positions, start=1):
            x, y = project(point_lat, point_lng)
            if x < 12 or y < 92 or x > width - 12 or y > height - 12:
                continue
            draw.ellipse((x - 11, y - 11, x + 11, y + 11), fill=(255, 149, 0, 245), outline=(255, 255, 255, 255), width=3)
            draw.text((x + 14, y - 8), label or f'Avvik {idx}', fill=(16, 39, 61, 255))
        img.convert('RGB').save(path)
    except Exception:
        return item
    return item


def _map_caption_for_radius_1_8_21(radius_km: float) -> str:
    return 'Detaljert oversiktskart av kontrollposisjon' if radius_km <= 5.1 else 'Oversiktskart av kontrollposisjon'


def _generate_overview_map_image(case_row: Dict[str, Any], output_dir: Path, radius_km: float = 50.0) -> dict[str, Any] | None:  # type: ignore[override]
    use_tile_first = str(os.getenv('KV_USE_TILE_OVERVIEW_MAP', '1') or '1').strip().lower() in {'1', 'true', 'yes', 'on'}
    zoom = 14 if radius_km <= 2.5 else (13 if radius_km <= 5.1 else 9)
    result = None
    if use_tile_first:
        try:
            result = _generate_tile_overview_map_image(case_row, output_dir, radius_km=radius_km, zoom=zoom)
        except Exception:
            result = None
        if result is None:
            result = _generate_vector_overview_map_image(case_row, output_dir, radius_km=radius_km)
            zoom_for_annotation = None
        else:
            zoom_for_annotation = zoom
    else:
        result = _generate_vector_overview_map_image(case_row, output_dir, radius_km=radius_km)
        zoom_for_annotation = None
        if result is None:
            try:
                result = _generate_tile_overview_map_image(case_row, output_dir, radius_km=radius_km, zoom=zoom)
                zoom_for_annotation = zoom
            except Exception:
                result = None
    if result is None:
        return None
    result = dict(result)
    result['caption'] = _map_caption_for_radius_1_8_21(radius_km)
    result['violation_reason'] = ''
    result['law_text'] = ''
    result['finding_key'] = 'oversiktskart'
    if radius_km <= 5.1:
        result = _annotate_overview_map_1_8_21(result, case_row, radius_km, zoom=zoom_for_annotation)
    return result


def _add_v91_map_items(case_row: Dict[str, Any], evidence_rows: list[Dict[str, Any]]) -> list[Dict[str, Any]]:  # type: ignore[override]
    maps: list[Dict[str, Any]] = []
    for radius in (50.0, 2.0):
        try:
            item = _generate_overview_map_image(case_row, GENERATED_DIR, radius_km=radius)
            if item:
                item = dict(item)
                item['caption'] = _map_caption_for_radius_1_8_21(radius)
                item['violation_reason'] = ''
                item['law_text'] = ''
                maps.append(item)
        except Exception:
            continue
    non_maps = [dict(item) for item in evidence_rows if str(item.get('finding_key') or '').strip().lower() != 'oversiktskart']
    return _sort_evidence_rows_v91(maps + non_maps)


def _build_illustration_texts(evidence_rows: list[Dict[str, Any]]) -> list[str]:  # type: ignore[override]
    if not evidence_rows:
        return ['Ingen illustrasjoner registrert i saken.']
    texts: list[str] = []
    for idx, item in enumerate(evidence_rows, start=1):
        if str(item.get('finding_key') or '').strip().lower() == 'oversiktskart':
            texts.append(str(item.get('caption') or _map_caption_for_radius_1_8_21(50.0)))
            continue
        caption = _first_clean_1_7(item.get('caption'), item.get('original_filename'), f'Foto {idx}')
        seizure = _first_clean_1_7(item.get('seizure_ref'))
        reason = _shorten_sentence_1_8_21(item.get('violation_reason'), 120)
        parts = [f'Foto {idx}: {caption}']
        if seizure:
            parts.append(f'Beslag {seizure}')
        if reason:
            parts.append(reason)
        texts.append(' - '.join(parts))
    return texts


def _draw_illustration_pages(c: rl_canvas.Canvas, case_row: Dict[str, Any], packet: Dict[str, Any], doc_number: str = '06') -> None:  # type: ignore[override]
    evidence = list(packet.get('evidence') or []) or [{'caption': 'Ingen illustrasjoner registrert', 'filename': '', 'generated_path': ''}]
    text_rows = list(packet.get('illustration_texts') or _build_illustration_texts(evidence))
    chunks = [evidence[i:i + 2] for i in range(0, len(evidence), 2)]
    total = len(chunks)
    for page_idx, chunk in enumerate(chunks, start=1):
        _draw_template(c, 'page-08.png' if page_idx == 1 else 'page-09.png')
        _header_meta_box(c, case_row, str(doc_number or '06'), page_idx, total)
        _common_body_frame(c)
        compact_bottom = _draw_sak_section_compact(c, case_row, 302)
        _draw_section_caption(c, 118, compact_bottom + 10, 1128, compact_bottom + 38, 'Illustrasjoner')
        slots = [(186, compact_bottom + 54, 1060, compact_bottom + 470, compact_bottom + 480, compact_bottom + 540), (200, compact_bottom + 592, 1045, 1500, 1510, 1568)]
        for slot_idx, item in enumerate(chunk):
            absolute_idx = (page_idx - 1) * 2 + slot_idx
            l, t, r, b, ct, cb = slots[min(slot_idx, len(slots) - 1)]
            img_path = _image_path_for_evidence(item)
            if img_path and img_path.exists():
                _draw_image_fit(c, img_path, l, t, r, b)
            else:
                _stroke_box_px(c, l, t, r, b)
                _draw_text_px(c, 'Mangler bildefil', l + 4, t + 4, r - 4, b - 4, font_name='Helvetica', font_size=8.5)
            cap_text = text_rows[absolute_idx] if absolute_idx < len(text_rows) else str(item.get('caption') or f'Illustrasjon {absolute_idx + 1}')
            _draw_text_px(c, cap_text, 170, ct, 1070, cb, font_name='Helvetica', font_size=7.8, leading=9.0, align='center')
        if page_idx < total:
            c.showPage()


def _renumber_documents_1_8_21(documents: list[Dict[str, Any]]) -> list[Dict[str, Any]]:
    out: list[Dict[str, Any]] = []
    for idx, doc in enumerate(documents, start=1):
        clone = dict(doc)
        clone['number'] = f'{idx:02d}'
        out.append(clone)
    return out


def build_case_packet(case_row: Dict[str, Any], evidence_rows: Iterable[Dict[str, Any]]) -> Dict[str, Any]:  # type: ignore[override]
    evidence_rows = list(evidence_rows)
    packet = _build_case_packet_before_1_8_21(case_row, evidence_rows)
    findings = [dict(item, display_notes=_finding_display_note(item)) for item in _safe_findings(case_row)]
    sources = _safe_sources(case_row)
    audio_rows = [dict(item) for item in evidence_rows if str(item.get('mime_type') or '').startswith('audio/')]
    image_rows = [dict(item) for item in evidence_rows if not str(item.get('mime_type') or '').startswith('audio/')]
    image_rows = _add_v91_map_items(case_row, image_rows)
    image_rows = _ensure_evidence_preview_urls_1_8_15(case_row, image_rows)
    audio_rows = _ensure_evidence_preview_urls_1_8_15(case_row, audio_rows)
    has_interview = _has_interview_report_content_1_8_21(case_row)
    primary_document_title = _primary_document_title(case_row, findings)
    docs: list[Dict[str, Any]] = [
        {'number': '01', 'title': 'Dokumentliste'},
        {'number': '02', 'title': primary_document_title},
        {'number': '03', 'title': f"Egenrapport: {case_row.get('investigator_name') or 'kontrollør'}"},
    ]
    if has_interview:
        docs.append({'number': '04', 'title': f"Avhørsrapport: {case_row.get('suspect_name') or 'mistenkte'}"})
    docs.extend([
        {'number': '05', 'title': 'Beslagsrapport'},
        {'number': '06', 'title': 'Illustrasjonsmappe'},
    ])
    packet['documents'] = _renumber_documents_1_8_21(docs)
    packet['primary_document_title'] = primary_document_title
    packet['has_offences'] = bool(_offence_blocks(case_row, findings))
    packet['title'] = _offence_title(case_row, findings)
    packet['summary'] = build_summary(case_row, findings)
    packet['short_complaint'] = _build_short_complaint(case_row, findings, sources)
    packet['own_report'] = _build_own_report(case_row, findings)
    packet['interview_guidance'] = ''
    packet['interview_report'] = _build_interview_report(case_row) if has_interview else ''
    packet['interview_not_conducted'] = not has_interview
    packet['interview_not_conducted_reason'] = _interview_not_conducted_reason(case_row) if _interview_not_conducted(case_row) else ''
    packet['seizure_report'] = _build_seizure_report(case_row, image_rows)
    packet['illustration_texts'] = _build_illustration_texts(image_rows)
    packet['legal_refs'] = _registered_avvik_ref_rows_1_8_21(case_row, findings)
    packet['findings'] = findings
    packet['sources'] = sources
    packet['evidence'] = image_rows
    packet['audio_files'] = audio_rows
    return packet


def build_text_drafts(case_row: Dict[str, Any], findings: list[Dict[str, Any]]) -> Dict[str, str]:  # type: ignore[override]
    return {
        'summary': build_summary(case_row, findings),
        'basis_details': build_control_reason(case_row, findings),
        'notes': _build_own_report(case_row, findings),
        'complaint_preview': _build_short_complaint(case_row, findings, _safe_sources(case_row)),
        'source_label': 'straffesaksmal 1.8.27',
    }


def build_case_pdf(case_row: Dict[str, Any], evidence_rows: Iterable[Dict[str, Any]], output_dir: Path) -> Path:  # type: ignore[override]
    case_row = _case_row_signature_labels_v94(case_row)
    if not _template_pages_ready_v88():
        return _build_case_pdf_story_fallback_v88(case_row, evidence_rows, output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    filename = f"{str(case_row['case_number']).replace(' ', '_')}.pdf"
    outpath = output_dir / filename
    packet = build_case_packet(case_row, evidence_rows)
    has_interview = bool(packet.get('interview_report'))
    c = rl_canvas.Canvas(str(outpath), pagesize=A4)
    c.setTitle(f"Anmeldelsespakke {case_row['case_number']}")
    c.setAuthor(case_row.get('investigator_name') or 'Minfiskerikontroll')
    _draw_template(c, 'page-01.png')
    _header_meta_box(c, case_row, '01', 1, 1)
    _common_body_frame(c)
    _draw_document_list_body(c, case_row, packet)
    c.showPage()
    _draw_complaint_pages(c, case_row, packet)
    c.showPage()
    _draw_own_report_pages(c, case_row)
    c.showPage()
    if has_interview:
        _draw_interview_pages(c, case_row)
        c.showPage()
    seizure_doc_no = '05' if has_interview else '04'
    illustration_doc_no = '06' if has_interview else '05'
    _draw_seizure_page(c, case_row, packet, doc_number=seizure_doc_no)
    c.showPage()
    _draw_illustration_pages(c, case_row, packet, doc_number=illustration_doc_no)
    c.save()
    return outpath


def build_interview_only_pdf(case_row: Dict[str, Any], evidence_rows: Iterable[Dict[str, Any]], output_dir: Path) -> Path:  # type: ignore[override]
    output_dir.mkdir(parents=True, exist_ok=True)
    filename = f"{str(case_row['case_number']).replace(' ', '_')}_avhor.pdf"
    outpath = output_dir / filename
    if not _has_interview_report_content_1_8_21(case_row):
        c = rl_canvas.Canvas(str(outpath), pagesize=A4)
        c.setTitle(f"Avhørsrapport {case_row['case_number']}")
        c.setAuthor(case_row.get('investigator_name') or 'Minfiskerikontroll')
        if _template_pages_ready_v88():
            _draw_template(c, 'page-05.png')
            _header_meta_box(c, case_row, '04', 1, 1)
            _common_body_frame(c)
            _draw_section_caption(c, 118, 302, 1128, 330, 'Avhørsrapport')
        c.save()
        return outpath
    try:
        return _build_interview_only_pdf_before_1_8_21(case_row, evidence_rows, output_dir)
    except Exception:
        return _build_interview_pdf_story_fallback_v88(case_row, evidence_rows, output_dir)

# 1.8.23 hotfix: report map generation must not refresh live layer catalog while building PDFs.
def _collect_overview_shapes(case_row: Dict[str, Any], bbox: tuple[float, float, float, float]) -> list[dict[str, Any]]:  # type: ignore[override]
    shapes: list[dict[str, Any]] = []
    try:
        from . import area
        for zone in getattr(area, 'ZONES', []):
            polygon = zone.get('polygon') or []
            ring = [[float(pt[1]), float(pt[0])] for pt in polygon if len(pt) >= 2]
            if ring and _shape_intersects_bbox(ring, bbox):
                shapes.append({
                    'name': zone.get('name') or 'Regulert sone',
                    'status': zone.get('status') or 'regulert område',
                    'color': '#d97706' if 'fredning' in str(zone.get('status') or '').lower() else '#b91c1c',
                    'rings': [ring],
                })
    except Exception:
        pass
    try:
        from . import live_sources
        catalog_fn = getattr(live_sources, 'portal_layer_catalog_fast', None)
        if callable(catalog_fn):
            layers = catalog_fn(
                fishery=str(case_row.get('fishery_type') or case_row.get('species') or '').strip(),
                control_type=str(case_row.get('control_type') or '').strip(),
                gear_type=str(case_row.get('gear_type') or '').strip(),
            )
        else:
            layers = []
        for layer in layers[:20]:
            try:
                layer_id = int(layer.get('id'))
            except Exception:
                continue
            cache_path = getattr(live_sources, 'PORTAL_LAYER_CACHE_DIR', GENERATED_DIR) / f'layer_{layer_id}.geojson'
            if not cache_path.exists():
                continue
            try:
                geojson = json.loads(cache_path.read_text(encoding='utf-8'))
            except Exception:
                continue
            for feature in (geojson.get('features') or [])[:300]:
                rings = [ring for ring in _iter_polygon_rings(feature.get('geometry') or {}) if _shape_intersects_bbox(ring, bbox)]
                if rings:
                    shapes.append({
                        'name': layer.get('name') or 'Kartlag',
                        'status': layer.get('status') or 'regulert område',
                        'color': layer.get('color') or '#24527b',
                        'rings': rings[:6],
                    })
            if len(shapes) > 60:
                break
    except Exception:
        pass
    return shapes[:60]

# 1.8.23: keep overview map before detail map after caption cleanup.
def _sort_evidence_rows_v91(rows: list[Dict[str, Any]]) -> list[Dict[str, Any]]:  # type: ignore[override]
    indexed = [(idx, dict(item)) for idx, item in enumerate(rows or [])]
    def key(pair: tuple[int, Dict[str, Any]]) -> tuple[int, int, int, str, int]:
        idx, item = pair
        fk = str(item.get('finding_key') or '').strip().lower()
        caption = str(item.get('caption') or '').strip().lower()
        filename = str(item.get('filename') or item.get('generated_path') or '').strip().lower()
        if fk == 'oversiktskart':
            if '50km' in filename or caption.startswith('oversiktskart av'):
                radius_rank = 0
            elif '2km' in filename or '5km' in filename or caption.startswith('detaljert'):
                radius_rank = 1
            else:
                radius_rank = 2
            return (0, radius_rank, 0, caption, idx)
        return (1, 0, _evidence_manual_order_value(item, idx), caption, idx)
    return [item for _, item in sorted(indexed, key=key)]

# 1.8.23 final packet builder: avoid earlier nested packet builders and repeated map export.
def build_case_packet(case_row: Dict[str, Any], evidence_rows: Iterable[Dict[str, Any]]) -> Dict[str, Any]:  # type: ignore[override]
    findings = [dict(item, display_notes=_finding_display_note(item)) for item in _safe_findings(case_row)]
    sources = _safe_sources(case_row)
    all_evidence_rows = list(evidence_rows)
    audio_rows = [dict(item) for item in all_evidence_rows if str(item.get('mime_type') or '').startswith('audio/')]
    image_rows = [dict(item) for item in all_evidence_rows if not str(item.get('mime_type') or '').startswith('audio/')]
    image_rows = _add_v91_map_items(case_row, image_rows)
    image_rows = _ensure_evidence_preview_urls_1_8_15(case_row, image_rows)
    audio_rows = _ensure_evidence_preview_urls_1_8_15(case_row, audio_rows)
    has_interview = _has_interview_report_content_1_8_21(case_row)
    primary_document_title = _primary_document_title(case_row, findings)
    docs: list[Dict[str, Any]] = [
        {'number': '01', 'title': 'Dokumentliste'},
        {'number': '02', 'title': primary_document_title},
        {'number': '03', 'title': f"Egenrapport: {case_row.get('investigator_name') or 'kontrollør'}"},
    ]
    if has_interview:
        docs.append({'number': '04', 'title': f"Avhørsrapport: {case_row.get('suspect_name') or 'mistenkte'}"})
    docs.extend([
        {'number': '05', 'title': 'Beslagsrapport'},
        {'number': '06', 'title': 'Illustrasjonsmappe'},
    ])
    documents = _renumber_documents_1_8_21(docs)
    return {
        'documents': documents,
        'primary_document_title': primary_document_title,
        'has_offences': bool(_offence_blocks(case_row, findings)),
        'title': _offence_title(case_row, findings),
        'summary': build_summary(case_row, findings),
        'short_complaint': _build_short_complaint(case_row, findings, sources),
        'own_report': _build_own_report(case_row, findings),
        'interview_report': _build_interview_report(case_row) if has_interview else '',
        'interview_guidance': '',
        'interview_not_conducted': not has_interview,
        'interview_not_conducted_reason': _interview_not_conducted_reason(case_row) if _interview_not_conducted(case_row) else '',
        'seizure_report': _build_seizure_report(case_row, image_rows),
        'illustration_texts': _build_illustration_texts(image_rows),
        'legal_refs': _registered_avvik_ref_rows_1_8_21(case_row, findings),
        'findings': findings,
        'sources': sources,
        'evidence': image_rows,
        'audio_files': audio_rows,
        'interview_entries': [entry for entry in _safe_list_json(case_row.get('interview_sessions_json')) if isinstance(entry, dict)],
        'notes': _build_own_report(case_row, findings),
        'hearing_text': case_row.get('hearing_text') or '',
        'seizure_text': case_row.get('seizure_notes') or '',
        'meta_rows': [row for row in [
            ('Saksnummer', _fmt_value(case_row.get('case_number'))),
            ('Registrert', _fmt_datetime(case_row.get('created_at'))),
            ('Oppdatert', _fmt_datetime(case_row.get('updated_at'))),
            ('Grunnlag for iverksetting', _case_basis_label(case_row)),
            ('Etterforsker', _fmt_value(case_row.get('investigator_name'))),
            ('Anmelder', _fmt_value(case_row.get('complainant_name'))),
            ('Observatør/vitne', _fmt_value(case_row.get('witness_name'))),
            ('Patruljeteam / roller', _crew_text(case_row)),
            ('Eksterne aktører', _external_text(case_row)),
            ('Kontrolltype', _fmt_value(case_row.get('control_type'))),
            ('Art / fiskeri', f"{_fmt_value(case_row.get('species'))} / {_fmt_value(case_row.get('fishery_type'))}"),
            ('Redskap', _fmt_value(case_row.get('gear_type'))),
            ('Lokasjon', _fmt_value(case_row.get('location_name'))),
            ('Område', ' - '.join([part for part in [_area_status_value(case_row), _area_name_value(case_row)] if part])),
            ('Posisjon', f"{_fmt_value(case_row.get('latitude'))}, {_fmt_value(case_row.get('longitude'))}"),
            ('Mistenkt / ansvarlig', _fmt_value(case_row.get('suspect_name'))),
            ('Mobil', _fmt_value(case_row.get('suspect_phone'))),
            ('Adresse', _fmt_value(case_row.get('suspect_address'))),
            ('Fødselsdato', _fmt_value(case_row.get('suspect_birthdate'))),
            ('Hummerdeltakernr', _fmt_value(case_row.get('hummer_participant_no'))),
            ('Fartøysnavn', _fmt_value(case_row.get('vessel_name'))),
            ('Fiskerimerke', _fmt_value(case_row.get('vessel_reg'))),
            ('Radiokallesignal', _fmt_value(case_row.get('radio_call_sign'))),
            ('Tidsrom', f"{_fmt_datetime(case_row.get('start_time'))} - {_fmt_datetime(case_row.get('end_time'))}"),
        ] if str(row[1]).strip() not in {'', '-'}],
    }

# ---- 1.8.23: conducted-interview gate and concise police-style report polish ----
def _truthy_report_flag_1_8_21(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return int(value) == 1
    text = str(value or '').strip().lower()
    return text in {'1', 'true', 'yes', 'ja', 'on', 'gjennomført', 'gjennomfort', 'completed', 'conducted'}


def _interview_entry_body_1_8_21(entry: Dict[str, Any]) -> str:
    return str(
        entry.get('summary')
        or entry.get('sammendrag')
        or entry.get('transcript')
        or entry.get('text')
        or entry.get('tekst')
        or entry.get('notes')
        or entry.get('notater')
        or ''
    ).strip()


def _interview_entry_conducted_1_8_21(entry: Dict[str, Any]) -> bool:
    for key in ('conducted', 'completed', 'is_conducted', 'report_included', 'include_in_report', 'gjennomfort', 'gjennomført'):
        if key in entry:
            return _truthy_report_flag_1_8_21(entry.get(key))
    return False


def _conducted_interview_entries_1_8_21(case_row: Dict[str, Any]) -> list[Dict[str, Any]]:
    if _interview_not_conducted(case_row):
        return []
    entries: list[Dict[str, Any]] = []
    for entry in _safe_list_json(case_row.get('interview_sessions_json')):
        if not isinstance(entry, dict):
            continue
        if not _interview_entry_conducted_1_8_21(entry):
            continue
        if not _interview_entry_body_1_8_21(entry):
            continue
        entries.append(entry)
    return entries


def _has_interview_report_content_1_8_21(case_row: Dict[str, Any]) -> bool:  # type: ignore[override]
    if _interview_not_conducted(case_row):
        return False
    # A manually written override is treated as an explicit report decision.
    if str(case_row.get('interview_report_override') or '').strip():
        return True
    return bool(_conducted_interview_entries_1_8_21(case_row))


def _build_interview_report(case_row: Dict[str, Any]) -> str:  # type: ignore[override]
    if not _has_interview_report_content_1_8_21(case_row):
        return ''
    override = str(case_row.get('interview_report_override') or '').strip()
    if override:
        return _clean_standard_text_1_7(override, case_row)
    entries = _conducted_interview_entries_1_8_21(case_row)
    lines: list[str] = ['Avhørsrapport', '']
    used = 0
    for entry in entries:
        summary = str(entry.get('summary') or entry.get('sammendrag') or '').strip()
        transcript = str(entry.get('transcript') or entry.get('text') or entry.get('tekst') or '').strip()
        notes = str(entry.get('notes') or entry.get('notater') or '').strip()
        body = summary or transcript or notes
        if not body:
            continue
        used += 1
        name = _first_clean_1_7(entry.get('name'), case_row.get('suspect_name'), f'Avhørt {used}')
        role = _first_clean_1_7(entry.get('role'), 'Mistenkt')
        method = _first_clean_1_7(entry.get('method'), 'ikke oppgitt')
        place = _first_clean_1_7(entry.get('place'), _place_phrase_1_7(case_row))
        start = _fmt_datetime(entry.get('start') or case_row.get('start_time'))
        end = _fmt_datetime(entry.get('end') or case_row.get('end_time'))
        lines.extend([
            f'Avhør {used}',
            f'Avhørt: {name} ({role})',
            f'Sted/metode: {place} - {method}',
            f'Tid: {start} - {end}',
            '',
            'Forklaring / sammendrag:',
            body,
            '',
        ])
        if transcript and summary and transcript != summary:
            lines.extend(['Utfyllende transkripsjon/notat:', transcript, ''])
    if used == 0:
        return ''
    return _clean_standard_text_1_7('\n'.join(lines), case_row)


def _strip_generated_report_noise_1_8_21(value: Any) -> str:  # type: ignore[override]
    text = re.sub(r'\s+', ' ', str(value or '')).strip()
    if not text:
        return ''
    lowered = text.lower()
    banned = [
        'rapporten beskriver faktiske observasjoner',
        'beslag og bevis:',
        'utfyllende notater fra kontrollør: egenrapport',
        'teksten er utformet for å sikre notoritet',
        'egenrapport rapporten beskriver',
        'egenrapport 1. tid, sted og oppdrag',
        '1. tid, sted og oppdrag',
        'rapporten gjengir ikke beslagslisten',
        'registrerte beslag og bildebevis er ført i beslagsrapport',
    ]
    if any(part in lowered for part in banned):
        return ''
    # If the entire notes field is a generated report, do not repeat it as a control note.
    if lowered.startswith('egenrapport') and ('observasjoner og funn' in lowered or 'tiltak og dokumentasjon' in lowered):
        return ''
    return text


def _build_short_complaint(case_row: Dict[str, Any], findings: list[Dict[str, Any]], sources: list[Dict[str, Any]]) -> str:  # type: ignore[override]
    override = str(case_row.get('complaint_override') or '').strip()
    if override:
        return _clean_standard_text_1_7(override, case_row)
    subject = _first_clean_1_7(case_row.get('suspect_name'), case_row.get('vessel_name'), 'kontrollobjektet')
    when = _fmt_datetime(case_row.get('start_time'))
    where = _where_line_1_7(case_row)
    topic = _topic_1_7(case_row)
    offences = _offence_blocks(case_row, findings)
    lines: list[str] = ['Anmeldelse', '']
    if offences:
        lines.append(f'{subject} anmeldes for mulige brudd på fiskeriregelverket avdekket under kontroll den {when} ved {where}. Kontrolltema var {topic.lower()}.')
    else:
        lines.append(f'Det ble gjennomført kontroll av {subject} den {when} ved {where}. Det er ikke registrert avvik som danner grunnlag for anmeldelse i kontrollpunktene på tidspunktet for utkastet.')
    lines.extend(['', 'Faktisk grunnlag:'])
    if offences:
        for idx, block in enumerate(offences, start=1):
            allegation = _sentence_1_7(block.get('allegation'))
            details = _sentence_1_7(block.get('details'))
            line = allegation
            if details and details.lower() not in allegation.lower():
                line += ' ' + details
            lines.append(f'{idx}. {_shorten_sentence_1_8_21(line, 360)}')
    else:
        lines.append(_sentence_1_7(build_control_reason(case_row, findings)))
    refs = _registered_avvik_ref_rows_1_8_21(case_row, findings)
    if refs:
        lines.extend(['', 'Aktuelle lovhjemler:'])
        for ref in refs[:10]:
            head = ' - '.join([part for part in [ref.get('name', ''), ref.get('ref', '')] if part]).strip()
            if head:
                lines.append(f'- {head}')
    lines.extend(['', 'Bevis:'])
    lines.append('Egenrapport, beslagsrapport og illustrasjonsmappe/fotomappe beskriver observasjoner, beslag og bildebevis. Det vises til dokumentlisten for detaljer.')
    if _has_interview_report_content_1_8_21(case_row):
        lines.append('Avhør/forklaring fremgår av egen avhørsrapport.')
    return _clean_standard_text_1_7('\n'.join(lines), case_row)


def _build_own_report(case_row: Dict[str, Any], findings: list[Dict[str, Any]]) -> str:  # type: ignore[override]
    override = str(case_row.get('own_report_override') or '').strip()
    if override:
        return _clean_standard_text_1_7(override, case_row)
    when = _fmt_datetime(case_row.get('start_time'))
    where = _where_line_1_7(case_row)
    investigator = _first_clean_1_7(case_row.get('investigator_name'), 'kontrollør')
    subject = _first_clean_1_7(case_row.get('suspect_name'), case_row.get('vessel_name'), 'kontrollobjektet')
    topic = _topic_1_7(case_row)
    crew = _crew_text(case_row)
    external = _external_text(case_row)
    lines: list[str] = [
        'Egenrapport',
        '',
        '1. Tid og sted',
        f'Den {when} gjennomførte {investigator} fiskerikontroll ved {where}.',
        '',
        '2. Kontrolltema',
        f'Kontrollen gjaldt {topic.lower()} og omfattet {subject}.',
    ]
    if crew and crew != '-':
        lines.append(f'Patruljeteam/observatører: {crew}.')
    if external and external != '-':
        lines.append(f'Eksterne aktører/opplysningskilder: {external}.')
    basis_text = _shorten_sentence_1_8_21(build_control_reason(case_row, findings), 520)
    if basis_text:
        lines.extend(['', '3. Bakgrunn', basis_text])
    lines.extend(['', '4. Faktiske observasjoner'])
    lines.extend(_format_avvik_lines_1_8_21(findings))
    lines.extend(['', '5. Tiltak og dokumentasjon'])
    lines.append('Beslag er dokumentert i beslagsrapport. Fotografier og kart er dokumentert i illustrasjonsmappe/fotomappe.')
    if _has_interview_report_content_1_8_21(case_row):
        lines.append('Gjennomført avhør/forklaring er protokollert i egen avhørsrapport.')
    notes = _strip_generated_report_noise_1_8_21(case_row.get('notes'))
    if notes:
        lines.extend(['', '6. Kontrollørs merknad', _shorten_sentence_1_8_21(notes, 520)])
    return _clean_standard_text_1_7('\n'.join(lines), case_row)


def build_text_drafts(case_row: Dict[str, Any], findings: list[Dict[str, Any]]) -> Dict[str, str]:  # type: ignore[override]
    # Do not write generated egenrapport text into case.notes. That field is for
    # the controller's own free-text note; repeating the whole report there caused
    # duplicate text in later PDFs.
    return {
        'summary': build_summary(case_row, findings),
        'basis_details': build_control_reason(case_row, findings),
        'notes': '',
        'complaint_preview': _build_short_complaint(case_row, findings, _safe_sources(case_row)),
        'source_label': 'straffesaksmal 1.8.27',
    }

# ---- 1.8.23: standardtekster etter Kystvaktens straffesaksføringer ----
# Synlig grunnlag for kontroll skal være Patrulje eller Tips. Legacyverdier
# beholdes ikke som valg, men håndteres trygt som patrulje i rapporttekstene.
CASE_BASIS_LABELS.clear()
CASE_BASIS_LABELS.update({
    'patruljeobservasjon': 'Patrulje',
    'tips': 'Tips',
})

_clean_standard_text_before_1_8_22 = _clean_standard_text_1_7


def _normal_case_basis_1_8_22(value: Any) -> str:
    return 'tips' if str(value or '').strip().lower() == 'tips' else 'patruljeobservasjon'


def _case_basis_label(case_row: Dict[str, Any]) -> str:  # type: ignore[override]
    return 'Tips' if _normal_case_basis_1_8_22(case_row.get('case_basis')) == 'tips' else 'Patrulje'


def _clean_standard_text_1_7(text: Any, case_row: Dict[str, Any] | None = None) -> str:  # type: ignore[override]
    cleaned = _clean_standard_text_before_1_8_22(text, case_row)
    if not cleaned:
        return ''
    replacements = [
        (r'\binvolverte\s+personer\s*/\s*fartøy\b', 'relevante personer og kontrollobjekt'),
        (r'\binvolverte\s+personer\s+eller\s+fartøy\b', 'relevante personer og kontrollobjekt'),
        (r'\bInvolverte\b', 'Personer i saken'),
        (r'\binvolverte\b', 'relevante personer'),
        (r'\bkontrollert\s+person\s*/\s*fartøy\b', 'kontrollobjektet'),
        (r'\bregistrert anmeldelse\b', 'registrerte opplysninger'),
        (r'\bgrunnlag for anmeldelse\b', 'rapportgrunnlag'),
        (r'\banmeldelsesgrunnlag\b', 'rapportgrunnlag'),
    ]
    for pattern, repl in replacements:
        cleaned = re.sub(pattern, repl, cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r'\s+,', ',', cleaned)
    cleaned = re.sub(r'\s+\.', '.', cleaned)
    cleaned = re.sub(r'[ \t]{2,}', ' ', cleaned)
    cleaned = '\n'.join(re.sub(r'[ \t]+', ' ', line).strip() for line in cleaned.split('\n')).strip()
    return cleaned


def _report_subject_1_8_22(case_row: Dict[str, Any], *, for_complaint: bool = False) -> str:
    name = _first_clean_1_7(case_row.get('suspect_name'))
    vessel = _first_clean_1_7(case_row.get('vessel_name'), case_row.get('vessel_reg'))
    if name and vessel and vessel.lower() not in name.lower():
        return f'{name} / {vessel}'
    if name:
        return name
    if vessel:
        return vessel
    return 'ukjent gjerningsperson' if for_complaint else 'kontrollobjektet'




def _subject_line_1_8_22(subject: str) -> str:
    if str(subject or '').strip().lower() == 'kontrollobjektet':
        return 'Kontrollobjekt er ikke særskilt identifisert i person-/fartøyfeltene.'
    return f'Kontrollobjekt: {subject}.'

def _basis_background_sentence_1_8_22(case_row: Dict[str, Any]) -> str:
    basis = _normal_case_basis_1_8_22(case_row.get('case_basis'))
    source = _first_clean_1_7(case_row.get('basis_source_name'))
    if basis == 'tips':
        if source:
            return f'Kontrollen ble iverksatt etter tips eller opplysninger fra {source}. Tipsopplysningene er bakgrunn for kontrollen og holdes adskilt fra patruljens egne observasjoner.'
        return 'Kontrollen ble iverksatt etter tips eller opplysninger. Tipsopplysningene er bakgrunn for kontrollen og holdes adskilt fra patruljens egne observasjoner.'
    return 'Kontrollen ble gjennomført som del av patrulje- og kontrollvirksomhet. Rapportteksten bygger på patruljens egne observasjoner, gjennomførte tiltak og sikret dokumentasjon.'


def _standard_basis_text_1_8_22(case_row: Dict[str, Any]) -> str:
    when = _fmt_datetime(case_row.get('start_time'))
    place = _place_phrase_1_7(case_row)
    topic = _topic_1_7(case_row).lower()
    area = _first_clean_1_7(case_row.get('area_name'), case_row.get('area_status'))
    lines = [
        f'Den {when} gjennomførte patruljen stedlig fiskerikontroll ved {place}.',
        f'Kontrollen gjaldt {topic}.',
        'Formålet var å kontrollere observerbare forhold på stedet og etterlevelse av gjeldende regelverk, med vekt på redskap, merking, fangst/oppbevaring, posisjon og relevante område- eller redskapsbestemmelser.',
        _basis_background_sentence_1_8_22(case_row),
    ]
    if area and area.lower() not in {'ingen treff', 'ikke oppgitt'}:
        lines.append(f'Kontrollstedet ble vurdert opp mot registrerte verne- eller reguleringsområder: {area}.')
    return ' '.join(line for line in lines if line)


def _looks_like_old_generated_basis_1_8_22(value: str) -> bool:
    lowered = str(value or '').strip().lower()
    if not lowered:
        return True
    markers = (
        'anmeldelsesegnet form',
        'registrert anmeldelse',
        'involverte personer',
        'kontrollert person/fartøy',
        'formålet var å kontrollere faktiske forhold',
        'tekstutkastet er skrevet kortfattet',
        'identifisere relevante personer og kontrollobjekt',
        'identifisere involverte',
    )
    return any(marker in lowered for marker in markers)


def build_control_reason(case_row: Dict[str, Any], findings: list[Dict[str, Any]]) -> str:  # type: ignore[override]
    override = str(case_row.get('basis_details') or '').strip()
    if override and not _looks_like_old_generated_basis_1_8_22(override):
        return _clean_standard_text_1_7(override, case_row)
    return _clean_standard_text_1_7(_standard_basis_text_1_8_22(case_row), case_row)


def build_summary(case_row: Dict[str, Any], findings: list[Dict[str, Any]]) -> str:  # type: ignore[override]
    if (case_row.get('summary') or '').strip():
        return _clean_standard_text_1_7(case_row.get('summary'), case_row)
    when = _fmt_datetime(case_row.get('start_time'))
    where = _where_line_1_7(case_row)
    topic = _topic_1_7(case_row)
    subject = _report_subject_1_8_22(case_row)
    area = _first_clean_1_7(case_row.get('area_name'), case_row.get('area_status'))
    lines: list[str] = [
        'Oppsummering / rapportgrunnlag',
        '',
        '1. Tid, sted og kontrolltema',
        f'Den {when} ble det gjennomført kontroll ved {where}. Kontrolltema var {topic.lower()}.',
        _subject_line_1_8_22(subject),
    ]
    if area and area.lower() not in {'ingen treff', 'ikke oppgitt'}:
        lines.append(f'Kontrollstedet er vurdert mot registrert områdestatus/verneområde: {area}.')
    lines.extend(['', '2. Bakgrunn og gjennomføring', build_control_reason(case_row, findings), '', '3. Registrerte avvik'])
    lines.extend(_format_avvik_lines_1_8_21(findings))
    lines.extend(['', '4. Dokumentasjon og tiltak'])
    seizure_rows = _seizure_rows_1_7(case_row, findings)
    if seizure_rows:
        lines.append('Beslag er ført i egen beslagsrapport. Foto og kart fremgår av illustrasjonsmappe/fotomappe.')
    else:
        lines.append('Foto, kart og øvrig dokumentasjon fremgår av illustrasjonsmappe/fotomappe der dette er registrert.')
    if _has_interview_report_content_1_8_21(case_row):
        lines.append('Gjennomført avhør/forklaring fremgår av egen avhørsrapport.')
    return _clean_standard_text_1_7('\n'.join(lines), case_row)


def _build_short_complaint(case_row: Dict[str, Any], findings: list[Dict[str, Any]], sources: list[Dict[str, Any]]) -> str:  # type: ignore[override]
    override = str(case_row.get('complaint_override') or '').strip()
    if override:
        return _clean_standard_text_1_7(override, case_row)
    subject = _report_subject_1_8_22(case_row, for_complaint=True)
    when = _fmt_datetime(case_row.get('start_time'))
    where = _where_line_1_7(case_row)
    topic = _topic_1_7(case_row)
    offences = _offence_blocks(case_row, findings)
    lines: list[str] = ['Anmeldelse', '']
    if offences:
        lines.append(f'Det inngis anmeldelse mot {subject} for mulige brudd på fiskeriregelverket avdekket under kontroll den {when} ved {where}. Kontrolltema var {topic.lower()}.')
    else:
        lines.append(f'Det ble gjennomført kontroll den {when} ved {where}. Kontrolltema var {topic.lower()}. Det er ikke registrert avvik som danner rapportgrunnlag i kontrollpunktene på tidspunktet for utkastet.')
    lines.extend(['', 'Faktisk grunnlag:'])
    if offences:
        for idx, block in enumerate(offences, start=1):
            allegation = _sentence_1_7(block.get('allegation'))
            details = _sentence_1_7(block.get('details'))
            line = allegation
            if details and details.lower() not in allegation.lower():
                line += ' ' + details
            lines.append(f'{idx}. {_shorten_sentence_1_8_21(line, 360)}')
    else:
        lines.append(_sentence_1_7(build_control_reason(case_row, findings)))
    refs = _registered_avvik_ref_rows_1_8_21(case_row, findings)
    if refs:
        lines.extend(['', 'Aktuelle lovhjemler:'])
        for ref in refs[:10]:
            head = ' - '.join([part for part in [ref.get('name', ''), ref.get('ref', '')] if part]).strip()
            if head:
                lines.append(f'- {head}')
    lines.extend(['', 'Bevis:'])
    evidence_docs = ['egenrapport', 'beslagsrapport', 'illustrasjonsmappe/fotomappe']
    if _has_interview_report_content_1_8_21(case_row):
        evidence_docs.append('avhørsrapport')
    lines.append('Det vises til dokumentlisten og sakens ' + ', '.join(evidence_docs) + '.')
    return _clean_standard_text_1_7('\n'.join(lines), case_row)


def _build_own_report(case_row: Dict[str, Any], findings: list[Dict[str, Any]]) -> str:  # type: ignore[override]
    override = str(case_row.get('own_report_override') or '').strip()
    if override:
        return _clean_standard_text_1_7(override, case_row)
    when = _fmt_datetime(case_row.get('start_time'))
    where = _where_line_1_7(case_row)
    investigator = _first_clean_1_7(case_row.get('investigator_name'), 'kontrollør')
    subject = _report_subject_1_8_22(case_row)
    topic = _topic_1_7(case_row)
    crew = _crew_text(case_row)
    external = _external_text(case_row)
    lines: list[str] = [
        'Egenrapport',
        '',
        '1. Tid og sted',
        f'Den {when} gjennomførte {investigator} fiskerikontroll ved {where}.',
        '',
        '2. Kontrolltema og objekt',
        f'Kontrolltema var {topic.lower()}.',
        _subject_line_1_8_22(subject),
    ]
    if crew and crew != '-':
        lines.append(f'Patruljeteam/observatører: {crew}.')
    if external and external != '-':
        lines.append(f'Eksterne aktører/opplysningskilder: {external}.')
    basis_text = _shorten_sentence_1_8_21(build_control_reason(case_row, findings), 560)
    if basis_text:
        lines.extend(['', '3. Bakgrunn', basis_text])
    lines.extend(['', '4. Faktiske observasjoner'])
    lines.extend(_format_avvik_lines_1_8_21(findings))
    lines.extend(['', '5. Tiltak og dokumentasjon'])
    if _seizure_rows_1_7(case_row, findings):
        lines.append('Beslag er dokumentert i beslagsrapport. Fotografier, kart og øvrige bildebevis er dokumentert i illustrasjonsmappe/fotomappe.')
    else:
        lines.append('Fotografier, kart og øvrig dokumentasjon fremgår av illustrasjonsmappe/fotomappe der dette er registrert.')
    if _has_interview_report_content_1_8_21(case_row):
        lines.append('Gjennomført avhør/forklaring er protokollert i egen avhørsrapport.')
    notes = _strip_generated_report_noise_1_8_21(case_row.get('notes'))
    if notes:
        lines.extend(['', '6. Kontrollørs merknad', _shorten_sentence_1_8_21(notes, 560)])
    return _clean_standard_text_1_7('\n'.join(lines), case_row)


def build_text_drafts(case_row: Dict[str, Any], findings: list[Dict[str, Any]]) -> Dict[str, str]:  # type: ignore[override]
    return {
        'summary': build_summary(case_row, findings),
        'basis_details': build_control_reason(case_row, findings),
        'notes': '',
        'complaint_preview': _build_short_complaint(case_row, findings, _safe_sources(case_row)),
        'source_label': 'straffesaksmal 1.8.27',
    }

# ---- 1.8.23: anmeldelse/egenrapport/fotomappe tekstmaler tilpasset Kystvaktens IKV-stil ----
_registered_avvik_ref_rows_before_1_8_23 = _registered_avvik_ref_rows_1_8_21
_full_ref_rows_before_1_8_23 = _full_ref_rows
_refs_to_text_before_1_8_23 = _refs_to_text
_build_short_complaint_before_1_8_23 = _build_short_complaint
_build_own_report_before_1_8_23 = _build_own_report
_build_illustration_texts_before_1_8_23 = _build_illustration_texts
_build_control_reason_before_1_8_23 = build_control_reason
_build_summary_before_1_8_23 = build_summary
_offence_title_before_1_8_23 = _offence_title


def _strip_doc_heading_1_8_23(value: Any) -> str:
    text = str(value or '').strip()
    text = re.sub(r'^\s*(Anmeldelse|Egenrapport|Oppsummering\s*/\s*rapportgrunnlag)\s*\n+', '', text, flags=re.IGNORECASE)
    return text.strip()


def _clean_law_text_1_8_23(value: Any) -> str:
    text = re.sub(r'\s+', ' ', str(value or '')).strip()
    if not text or text == '-':
        return ''
    text = re.sub(r'([a-zæøå])([A-ZÆØÅ])', r'\1 \2', text)
    text = re.sub(r'\bNavn på gytefeltBeskrivelsePunktPosisjon\b', '', text, flags=re.IGNORECASE).strip()
    return text


def _legal_ref_head_1_8_23(ref: Dict[str, Any]) -> str:
    return ' - '.join([part for part in [str(ref.get('name') or '').strip(), str(ref.get('ref') or '').strip()] if part]).strip()


def _law_excerpt_1_8_23(ref: Dict[str, Any], limit: int = 360) -> str:
    text = _clean_law_text_1_8_23(ref.get('law_text'))
    if not text:
        return ''
    # Store forskriftstekster kan inneholde hele kart-/områdebeskrivelser. I anmeldelsen skal
    # leseren få utdraget som forklarer regelen, ikke hele Lovdata-teksten.
    stop_patterns = [
        r'\bNavn på gytefelt\b',
        r'\bIndre Oslofjord\b',
        r'\bMossesundet\b',
        r'\bSletterhausen\b',
        r'\bHvaler\b',
        r'\bPunktPosisjon\b',
    ]
    for pattern in stop_patterns:
        m = re.search(pattern, text, flags=re.IGNORECASE)
        if m and m.start() > 60:
            text = text[:m.start()].strip(' ,.;:')
            break
    # Prioriter først den normative setningen. Deretter tas eventuell strafferegel kort med.
    sentences = re.split(r'(?<=[.!?])\s+', text)
    chosen: list[str] = []
    for sentence in sentences:
        s = sentence.strip()
        if not s:
            continue
        chosen.append(s)
        if len(' '.join(chosen)) >= limit or len(chosen) >= 2:
            break
    excerpt = ' '.join(chosen).strip() or text
    if len(excerpt) > limit:
        excerpt = excerpt[:limit].rsplit(' ', 1)[0].rstrip(' ,.;:') + '...'
    return excerpt


def _display_ref_row_1_8_23(ref: Dict[str, Any]) -> Dict[str, str]:
    excerpt = _law_excerpt_1_8_23(ref, 360)
    return {
        'name': str(ref.get('name') or '').strip(),
        'ref': str(ref.get('ref') or '').strip(),
        'law_text': excerpt,
        'excerpt': excerpt,
    }


def _registered_avvik_ref_rows_1_8_21(case_row: Dict[str, Any], findings: list[Dict[str, Any]] | None = None) -> list[Dict[str, str]]:  # type: ignore[override]
    raw_rows = _registered_avvik_ref_rows_before_1_8_23(case_row, findings)
    display_rows = [_display_ref_row_1_8_23(row) for row in raw_rows]
    return _merge_ref_rows(display_rows)


def _full_ref_rows(case_row: Dict[str, Any]) -> list[Dict[str, str]]:  # type: ignore[override]
    return _registered_avvik_ref_rows_1_8_21(case_row)


def _refs_to_text(refs: list[Dict[str, str]]) -> str:  # type: ignore[override]
    chunks: list[str] = []
    for ref in refs:
        head = _legal_ref_head_1_8_23(ref)
        excerpt = str(ref.get('excerpt') or ref.get('law_text') or '').strip()
        if not head and not excerpt:
            continue
        if head:
            chunks.append(head)
        if excerpt:
            chunks.append('Utdrag: ' + excerpt)
        chunks.append('')
    return '\n'.join(chunks).strip()


def _case_vessel_unit_1_8_23(case_row: Dict[str, Any]) -> str:
    unit = _first_clean_1_7(case_row.get('service_unit'), case_row.get('patrol_vessel'), case_row.get('kv_vessel'), 'Kystvakten')
    return unit


def _case_place_1_8_23(case_row: Dict[str, Any]) -> str:
    return _first_clean_1_7(case_row.get('location_name'), _area_name_value(case_row), _where_line_1_7(case_row), 'kontrollstedet')


def _case_time_phrase_1_8_23(case_row: Dict[str, Any]) -> str:
    when = _fmt_datetime(case_row.get('start_time'))
    return when if when and when != '-' else 'kontrolltidspunktet'


def _offence_title_from_block_1_8_23(block: Dict[str, Any]) -> str:
    key = str(block.get('key') or '').strip().lower()
    title = str(block.get('title') or '').strip()
    mapping = {
        'hummer_minstemal': 'Fangst og oppbevaring av hummer under minstemål',
        'hummer_maksimalmal': 'Fangst og oppbevaring av hummer på eller over maksimalmål',
        'hummer_lengdekrav': 'Fangst og oppbevaring av hummer utenfor tillatt lengdekrav',
        'hummer_rogn': 'Fangst og oppbevaring av rognhummer',
        'vak_merking': 'Mangelfull merking av vak/blåse',
        'hummer_merking': 'Mangelfull merking av vak/blåse',
        'teiner_ruser_merking_rekreasjon': 'Mangelfull merking av teine/ruse',
        'hummer_fluktapning': 'Hummerteine uten påbudt fluktåpning',
        'hummer_ratentrad': 'Hummerteine uten påbudt rømningshull/råtnetråd',
        'krabbe_fluktapning_fritid': 'Krabbeteine uten påbudt fluktåpning',
        'krabbe_fluktapning_komm': 'Krabbeteine uten påbudt fluktåpning',
        'krabbe_ratentrad': 'Teine uten påbudt rømningshull/råtnetråd',
        'ruse_forbud_periode': 'Fiske med ruse i forbudsperiode',
        'hummerdeltakernummer': 'Fiske etter hummer uten gyldig deltakernummer',
        'samleteine_merking': 'Oppbevaring av hummer i umerket sanketeine/samleteine',
        'hummer_oppbevaring_desember': 'Oppbevaring av hummer i sjø i desember uten innmelding',
        'hummer_antall_teiner_fritid': 'Fiske med flere hummerteiner enn tillatt',
        'hummer_antall_teiner_komm': 'Fiske med flere hummerteiner enn tillatt',
        'hummer_periode': 'Fiske etter hummer utenfor tillatt periode',
        'hummer_fredningsomrade_redskap': 'Fiske i hummerfredningsområde',
        'stengt_omrade_status': 'Fiske i stengt eller forbudsregulert område',
        'fredningsomrade_status': 'Fiske i fredningsområde',
        'maksimalmal_omrade': 'Fiske i maksimalmålområde for hummer',
        'garn_line_merke_utenfor_grunnlinjene': 'Mangelfull endemerking av garn/line',
        'omradekrav': 'Fiske i område med særregler',
    }
    if key in mapping:
        return mapping[key]
    if key.startswith('minstemal_'):
        return title or 'Fangst eller oppbevaring under minstemål'
    return title or 'Mulig brudd på fiskeriregelverket'


def _offence_title(case_row: Dict[str, Any], findings: list[Dict[str, Any]]) -> str:  # type: ignore[override]
    offences = _offence_blocks(case_row, findings)
    if not offences:
        species = (case_row.get('species') or case_row.get('fishery_type') or 'fiskerikontroll')
        return f'Kontroll av {str(species).strip().lower() or "fiskerikontroll"}'
    titles: list[str] = []
    seen: set[str] = set()
    for block in offences:
        title = _offence_title_from_block_1_8_23(block)
        if title and title.lower() not in seen:
            seen.add(title.lower())
            titles.append(title)
    if len(titles) == 1:
        return titles[0]
    return '; '.join(titles[:4]) + (' m.fl.' if len(titles) > 4 else '')


def _offence_fact_sentence_1_8_23(case_row: Dict[str, Any], block: Dict[str, Any], idx: int | None = None) -> str:
    title = _offence_title_from_block_1_8_23(block)
    details = _shorten_sentence_1_8_21(block.get('details'), 230)
    text = title
    if details:
        # Fjern overflødig posisjonsdublett fra eldre detaljer dersom setningen allerede er lang.
        details = re.sub(r'Kontrollposisjon:\s*[^.]+\.', '', details).strip()
        if details:
            text += f': {details}'
    return _sentence_1_7(text)


def _basis_intro_for_case_1_8_23(case_row: Dict[str, Any], findings: list[Dict[str, Any]]) -> str:
    basis = _normal_case_basis_1_8_22(case_row.get('case_basis'))
    unit = _case_vessel_unit_1_8_23(case_row)
    when = _case_time_phrase_1_8_23(case_row)
    place = _case_place_1_8_23(case_row)
    topic = _topic_1_7(case_row).lower()
    area = _first_clean_1_7(case_row.get('area_name'), case_row.get('area_status'))
    area_sentence = ''
    if area and area.lower() not in {'ingen treff', 'ikke oppgitt'}:
        area_sentence = f' Kontrollstedet ble samtidig vurdert opp mot registrert område: {area}.'
    if basis == 'tips':
        source = _first_clean_1_7(case_row.get('basis_source_name'))
        tip = _strip_generated_report_noise_1_8_21(case_row.get('basis_details'))
        if _looks_like_old_generated_basis_1_8_22(tip):
            tip = ''
        source_text = f' fra {source}' if source else ''
        tip_text = f' om {tip.lower()}' if tip and len(tip) < 180 else ''
        return (f'{unit} gjennomførte den {when} fiskerioppsyn ved {place} etter tips eller opplysninger{source_text}{tip_text}. '
                f'Tipsopplysningene er bakgrunn for kontrollen. Rapporten bygger på patruljens egne observasjoner og dokumentasjon på stedet.{area_sentence}').strip()
    return (f'{unit} var den {when} på fiskeripatrulje ved {place}. '
            f'Patruljeformålet var å kontrollere {topic} og etterlevelse av relevante regler om redskap, merking, fangst/oppbevaring, posisjon og eventuelle områdebestemmelser.{area_sentence}').strip()


def _looks_like_old_generated_basis_1_8_22(value: str) -> bool:  # type: ignore[override]
    lowered = str(value or '').strip().lower()
    if not lowered:
        return True
    markers = (
        'anmeldelsesegnet form',
        'registrert anmeldelse',
        'involverte personer',
        'kontrollert person/fartøy',
        'formålet var å kontrollere faktiske forhold',
        'tekstutkastet er skrevet kortfattet',
        'identifisere relevante personer og kontrollobjekt',
        'identifisere involverte',
        'rapportteksten bygger på patruljens egne observasjoner',
        'stedlig fiskerikontroll',
        'formålet var å kontrollere observerbare forhold',
        'kontrollen ble gjennomført som del av patrulje- og kontrollvirksomhet',
    )
    return any(marker in lowered for marker in markers)


def build_control_reason(case_row: Dict[str, Any], findings: list[Dict[str, Any]]) -> str:  # type: ignore[override]
    override = str(case_row.get('basis_details') or '').strip()
    if override and not _looks_like_old_generated_basis_1_8_22(override):
        return _clean_standard_text_1_7(override, case_row)
    return _clean_standard_text_1_7(_basis_intro_for_case_1_8_23(case_row, findings), case_row)


def _format_avvik_lines_1_8_23(findings: list[Dict[str, Any]]) -> list[str]:
    avvik = _avvik_1_7(findings)
    if not avvik:
        return ['Det ble ikke registrert avvik i kontrollpunktene på tidspunktet rapporten ble laget.']
    rows: list[str] = []
    for idx, item in enumerate(avvik, start=1):
        label = _finding_label_v91(item, idx)
        note = _first_clean_1_7(item.get('notes'), item.get('auto_note'), item.get('display_notes'), item.get('summary_text'))
        line = label
        if note:
            line += f': {_shorten_sentence_1_8_21(note, 260)}'
        rows.append(_sentence_1_7(line))
    return rows


def _build_short_complaint(case_row: Dict[str, Any], findings: list[Dict[str, Any]], sources: list[Dict[str, Any]]) -> str:  # type: ignore[override]
    override = str(case_row.get('complaint_override') or '').strip()
    if override:
        return _clean_standard_text_1_7(_strip_doc_heading_1_8_23(override), case_row)
    subject = _report_subject_1_8_22(case_row, for_complaint=True)
    when = _case_time_phrase_1_8_23(case_row)
    place = _case_place_1_8_23(case_row)
    unit = _case_vessel_unit_1_8_23(case_row)
    offences = _offence_blocks(case_row, findings)
    lines: list[str] = []
    if offences:
        if subject.lower() == 'ukjent gjerningsperson':
            lines.append(f'Med dette anmeldes forhold avdekket ved fiskerikontroll {when} ved {place}.')
        else:
            lines.append(f'{subject} anmeldes for forhold avdekket ved fiskerikontroll {when} ved {place}.')
        if len(offences) == 1:
            lines.append(f'Forholdet gjelder {_offence_title_from_block_1_8_23(offences[0]).lower()}.')
        else:
            lines.append('Forholdene gjelder: ' + '; '.join(_offence_title_from_block_1_8_23(block).lower() for block in offences) + '.')
        lines.append(build_control_reason(case_row, findings))
        lines.append('')
        lines.append('Kort beskrivelse av forholdet:')
        for idx, block in enumerate(offences, start=1):
            lines.append(f'{idx}. {_offence_fact_sentence_1_8_23(case_row, block, idx)}')
    else:
        lines.append(f'Det ble gjennomført fiskerikontroll {when} ved {place}. Det er ikke registrert avvik i kontrollpunktene som danner grunnlag for anmeldelse.')
        lines.append(build_control_reason(case_row, findings))
    refs = _registered_avvik_ref_rows_1_8_21(case_row, findings)
    if refs:
        lines.append('')
        lines.append('Aktuelle lovhjemler er begrenset til registrerte avvik og fremgår av hjemmelsfeltet i anmeldelsen.')
    evidence_docs = ['egenrapport', 'beslagsrapport', 'illustrasjonsmappe/fotomappe']
    if _has_interview_report_content_1_8_21(case_row):
        evidence_docs.append('avhørsrapport')
    if offences:
        lines.append('')
        lines.append('For nærmere detaljer om de faktiske forholdene vises det til sakens ' + ', '.join(evidence_docs) + '.')
    return _clean_standard_text_1_7('\n'.join(line for line in lines if line is not None).strip(), case_row)


def _build_own_report(case_row: Dict[str, Any], findings: list[Dict[str, Any]]) -> str:  # type: ignore[override]
    override = str(case_row.get('own_report_override') or '').strip()
    if override:
        return _clean_standard_text_1_7(_strip_doc_heading_1_8_23(override), case_row)
    investigator = _first_clean_1_7(case_row.get('investigator_name'), 'rapportskriver')
    unit = _case_vessel_unit_1_8_23(case_row)
    when = _case_time_phrase_1_8_23(case_row)
    place = _case_place_1_8_23(case_row)
    topic = _topic_1_7(case_row).lower()
    crew = _crew_text(case_row)
    external = _external_text(case_row)
    subject = _report_subject_1_8_22(case_row)
    lines: list[str] = []
    lines.append(f'Den {when} var {unit} på fiskeripatrulje/oppsyn ved {place}.')
    lines.append(f'Jeg, {investigator}, deltok i kontrollen. Kontrolltema var {topic}.')
    if crew and crew != '-':
        lines.append(f'Øvrige i patrulje-/inspeksjonslaget var: {crew}.')
    if external and external != '-':
        lines.append(f'Eksterne aktører eller opplysningskilder i saken: {external}.')
    basis = build_control_reason(case_row, findings)
    if basis:
        lines.append(basis)
    if subject and subject.lower() != 'kontrollobjektet':
        lines.append(f'Kontrollobjekt/ansvarlig som er registrert i saken: {subject}.')
    else:
        lines.append('Kontrollobjekt/ansvarlig er ikke særskilt identifisert i person-/fartøyfeltene.')
    avvik = _avvik_1_7(findings)
    if avvik:
        lines.append('Under kontrollen ble følgende forhold registrert som avvik:')
        for idx, item in enumerate(avvik, start=1):
            label = _finding_label_v91(item, idx)
            note = _first_clean_1_7(item.get('notes'), item.get('auto_note'), item.get('display_notes'), item.get('summary_text'))
            sentence = label
            if note:
                sentence += f': {_shorten_sentence_1_8_21(note, 280)}'
            lines.append(f'{idx}. {_sentence_1_7(sentence)}')
    else:
        lines.append('Det ble ikke registrert avvik i kontrollpunktene på tidspunktet rapporten ble laget.')
    if _seizure_rows_1_7(case_row, findings):
        lines.append('På bakgrunn av observasjonene ble redskap/beslag dokumentert i egen beslagsrapport. Relevante bilder og kart er tatt inn i illustrasjonsmappe/fotomappe.')
    else:
        lines.append('Relevante bilder, kart og øvrig dokumentasjon er tatt inn i illustrasjonsmappe/fotomappe der dette er registrert.')
    if _has_interview_report_content_1_8_21(case_row):
        lines.append('Gjennomført avhør/forklaring er protokollert i egen avhørsrapport.')
    notes = _strip_generated_report_noise_1_8_21(case_row.get('notes'))
    if notes:
        lines.append('Kontrollørs merknad: ' + _shorten_sentence_1_8_21(notes, 520))
    return _clean_standard_text_1_7('\n\n'.join(lines), case_row)


def build_summary(case_row: Dict[str, Any], findings: list[Dict[str, Any]]) -> str:  # type: ignore[override]
    if (case_row.get('summary') or '').strip():
        return _clean_standard_text_1_7(case_row.get('summary'), case_row)
    when = _case_time_phrase_1_8_23(case_row)
    place = _case_place_1_8_23(case_row)
    topic = _topic_1_7(case_row).lower()
    subject = _report_subject_1_8_22(case_row)
    offences = _offence_blocks(case_row, findings)
    lines: list[str] = [
        'Oppsummering / rapportgrunnlag',
        '',
        f'Kontrollen ble gjennomført {when} ved {place}. Kontrolltema var {topic}.',
        _subject_line_1_8_22(subject),
        build_control_reason(case_row, findings),
        '',
        'Registrerte avvik:',
    ]
    lines.extend(_format_avvik_lines_1_8_23(findings))
    if offences:
        lines.extend(['', 'Anmeldt forhold:', _offence_title(case_row, findings)])
    lines.append('')
    lines.append('Dokumentasjon fremgår av egenrapport, beslagsrapport og illustrasjonsmappe/fotomappe. Avhørsrapport tas bare med når avhør er merket gjennomført.')
    return _clean_standard_text_1_7('\n'.join(lines), case_row)


def _image_caption_base_1_8_23(item: Dict[str, Any], idx: int) -> str:
    raw = _first_clean_1_7(item.get('caption'), item.get('original_filename'), item.get('filename'), f'foto {idx}')
    raw = re.sub(r'\s+', ' ', raw).strip(' .')
    low = raw.lower()
    if low.startswith('bilde viser') or low.startswith('foto viser'):
        base = raw[0].upper() + raw[1:]
    elif low.startswith('oversiktskart') or low.startswith('detaljert oversiktskart') or low.startswith('kartutsnitt'):
        base = 'Bilde viser ' + raw[0].lower() + raw[1:]
    else:
        base = 'Bilde viser ' + raw[0].lower() + raw[1:] if raw else f'Bilde viser foto {idx}'
    if not base.endswith('.'):
        base += '.'
    return base


def _build_illustration_texts(evidence_rows: list[Dict[str, Any]]) -> list[str]:  # type: ignore[override]
    if not evidence_rows:
        return ['Ingen illustrasjoner registrert i saken.']
    texts: list[str] = []
    for idx, item in enumerate(evidence_rows, start=1):
        finding_key = str(item.get('finding_key') or '').strip().lower()
        caption = str(item.get('caption') or '').strip()
        filename = str(item.get('filename') or item.get('generated_path') or '').strip().lower()
        if finding_key == 'oversiktskart':
            if '2km' in filename or '5km' in filename or caption.lower().startswith('detaljert'):
                texts.append('Bilde viser detaljert kartutsnitt med kontrollposisjon og registrerte avviks-/beslagsposisjoner.')
            else:
                texts.append('Bilde viser oversiktskart av kontrollposisjon.')
            continue
        base = _image_caption_base_1_8_23(item, idx)
        seizure = _first_clean_1_7(item.get('seizure_ref'))
        reason = _shorten_sentence_1_8_21(item.get('violation_reason'), 140)
        extras: list[str] = []
        if seizure:
            extras.append(f'Beslag {seizure}')
        if reason:
            extras.append(f'Avvik: {reason}')
        if extras:
            base = base.rstrip('.') + ' - ' + ' - '.join(extras) + '.'
        texts.append(base)
    return texts


def build_text_drafts(case_row: Dict[str, Any], findings: list[Dict[str, Any]]) -> Dict[str, str]:  # type: ignore[override]
    return {
        'summary': build_summary(case_row, findings),
        'basis_details': build_control_reason(case_row, findings),
        'notes': '',
        'complaint_preview': _build_short_complaint(case_row, findings, _safe_sources(case_row)),
        'source_label': 'straffesaksmal 1.8.27',
    }

# 1.8.23a: small precision fixes for dates, law excerpts and tips/patrol basis text.
def _case_time_phrase_1_8_23(case_row: Dict[str, Any]) -> str:  # type: ignore[override]
    raw = str(case_row.get('start_time') or '').strip()
    if raw and re.match(r'^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}', raw):
        raw = raw[:16]
    when = _fmt_datetime(raw)
    return when if when and when != '-' else 'kontrolltidspunktet'


def _law_excerpt_1_8_23(ref: Dict[str, Any], limit: int = 360) -> str:  # type: ignore[override]
    text = _clean_law_text_1_8_23(ref.get('law_text'))
    if not text:
        return ''
    stop_patterns = [
        r'\bNavn på gytefelt\b', r'\bIndre Oslofjord\b', r'\bMossesundet\b', r'\bSletterhausen\b',
        r'\bHvaler\b', r'\bPunktPosisjon\b', r'\bAvgrenset i\b', r'\bSjøområdet innenfor\b'
    ]
    for pattern in stop_patterns:
        m = re.search(pattern, text, flags=re.IGNORECASE)
        if m and m.start() > 60:
            text = text[:m.start()].strip(' ,.;:')
            break
    colon_pos = text.find(':')
    if 45 < colon_pos < min(limit, 260):
        excerpt = text[:colon_pos + 1]
    else:
        protected = re.sub(r'(?<=\d)\.\s+(?=[a-zæøå])', '. ', text)
        # Avoid splitting dates like "30. april" by using semicolon/period with uppercase/quote as safer boundaries.
        parts = re.split(r'(?<=[.!?])\s+(?=[A-ZÆØÅ«])', protected)
        excerpt = ' '.join(part.strip() for part in parts[:2] if part.strip()) or protected
    if len(excerpt) > limit:
        excerpt = excerpt[:limit].rsplit(' ', 1)[0].rstrip(' ,.;:') + '...'
    return excerpt.strip()


def _display_ref_row_1_8_23(ref: Dict[str, Any]) -> Dict[str, str]:  # type: ignore[override]
    excerpt = _law_excerpt_1_8_23(ref, 360)
    return {
        'name': str(ref.get('name') or '').strip(),
        'ref': str(ref.get('ref') or '').strip(),
        'law_text': excerpt,
        'excerpt': excerpt,
    }


def _registered_avvik_ref_rows_1_8_21(case_row: Dict[str, Any], findings: list[Dict[str, Any]] | None = None) -> list[Dict[str, str]]:  # type: ignore[override]
    raw_rows = _registered_avvik_ref_rows_before_1_8_23(case_row, findings)
    return _merge_ref_rows([_display_ref_row_1_8_23(row) for row in raw_rows])


def _full_ref_rows(case_row: Dict[str, Any]) -> list[Dict[str, str]]:  # type: ignore[override]
    return _registered_avvik_ref_rows_1_8_21(case_row)


def _refs_to_text(refs: list[Dict[str, str]]) -> str:  # type: ignore[override]
    chunks: list[str] = []
    for ref in refs:
        head = _legal_ref_head_1_8_23(ref)
        excerpt = str(ref.get('excerpt') or ref.get('law_text') or '').strip()
        if head:
            chunks.append(head)
        if excerpt:
            chunks.append('Utdrag: ' + excerpt)
        if head or excerpt:
            chunks.append('')
    return '\n'.join(chunks).strip()


def _offence_title_from_block_1_8_23(block: Dict[str, Any]) -> str:  # type: ignore[override]
    key = str(block.get('key') or '').strip().lower()
    title = str(block.get('title') or '').strip()
    mapping = {
        'hummer_minstemal': 'Fangst og oppbevaring av hummer under minstemål',
        'hummer_maksimalmal': 'Fangst og oppbevaring av hummer på eller over maksimalmål',
        'hummer_lengdekrav': 'Fangst og oppbevaring av hummer utenfor tillatt lengdekrav',
        'hummer_rogn': 'Fangst og oppbevaring av rognhummer',
        'vak_merking': 'Mangelfull merking av vak/blåse',
        'hummer_merking': 'Mangelfull merking av vak/blåse',
        'teiner_ruser_merking_rekreasjon': 'Mangelfull merking av teine/ruse',
        'hummer_fluktapning': 'Hummerteine uten påbudt fluktåpning',
        'hummer_ratentrad': 'Hummerteine uten påbudt rømningshull/råtnetråd',
        'krabbe_fluktapning_fritid': 'Krabbeteine uten påbudt fluktåpning',
        'krabbe_fluktapning_komm': 'Krabbeteine uten påbudt fluktåpning',
        'krabbe_ratentrad': 'Teine uten påbudt rømningshull/råtnetråd',
        'ruse_forbud_periode': 'Fiske med ruse i forbudsperiode',
        'hummerdeltakernummer': 'Fiske etter hummer uten gyldig deltakernummer',
        'samleteine_merking': 'Oppbevaring av hummer i umerket sanketeine/samleteine',
        'hummer_oppbevaring_desember': 'Oppbevaring av hummer i sjø i desember uten innmelding',
        'hummer_antall_teiner_fritid': 'Fiske med flere teiner enn tillatt',
        'hummer_antall_teiner_komm': 'Fiske med flere teiner enn tillatt',
        'hummer_periode': 'Fiske etter hummer utenfor tillatt periode',
        'hummer_fredningsomrade_redskap': 'Fiske i hummerfredningsområde',
        'stengt_omrade_status': 'Fiske i stengt eller forbudsregulert område',
        'fredningsomrade_status': 'Fiske i fredningsområde',
        'maksimalmal_omrade': 'Fiske i maksimalmålområde for hummer',
        'garn_line_merke_utenfor_grunnlinjene': 'Mangelfull endemerking av garn/line',
        'omradekrav': 'Fiske i område med særregler',
    }
    if key in mapping:
        return mapping[key]
    if key.startswith('minstemal_'):
        return title or 'Fangst eller oppbevaring under minstemål'
    return title or 'Mulig brudd på fiskeriregelverket'


def build_control_reason(case_row: Dict[str, Any], findings: list[Dict[str, Any]]) -> str:  # type: ignore[override]
    override = str(case_row.get('basis_details') or '').strip()
    basis = _normal_case_basis_1_8_22(case_row.get('case_basis'))
    if override and not _looks_like_old_generated_basis_1_8_22(override):
        cleaned_override = _clean_standard_text_1_7(override, case_row)
        if basis == 'tips' and 'patruljens egne observasjoner' not in cleaned_override.lower() and len(cleaned_override) < 260:
            source = _first_clean_1_7(case_row.get('basis_source_name'))
            source_text = f' fra {source}' if source else ''
            return _clean_standard_text_1_7(
                f'Kontrollen ble gjennomført etter tips eller opplysninger{source_text}: {cleaned_override}. Tipsopplysningene er bakgrunn for kontrollen. Rapporten bygger på patruljens egne observasjoner og dokumentasjon på stedet.',
                case_row,
            )
        return cleaned_override
    return _clean_standard_text_1_7(_basis_intro_for_case_1_8_23(case_row, findings), case_row)

# ---- 1.8.27: compact avvik UI text and IKV-style report wording ----
# These overrides keep the generated documents closer to Kystvakten/IKV examples:
# short anmeldelse, only relevant law excerpts, concise egenrapport and photo text.

_POSITION_RE_1_8_24 = re.compile(
    r'\s*(?:/|;|,)?\s*(?:kontrollposisjon|posisjon|startposisjon\s+lenke|sluttposisjon\s+lenke|lenke\s*\d+\s*:\s*start)\s*[: ]\s*'
    r'(?:N\s*)?\d{1,2}[^.;,\n]*(?:Ø|O|E)\s*\d{1,3}[^.;,\n]*',
    flags=re.IGNORECASE,
)


def _strip_position_phrases_1_8_24(value: Any) -> str:
    text = re.sub(r'\s+', ' ', str(value or '')).strip()
    if not text:
        return ''
    prev = None
    while prev != text:
        prev = text
        text = _POSITION_RE_1_8_24.sub('', text)
    text = re.sub(r'\s*/\s*(?=[.;,]|$)', '', text)
    text = re.sub(r'\s*;\s*(?=[.;,]|$)', '', text)
    text = re.sub(r'\s{2,}', ' ', text).strip(' ;,.-')
    return text


def _compact_law_excerpt_1_8_24(ref: Dict[str, Any], limit: int = 260) -> str:
    text = _clean_law_text_1_8_23(ref.get('law_text'))
    if not text:
        text = str(ref.get('excerpt') or '').strip()
    if not text:
        return ''
    # Keep only the first legally useful sentence/fragment. Drop long area lists,
    # coordinates, tables and full Lovdata text that clutter the complaint.
    stop_patterns = [
        r'\bNavn på gytefelt\b', r'\bPunktPosisjon\b', r'\bAvgrenset i\b',
        r'\bSjøområdet innenfor\b', r'\bFølgende områder\b', r'\bKoordinat\b',
        r'\bIndre Oslofjord\b', r'\bMossesundet\b', r'\bHvaler\b', r'\bSletterhausen\b',
    ]
    for pattern in stop_patterns:
        m = re.search(pattern, text, flags=re.IGNORECASE)
        if m and m.start() > 35:
            text = text[:m.start()].strip(' ,.;:')
            break
    # Prefer text up to a colon when it is an introductory legal norm.
    colon_pos = text.find(':')
    if 45 < colon_pos < 220:
        excerpt = text[:colon_pos + 1]
    else:
        parts = re.split(r'(?<=[.!?])\s+(?=[A-ZÆØÅ«])', text)
        excerpt = ' '.join(p.strip() for p in parts[:2] if p.strip()) or text
    excerpt = re.sub(r'\s+', ' ', excerpt).strip(' ;,')
    if len(excerpt) > limit:
        excerpt = excerpt[:limit].rsplit(' ', 1)[0].rstrip(' ,.;:') + '...'
    return excerpt


def _display_ref_row_1_8_24(ref: Dict[str, Any]) -> Dict[str, str]:
    head_name = str(ref.get('name') or ref.get('law_name') or '').strip()
    head_ref = str(ref.get('ref') or ref.get('section') or '').strip()
    excerpt = _compact_law_excerpt_1_8_24(ref, 260)
    return {
        'name': head_name,
        'ref': head_ref,
        'law_text': excerpt,
        'excerpt': excerpt,
    }


def _registered_avvik_ref_rows_1_8_21(case_row: Dict[str, Any], findings: list[Dict[str, Any]] | None = None) -> list[Dict[str, str]]:  # type: ignore[override]
    findings = findings if findings is not None else _safe_findings(case_row)
    rows: list[Dict[str, str]] = []
    for block in _offence_blocks(case_row, findings):
        for ref in block.get('legal_refs') or []:
            if isinstance(ref, dict):
                rows.append(_display_ref_row_1_8_24(ref))
    if not rows:
        # Fallback, but still restrict through existing avvik-aware function when possible.
        try:
            raw_rows = _registered_avvik_ref_rows_before_1_8_23(case_row, findings)
        except Exception:
            raw_rows = []
        rows = [_display_ref_row_1_8_24(row) for row in raw_rows if isinstance(row, dict)]
    return _merge_ref_rows(rows)


def _full_ref_rows(case_row: Dict[str, Any]) -> list[Dict[str, str]]:  # type: ignore[override]
    return _registered_avvik_ref_rows_1_8_21(case_row)


def _refs_to_text(refs: list[Dict[str, str]]) -> str:  # type: ignore[override]
    chunks: list[str] = []
    for ref in refs or []:
        head = _legal_ref_head_1_8_23(ref)
        excerpt = str(ref.get('excerpt') or ref.get('law_text') or '').strip()
        if head:
            chunks.append(head)
        if excerpt:
            chunks.append('Utdrag: ' + excerpt)
        if head or excerpt:
            chunks.append('')
    return '\n'.join(chunks).strip()


def _deviation_summary(item: Dict[str, Any]) -> str:  # type: ignore[override]
    rows = _deviation_rows(item)
    if not rows:
        return ''
    parts: list[str] = []
    for idx, row in enumerate(rows, start=1):
        seizure_ref = str(row.get('seizure_ref') or '').strip() or f'Beslag {idx}'
        gear_kind = str(row.get('gear_kind') or row.get('type') or '').strip()
        quantity = str(row.get('quantity') or '').strip()
        violation = _strip_position_phrases_1_8_24(row.get('violation') or row.get('violation_reason') or '').strip()
        note = _strip_position_phrases_1_8_24(row.get('note') or '').strip()
        head = ' - '.join([part for part in [seizure_ref, gear_kind] if part])
        bits = [head]
        if quantity:
            bits.append(f'antall {quantity}')
        if violation:
            bits.append(violation)
        elif note:
            bits.append(note)
        parts.append(': '.join([bits[0], '; '.join(bits[1:])]) if len(bits) > 1 else bits[0])
    return '; '.join(part for part in parts if part).strip()


def _finding_display_note(item: Dict[str, Any]) -> str:  # type: ignore[override]
    base_parts = [
        _strip_position_phrases_1_8_24(item.get('notes')),
        _strip_position_phrases_1_8_24(item.get('auto_note')),
        _measurement_summary(item),
        _marker_summary(item),
        _deviation_summary(item),
    ]
    text = ' '.join(part for part in base_parts if part).strip()
    return _strip_position_phrases_1_8_24(text)


def _finding_note(item: Dict[str, Any]) -> str:  # type: ignore[override]
    return _finding_display_note(item)


def _short_avvik_lines_1_8_24(findings: list[Dict[str, Any]], *, limit: int = 240) -> list[str]:
    avvik = _avvik_1_7(findings)
    if not avvik:
        return ['Det er ikke registrert avvik i kontrollpunktene på tidspunktet rapporten ble laget.']
    rows: list[str] = []
    for idx, item in enumerate(avvik, start=1):
        label = _finding_label_v91(item, idx)
        note = _strip_position_phrases_1_8_24(_first_clean_1_7(item.get('display_notes'), item.get('notes'), item.get('auto_note'), item.get('summary_text')))
        line = label
        if note:
            line += ': ' + _shorten_sentence_1_8_21(note, limit)
        rows.append(f'{idx}. {_sentence_1_7(line)}')
    return rows


def _collect_seizure_rows_from_findings(findings: list[Dict[str, Any]]) -> list[Dict[str, Any]]:  # type: ignore[override]
    rows: list[Dict[str, Any]] = []
    for item in findings or []:
        if str(item.get('status') or '').lower() != 'avvik':
            continue
        finding_key = str(item.get('key') or '').strip()
        caption = str(item.get('label') or item.get('key') or 'Avvik').strip()
        law_text = str(item.get('law_text') or item.get('help_text') or '').strip()
        for idx, row in enumerate(_deviation_rows(item), start=1):
            violation = _strip_position_phrases_1_8_24(row.get('violation') or '') or _strip_position_phrases_1_8_24(_finding_display_note(item))
            rows.append({
                'finding_key': finding_key,
                'caption': caption,
                'seizure_ref': str(row.get('seizure_ref') or '').strip() or f'{str(item.get("key") or "AVVIK").upper()}-{idx:02d}',
                'gear_kind': str(row.get('gear_kind') or '').strip(),
                'gear_ref': str(row.get('gear_ref') or '').strip(),
                'quantity': str(row.get('quantity') or '').strip() or '1',
                'position': str(row.get('position') or '').strip(),
                'linked_seizure_ref': str(row.get('linked_seizure_ref') or '').strip(),
                'violation_reason': violation,
                'description': violation,
                'law_text': law_text,
                'note': _strip_position_phrases_1_8_24(row.get('note') or ''),
                'photo_ref': str(row.get('photo_ref') or '').strip(),
            })
        measurements = item.get('measurements') or []
        if isinstance(measurements, list):
            for idx, row in enumerate(measurements, start=1):
                if not isinstance(row, dict):
                    continue
                seizure_ref = str(row.get('seizure_ref') or row.get('reference') or '').strip() or f'{str(item.get("key") or "MALING").upper()}-M{idx:02d}'
                length = str(row.get('length_cm') or '').strip()
                delta_text = str(row.get('delta_text') or '').strip()
                violation_reason = str(row.get('violation_text') or '').strip()
                if not violation_reason:
                    if length and delta_text:
                        violation_reason = f'Kontrollmålt til {length} cm - {delta_text}.'
                    elif length:
                        violation_reason = f'Kontrollmålt til {length} cm.'
                    else:
                        violation_reason = _strip_position_phrases_1_8_24(_finding_display_note(item))
                rows.append({
                    'finding_key': finding_key,
                    'caption': caption,
                    'seizure_ref': seizure_ref,
                    'gear_kind': 'Lengdemåling',
                    'gear_ref': '',
                    'quantity': '1',
                    'position': str(row.get('position') or '').strip(),
                    'linked_seizure_ref': str(row.get('linked_seizure_ref') or '').strip(),
                    'violation_reason': _strip_position_phrases_1_8_24(violation_reason),
                    'description': _strip_position_phrases_1_8_24(violation_reason),
                    'law_text': law_text,
                    'note': _strip_position_phrases_1_8_24(row.get('note') or ''),
                    'photo_ref': str(row.get('photo_ref') or '').strip(),
                })
    return rows


def _stored_seizure_rows_v93(case_row: Dict[str, Any], findings: list[Dict[str, Any]], evidence_rows: Iterable[Dict[str, Any]]) -> list[Dict[str, Any]]:  # type: ignore[override]
    stored = _parse_json_list_v93(case_row.get('seizure_reports_json'))
    generated = _collect_seizure_rows_from_findings(findings)
    result: list[Dict[str, Any]] = []
    by_key: dict[str, Dict[str, Any]] = {}
    for row in stored + generated:
        if not isinstance(row, dict):
            continue
        clone = dict(row)
        for key in ('description', 'violation_reason', 'note'):
            clone[key] = _strip_position_phrases_1_8_24(clone.get(key))
        key = str(clone.get('source_key') or clone.get('seizure_ref') or clone.get('caption') or len(result)).strip()
        if key in by_key:
            by_key[key].update({k: v for k, v in clone.items() if v not in (None, '', [])})
        else:
            by_key[key] = clone
            result.append(clone)
    for ev in evidence_rows or []:
        ref = str((ev or {}).get('seizure_ref') or '').strip()
        if not ref:
            continue
        target = None
        for row in result:
            if str(row.get('seizure_ref') or '').strip() == ref:
                target = row
                break
        if target is None:
            target = {
                'seizure_ref': ref,
                'type': 'Bildebevis',
                'description': _strip_position_phrases_1_8_24((ev or {}).get('caption') or (ev or {}).get('original_filename') or ''),
            }
            result.append(target)
        target.setdefault('evidence_refs', [])
        label = _first_clean_1_7((ev or {}).get('caption'), (ev or {}).get('original_filename'), (ev or {}).get('id'), 'bilde')
        if label and label not in target['evidence_refs']:
            target['evidence_refs'].append(label)
    return result


def _seizure_rows_1_7(case_row: Dict[str, Any], findings: list[Dict[str, Any]]) -> list[Dict[str, Any]]:  # type: ignore[override]
    try:
        return _stored_seizure_rows_v93(case_row, findings, [])
    except Exception:
        return _parse_json_list_v93(case_row.get('seizure_reports_json'))


def _build_seizure_report(case_row: Dict[str, Any], evidence_rows: list[Dict[str, Any]]) -> str:  # type: ignore[override]
    rows = _stored_seizure_rows_v93(case_row, _safe_findings(case_row), evidence_rows)
    override = str(case_row.get('seizure_report_override') or '').strip()
    if not rows and not override:
        return 'Det er ikke registrert beslag i saken.'
    lines = ['Beslagsrapport', '']
    place = _location_line(case_row)
    if place and place != '-':
        lines.append(f'Kontrollsted: {place}.')
    lines.append(f'Ledet av: {_fmt_value(case_row.get("investigator_name"))}.')
    if rows:
        lines.extend(['', 'Registrerte beslag:'])
        for idx, row in enumerate(rows, start=1):
            ref = _first_clean_1_7(row.get('seizure_ref'), f'Beslag {idx}')
            kind = _first_clean_1_7(row.get('gear_kind'), row.get('type'), 'redskap/beslag')
            qty = _first_clean_1_7(row.get('quantity'))
            desc = _strip_position_phrases_1_8_24(_first_clean_1_7(row.get('description'), row.get('violation_reason'), row.get('caption'), 'registrert avvik'))
            note = _strip_position_phrases_1_8_24(row.get('note'))
            pos = _first_clean_1_7(row.get('position'))
            ev = ', '.join([str(x) for x in row.get('evidence_refs') or [] if str(x).strip()])
            first = f'{idx}. {ref} - {kind}'
            if qty:
                first += f', antall {qty}'
            first += '.'
            lines.append(first)
            if desc:
                lines.append(f'   Avvik: {_shorten_sentence_1_8_21(desc, 260)}')
            if note and note.lower() not in (desc or '').lower():
                lines.append(f'   Merknad: {_shorten_sentence_1_8_21(note, 220)}')
            if pos:
                lines.append(f'   Posisjon: {pos}.')
            if ev:
                lines.append(f'   Tilknyttede bilder: {_shorten_sentence_1_8_21(ev, 220)}')
    if override:
        lines.extend(['', 'Utfyllende merknader:', _strip_position_phrases_1_8_24(override)])
    return _clean_standard_text_1_7('\n'.join(lines).strip(), case_row)


def _offence_title(case_row: Dict[str, Any], findings: list[Dict[str, Any]]) -> str:  # type: ignore[override]
    titles: list[str] = []
    for block in _offence_blocks(case_row, findings):
        title = _offence_title_from_block_1_8_23(block)
        if title and title not in titles:
            titles.append(title)
    if titles:
        return ', '.join(titles[:4]) + (' m.m.' if len(titles) > 4 else '')
    topic = _topic_1_7(case_row).lower()
    return f'Kontroll av {topic}' if topic and topic != '-' else 'Fiskerikontroll'


def _offence_fact_line_1_8_24(block: Dict[str, Any], idx: int) -> str:
    title = _offence_title_from_block_1_8_23(block)
    details = _strip_position_phrases_1_8_24(block.get('details') or block.get('allegation') or '')
    details = re.sub(r'^Mulig\s+brudd\s+på\s+[^:]+:\s*', '', details, flags=re.IGNORECASE).strip()
    if details and title.lower() not in details.lower():
        text = f'{title}: {details}'
    else:
        text = title
    return f'{idx}. {_shorten_sentence_1_8_21(_sentence_1_7(text), 300)}'


def build_control_reason(case_row: Dict[str, Any], findings: list[Dict[str, Any]]) -> str:  # type: ignore[override]
    override = str(case_row.get('basis_details') or '').strip()
    basis = _normal_case_basis_1_8_22(case_row.get('case_basis'))
    if override and not _looks_like_old_generated_basis_1_8_22(override):
        cleaned = _clean_standard_text_1_7(override, case_row)
        if basis == 'tips' and 'patruljens egne observasjoner' not in cleaned.lower():
            source = _first_clean_1_7(case_row.get('basis_source_name'))
            source_text = f' fra {source}' if source else ''
            cleaned = f'Kontrollen ble gjennomført etter tips/opplysninger{source_text}. Tipsopplysningene var bakgrunn for kontrollen. Rapporten bygger på patruljens egne observasjoner og dokumentasjon på stedet. {cleaned}'
        return _clean_standard_text_1_7(cleaned, case_row)
    unit = _case_vessel_unit_1_8_23(case_row)
    when = _case_time_phrase_1_8_23(case_row)
    place = _case_place_1_8_23(case_row)
    topic = _topic_1_7(case_row).lower()
    source = _first_clean_1_7(case_row.get('basis_source_name'))
    if basis == 'tips':
        source_text = f' fra {source}' if source else ''
        return _clean_standard_text_1_7(
            f'{unit} gjennomførte den {when} kontroll ved {place} etter tips/opplysninger{source_text}. Tipsopplysningene var bakgrunn for kontrollen. Patruljens vurderinger bygger på egne observasjoner, kontroll av redskap og dokumentasjon sikret på stedet.',
            case_row,
        )
    return _clean_standard_text_1_7(
        f'{unit} var den {when} på fiskeripatrulje/oppsyn ved {place}. Patruljeformålet var å kontrollere {topic} og avklare om redskap, merking, fangst/oppbevaring, posisjon og relevante områdebestemmelser var i samsvar med gjeldende regelverk.',
        case_row,
    )


def _subject_status_1_8_24(case_row: Dict[str, Any]) -> str:
    # When beslag is used, known person is normally omtalt as siktede in the complaint.
    has_seizure = bool(_seizure_rows_1_7(case_row, _safe_findings(case_row)))
    return 'siktede' if has_seizure else 'mistenkte'


def _build_short_complaint(case_row: Dict[str, Any], findings: list[Dict[str, Any]], sources: list[Dict[str, Any]]) -> str:  # type: ignore[override]
    override = str(case_row.get('complaint_override') or '').strip()
    if override:
        return _clean_standard_text_1_7(_strip_doc_heading_1_8_23(override), case_row)
    subject = _first_clean_1_7(case_row.get('suspect_name'), case_row.get('vessel_name'), 'ukjent gjerningsperson')
    status_word = _subject_status_1_8_24(case_row)
    when = _case_time_phrase_1_8_23(case_row)
    place = _case_place_1_8_23(case_row)
    unit = _case_vessel_unit_1_8_23(case_row)
    topic = _topic_1_7(case_row).lower()
    offences = _offence_blocks(case_row, findings)
    lines: list[str] = []
    if offences:
        lines.append(f'Med dette anmeldes {subject} for {_offence_title(case_row, findings).lower()} avdekket {when} ved {place}.')
        lines.append(f'Forholdet ble avdekket da {unit} gjennomførte fiskerioppsyn/kontroll. Kontrollen gjaldt {topic}.')
        lines.append('')
        lines.append('Under kontrollen ble følgende forhold registrert:')
        for idx, block in enumerate(offences, start=1):
            lines.append(_offence_fact_line_1_8_24(block, idx))
        refs = _registered_avvik_ref_rows_1_8_21(case_row, findings)
        if refs:
            lines.append('')
            lines.append('Aktuelle lovhjemler er begrenset til lov-/forskriftshenvisninger knyttet til registrerte avvik.')
        evidence_docs = ['egenrapport', 'beslagsrapport', 'illustrasjonsmappe/fotomappe']
        if _has_interview_report_content_1_8_21(case_row):
            evidence_docs.append('avhørsrapport')
        lines.append('')
        lines.append('For nærmere detaljer om faktum og bevissituasjonen vises det til sakens ' + ', '.join(evidence_docs) + '.')
        if subject != 'ukjent gjerningsperson':
            lines.append(f'I den videre teksten omtales {subject} som {status_word}.')
    else:
        lines.append(f'Det ble gjennomført fiskerikontroll av {subject} {when} ved {place}. Det er ikke registrert avvik som danner grunnlag for anmeldelse i kontrollpunktene på tidspunktet for utkastet.')
    return _clean_standard_text_1_7('\n'.join(lines).strip(), case_row)


def _build_own_report(case_row: Dict[str, Any], findings: list[Dict[str, Any]]) -> str:  # type: ignore[override]
    override = str(case_row.get('own_report_override') or '').strip()
    if override:
        return _clean_standard_text_1_7(_strip_doc_heading_1_8_23(override), case_row)
    investigator = _first_clean_1_7(case_row.get('investigator_name'), 'rapportskriver')
    unit = _case_vessel_unit_1_8_23(case_row)
    when = _case_time_phrase_1_8_23(case_row)
    place = _case_place_1_8_23(case_row)
    topic = _topic_1_7(case_row).lower()
    crew = _crew_text(case_row)
    subject = _first_clean_1_7(case_row.get('suspect_name'), case_row.get('vessel_name'))
    lines: list[str] = []
    lines.append(f'Den {when} var {unit} på fiskeripatrulje/oppsyn ved {place}.')
    lines.append(f'Jeg, {investigator}, deltok i kontrollen. Kontrolltema var {topic}.')
    if crew and crew != '-':
        lines.append(f'Patruljen/inspeksjonslaget bestod for øvrig av: {crew}.')
    lines.append('')
    lines.append(build_control_reason(case_row, findings))
    if subject:
        lines.append(f'Kontrollobjekt/ansvarlig registrert i saken er {subject}.')
    avvik = _avvik_1_7(findings)
    if avvik:
        lines.append('')
        lines.append('Under kontrollen ble følgende forhold registrert som avvik:')
        lines.extend(_short_avvik_lines_1_8_24(findings, limit=260))
    else:
        lines.append('')
        lines.append('Det ble ikke registrert avvik i kontrollpunktene på tidspunktet rapporten ble laget.')
    if _seizure_rows_1_7(case_row, findings):
        lines.append('')
        lines.append('Redskap/beslag er ført i egen beslagsrapport. Relevante fotografier og kartutsnitt fremgår av illustrasjonsmappe/fotomappe.')
    elif any(True for _ in findings or []):
        lines.append('')
        lines.append('Relevante fotografier og kartutsnitt fremgår av illustrasjonsmappe/fotomappe der dette er registrert.')
    if _has_interview_report_content_1_8_21(case_row):
        lines.append('Gjennomført avhør/forklaring er protokollert i egen avhørsrapport.')
    notes = _strip_generated_report_noise_1_8_21(case_row.get('notes'))
    notes = _strip_position_phrases_1_8_24(notes)
    if notes:
        lines.append('')
        lines.append('Kontrollørs merknad: ' + _shorten_sentence_1_8_21(notes, 420))
    return _clean_standard_text_1_7('\n\n'.join(line for line in lines if line is not None).strip(), case_row)


def _build_interview_report(case_row: Dict[str, Any]) -> str:  # type: ignore[override]
    if not _has_interview_report_content_1_8_21(case_row):
        return ''
    override = str(case_row.get('interview_report_override') or '').strip()
    if override:
        return _clean_standard_text_1_7(_strip_doc_heading_1_8_23(override), case_row)
    entries = _conducted_interview_entries_1_8_21(case_row)
    lines: list[str] = []
    used = 0
    for entry in entries:
        body = _interview_entry_body_1_8_21(entry)
        if not body:
            continue
        used += 1
        name = _first_clean_1_7(entry.get('name'), case_row.get('suspect_name'), f'avhørt person {used}')
        role = _first_clean_1_7(entry.get('role'), 'mistenkt/siktet')
        method = _first_clean_1_7(entry.get('method'), 'ikke oppgitt')
        place = _first_clean_1_7(entry.get('place'), _place_phrase_1_7(case_row))
        start = _fmt_datetime(entry.get('start') or case_row.get('start_time'))
        end = _fmt_datetime(entry.get('end') or case_row.get('end_time'))
        if used > 1:
            lines.append('')
        lines.append(f'Avhør av {name}')
        lines.append(f'Status/rolle: {role}.')
        lines.append(f'Tid/sted/metode: {start} - {end}, {place}, {method}.')
        lines.append('Forklaring/sammendrag:')
        lines.append(body.strip())
    if used == 0:
        return ''
    return _clean_standard_text_1_7('\n'.join(lines).strip(), case_row)


def _image_caption_base_1_8_24(item: Dict[str, Any], idx: int) -> str:
    raw = _first_clean_1_7(item.get('caption'), item.get('original_filename'), item.get('filename'), f'foto {idx}')
    raw = _strip_position_phrases_1_8_24(raw)
    raw = re.sub(r'\s+', ' ', raw).strip(' .')
    if not raw:
        raw = f'foto {idx}'
    low = raw.lower()
    if low.startswith('bilde viser') or low.startswith('foto viser'):
        text = raw[0].upper() + raw[1:]
    else:
        text = 'Bilde viser ' + raw[0].lower() + raw[1:]
    if not text.endswith('.'):
        text += '.'
    return text


def _build_illustration_texts(evidence_rows: list[Dict[str, Any]]) -> list[str]:  # type: ignore[override]
    if not evidence_rows:
        return ['Ingen illustrasjoner registrert i saken.']
    texts: list[str] = []
    for idx, item in enumerate(evidence_rows, start=1):
        finding_key = str(item.get('finding_key') or '').strip().lower()
        caption = str(item.get('caption') or '').strip()
        filename = str(item.get('filename') or item.get('generated_path') or '').strip().lower()
        if finding_key == 'oversiktskart':
            if '2km' in filename or '5km' in filename or caption.lower().startswith('detaljert'):
                texts.append('Bilde viser detaljert kartutsnitt med kontrollposisjon og registrerte avviks-/beslagsposisjoner.')
            else:
                texts.append('Bilde viser oversiktskart av kontrollposisjon.')
            continue
        base = _image_caption_base_1_8_24(item, idx)
        seizure = _first_clean_1_7(item.get('seizure_ref'))
        reason = _strip_position_phrases_1_8_24(_first_clean_1_7(item.get('violation_reason')))
        extras: list[str] = []
        if seizure:
            extras.append(f'Beslag {seizure}')
        if reason:
            extras.append(f'Avvik: {_shorten_sentence_1_8_21(reason, 120)}')
        if extras:
            base = base.rstrip('.') + ' - ' + ' - '.join(extras) + '.'
        texts.append(_shorten_sentence_1_8_21(base, 240))
    return texts


def build_summary(case_row: Dict[str, Any], findings: list[Dict[str, Any]]) -> str:  # type: ignore[override]
    if (case_row.get('summary') or '').strip():
        return _clean_standard_text_1_7(case_row.get('summary'), case_row)
    when = _case_time_phrase_1_8_23(case_row)
    place = _case_place_1_8_23(case_row)
    topic = _topic_1_7(case_row).lower()
    lines: list[str] = [
        f'Kontrollen ble gjennomført {when} ved {place}. Kontrolltema var {topic}.',
        build_control_reason(case_row, findings),
    ]
    avvik = _avvik_1_7(findings)
    if avvik:
        lines.append('Registrerte avvik:')
        lines.extend(_short_avvik_lines_1_8_24(findings, limit=180))
    else:
        lines.append('Det er ikke registrert avvik i kontrollpunktene.')
    if avvik:
        lines.append('Dokumentasjon fremgår av egenrapport, beslagsrapport og illustrasjonsmappe/fotomappe. Avhørsrapport tas bare med når avhør er merket gjennomført.')
    return _clean_standard_text_1_7('\n'.join(lines), case_row)


_build_case_packet_before_1_8_24 = build_case_packet


def build_case_packet(case_row: Dict[str, Any], evidence_rows: Iterable[Dict[str, Any]]) -> Dict[str, Any]:  # type: ignore[override]
    packet = _build_case_packet_before_1_8_24(case_row, evidence_rows)
    findings = [dict(item, display_notes=_finding_display_note(item)) for item in _safe_findings(case_row)]
    sources = _safe_sources(case_row)
    image_rows = list(packet.get('evidence') or [])
    has_interview = _has_interview_report_content_1_8_21(case_row)
    packet.update({
        'has_offences': bool(_offence_blocks(case_row, findings)),
        'title': _offence_title(case_row, findings),
        'summary': build_summary(case_row, findings),
        'short_complaint': _build_short_complaint(case_row, findings, sources),
        'own_report': _build_own_report(case_row, findings),
        'interview_report': _build_interview_report(case_row) if has_interview else '',
        'interview_guidance': '',
        'interview_not_conducted': not has_interview,
        'seizure_rows': _stored_seizure_rows_v93(case_row, findings, image_rows),
        'seizure_report': _build_seizure_report(case_row, image_rows),
        'illustration_texts': _build_illustration_texts(image_rows),
        'legal_refs': _registered_avvik_ref_rows_1_8_21(case_row, findings),
        'findings': findings,
        'sources': sources,
        'notes': _build_own_report(case_row, findings),
    })
    return packet


def build_text_drafts(case_row: Dict[str, Any], findings: list[Dict[str, Any]]) -> Dict[str, str]:  # type: ignore[override]
    return {
        'summary': build_summary(case_row, findings),
        'basis_details': build_control_reason(case_row, findings),
        'notes': '',
        'complaint_preview': _build_short_complaint(case_row, findings, _safe_sources(case_row)),
        'source_label': 'straffesaksmal 1.8.27',
    }

# 1.8.27a: remove decimal-coordinate repetitions from offence/beslag text.
_DECIMAL_POS_RE_1_8_24 = re.compile(r'\s*(?:/|;|,)?\s*(?:[A-ZÆØÅa-zæøå][^.;\n]{0,90}:\s*)?-?\d{1,3}\.\d{3,}\s*,\s*-?\d{1,3}\.\d{3,}', flags=re.IGNORECASE)


def _strip_position_phrases_1_8_24(value: Any) -> str:  # type: ignore[override]
    text = re.sub(r'\s+', ' ', str(value or '')).strip()
    if not text:
        return ''
    prev = None
    while prev != text:
        prev = text
        text = _POSITION_RE_1_8_24.sub('', text)
        text = _DECIMAL_POS_RE_1_8_24.sub('', text)
    text = re.sub(r'\s*/\s*(?=[.;,]|$)', '', text)
    text = re.sub(r'\s*;\s*(?=[.;,]|$)', '', text)
    text = re.sub(r'\s{2,}', ' ', text).strip(' ;,.-')
    return text


def _offence_fact_line_1_8_24(block: Dict[str, Any], idx: int) -> str:  # type: ignore[override]
    title = _offence_title_from_block_1_8_23(block)
    details = _strip_position_phrases_1_8_24(block.get('details') or block.get('allegation') or '')
    details = re.sub(r'^Mulig\s+brudd\s+på\s+[^:]+:\s*', '', details, flags=re.IGNORECASE).strip()
    details = re.sub(r'\s{2,}', ' ', details).strip(' ;,.-')
    if details and title.lower() not in details.lower():
        text = f'{title}: {details}'
    else:
        text = title
    return f'{idx}. {_shorten_sentence_1_8_21(_sentence_1_7(text), 280)}'


def _build_seizure_report(case_row: Dict[str, Any], evidence_rows: list[Dict[str, Any]]) -> str:  # type: ignore[override]
    rows = _stored_seizure_rows_v93(case_row, _safe_findings(case_row), evidence_rows)
    override = str(case_row.get('seizure_report_override') or '').strip()
    if not rows and not override:
        return 'Det er ikke registrert beslag i saken.'
    lines = ['Beslagsrapport', '']
    place = _case_place_1_8_23(case_row)
    if place and place != '-':
        lines.append(f'Kontrollsted: {place}.')
    lines.append(f'Ledet av: {_fmt_value(case_row.get("investigator_name"))}.')
    if rows:
        lines.extend(['', 'Registrerte beslag:'])
        for idx, row in enumerate(rows, start=1):
            ref = _first_clean_1_7(row.get('seizure_ref'), f'Beslag {idx}')
            kind = _first_clean_1_7(row.get('gear_kind'), row.get('type'), 'redskap/beslag')
            qty = _first_clean_1_7(row.get('quantity'))
            desc = _strip_position_phrases_1_8_24(_first_clean_1_7(row.get('description'), row.get('violation_reason'), row.get('caption'), 'registrert avvik'))
            note = _strip_position_phrases_1_8_24(row.get('note'))
            pos = _first_clean_1_7(row.get('position'))
            ev = ', '.join([str(x) for x in row.get('evidence_refs') or [] if str(x).strip()])
            first = f'{idx}. {ref} - {kind}'
            if qty:
                first += f', antall {qty}'
            first += '.'
            lines.append(first)
            if desc:
                lines.append(f'   Avvik: {_shorten_sentence_1_8_21(desc, 260)}')
            if note and note.lower() not in (desc or '').lower():
                lines.append(f'   Merknad: {_shorten_sentence_1_8_21(note, 220)}')
            if pos:
                lines.append(f'   Posisjon: {pos}.')
            if ev:
                lines.append(f'   Tilknyttede bilder: {_shorten_sentence_1_8_21(ev, 220)}')
    if override:
        lines.extend(['', 'Utfyllende merknader:', _strip_position_phrases_1_8_24(override)])
    return _clean_standard_text_1_7('\n'.join(lines).strip(), case_row)

# 1.8.27b: complaint/egenrapport should not carry full inline beslag summaries.
_INLINE_SEIZURE_RE_1_8_24 = re.compile(r'\s*[A-ZÆØÅ0-9]{2,10}\s*\d{5}-\d{3}\s*(?:[-–]\s*[^:.;]{1,40})?(?::\s*antall\s*\d+)?', flags=re.IGNORECASE)


def _strip_inline_seizure_text_1_8_24(value: Any) -> str:
    text = _strip_position_phrases_1_8_24(value)
    text = _INLINE_SEIZURE_RE_1_8_24.sub('', text)
    text = re.sub(r'\s{2,}', ' ', text).strip(' ;,.-:')
    return text


def _offence_fact_line_1_8_24(block: Dict[str, Any], idx: int) -> str:  # type: ignore[override]
    title = _offence_title_from_block_1_8_23(block)
    details = _strip_inline_seizure_text_1_8_24(block.get('details') or block.get('allegation') or '')
    details = re.sub(r'^Mulig\s+brudd\s+på\s+[^:]+:\s*', '', details, flags=re.IGNORECASE).strip()
    details = re.sub(r'\s{2,}', ' ', details).strip(' ;,.-')
    if details and title.lower() not in details.lower():
        text = f'{title}: {details}'
    else:
        text = title
    return f'{idx}. {_shorten_sentence_1_8_21(_sentence_1_7(text), 260)}'


def _short_avvik_lines_1_8_24(findings: list[Dict[str, Any]], *, limit: int = 240) -> list[str]:  # type: ignore[override]
    avvik = _avvik_1_7(findings)
    if not avvik:
        return ['Det er ikke registrert avvik i kontrollpunktene på tidspunktet rapporten ble laget.']
    rows: list[str] = []
    for idx, item in enumerate(avvik, start=1):
        label = _finding_label_v91(item, idx)
        note = _strip_inline_seizure_text_1_8_24(_first_clean_1_7(item.get('notes'), item.get('auto_note'), item.get('summary_text')))
        line = label
        if note:
            line += ': ' + _shorten_sentence_1_8_21(note, limit)
        rows.append(f'{idx}. {_sentence_1_7(line)}')
    return rows

# 1.8.27c: egenrapport should not repeat time/place from patruljeformål.
def _own_report_basis_1_8_24(case_row: Dict[str, Any], findings: list[Dict[str, Any]]) -> str:
    override = str(case_row.get('basis_details') or '').strip()
    basis = _normal_case_basis_1_8_22(case_row.get('case_basis'))
    if override and not _looks_like_old_generated_basis_1_8_22(override):
        cleaned = _clean_standard_text_1_7(override, case_row)
        if basis == 'tips' and 'tipsopplysningene' not in cleaned.lower():
            return 'Tipsopplysningene var bakgrunn for kontrollen. ' + cleaned
        return cleaned
    topic = _topic_1_7(case_row).lower()
    if basis == 'tips':
        source = _first_clean_1_7(case_row.get('basis_source_name'))
        source_text = f' fra {source}' if source else ''
        return f'Kontrollen ble gjennomført etter tips/opplysninger{source_text}. Tipsopplysningene var bakgrunn for kontrollen. Mine observasjoner og vurderinger bygger på det som ble kontrollert og dokumentert på stedet.'
    return f'Patruljeformålet var å kontrollere {topic} og avklare om redskap, merking, fangst/oppbevaring og relevante områdebestemmelser var i samsvar med gjeldende regelverk.'


def _build_own_report(case_row: Dict[str, Any], findings: list[Dict[str, Any]]) -> str:  # type: ignore[override]
    override = str(case_row.get('own_report_override') or '').strip()
    if override:
        return _clean_standard_text_1_7(_strip_doc_heading_1_8_23(override), case_row)
    investigator = _first_clean_1_7(case_row.get('investigator_name'), 'rapportskriver')
    unit = _case_vessel_unit_1_8_23(case_row)
    when = _case_time_phrase_1_8_23(case_row)
    place = _case_place_1_8_23(case_row)
    topic = _topic_1_7(case_row).lower()
    crew = _crew_text(case_row)
    subject = _first_clean_1_7(case_row.get('suspect_name'), case_row.get('vessel_name'))
    paragraphs: list[str] = []
    paragraphs.append(f'Den {when} var {unit} på fiskeripatrulje/oppsyn ved {place}. Jeg, {investigator}, deltok i kontrollen. Kontrolltema var {topic}.')
    if crew and crew != '-':
        paragraphs.append(f'Patruljen/inspeksjonslaget bestod for øvrig av: {crew}.')
    paragraphs.append(_own_report_basis_1_8_24(case_row, findings))
    if subject:
        paragraphs.append(f'Kontrollobjekt/ansvarlig registrert i saken er {subject}.')
    if _avvik_1_7(findings):
        paragraphs.append('Under kontrollen ble følgende forhold registrert som avvik:\n' + '\n'.join(_short_avvik_lines_1_8_24(findings, limit=260)))
    else:
        paragraphs.append('Det ble ikke registrert avvik i kontrollpunktene på tidspunktet rapporten ble laget.')
    if _seizure_rows_1_7(case_row, findings):
        paragraphs.append('Redskap/beslag er ført i egen beslagsrapport. Relevante fotografier og kartutsnitt fremgår av illustrasjonsmappe/fotomappe.')
    else:
        paragraphs.append('Relevante fotografier og kartutsnitt fremgår av illustrasjonsmappe/fotomappe der dette er registrert.')
    if _has_interview_report_content_1_8_21(case_row):
        paragraphs.append('Gjennomført avhør/forklaring er protokollert i egen avhørsrapport.')
    notes = _strip_inline_seizure_text_1_8_24(_strip_generated_report_noise_1_8_21(case_row.get('notes')))
    if notes:
        paragraphs.append('Kontrollørs merknad: ' + _shorten_sentence_1_8_21(notes, 420))
    return _clean_standard_text_1_7('\n\n'.join(part for part in paragraphs if part).strip(), case_row)

# ---- 1.8.27: forbedrede IKV-tekster, komplett anmeldt forhold og bedre feltflyt ----
_GENERIC_TOPIC_PARTS_1_8_25 = {
    '', '-', 'fiskerikontroll', 'kontroll', 'aktuelt fiskeri', 'fiskeri', 'redskap', 'annet', 'ukjent'
}


def _topic_part_1_8_25(value: Any) -> str:
    text = re.sub(r'\s+', ' ', str(value or '')).strip()
    if text.lower() in _GENERIC_TOPIC_PARTS_1_8_25:
        return ''
    return text


def _topic_narrative_1_8_25(case_row: Dict[str, Any]) -> str:
    control = _topic_part_1_8_25(case_row.get('control_type'))
    species = _topic_part_1_8_25(case_row.get('species') or case_row.get('fishery_type'))
    gear = _topic_part_1_8_25(case_row.get('gear_type'))
    parts: list[str] = []
    if control:
        parts.append(control.lower())
    if species:
        if control and 'fiske' in control.lower():
            parts.append('etter ' + species.lower())
        else:
            parts.append(species.lower())
    if gear:
        parts.append('med ' + gear.lower())
    text = ' '.join(parts).strip()
    return text or 'aktuelle redskaps- og fiskeribestemmelser'


def _subject_name_1_8_25(case_row: Dict[str, Any], *, fallback: str = 'ukjent gjerningsperson') -> str:
    return _first_clean_1_7(
        case_row.get('suspect_name'),
        case_row.get('responsible_name'),
        case_row.get('vessel_name'),
        fallback,
    )


def _title_shortener_1_8_25(title: Any) -> str:
    text = re.sub(r'\s+', ' ', str(title or '')).strip(' .')
    replacements = [
        (r'^Fangst og oppbevaring av hummer under minstemål$', 'Hummer under minstemål'),
        (r'^Fangst og oppbevaring av hummer på eller over maksimalmål$', 'Hummer på/over maksimalmål'),
        (r'^Fangst og oppbevaring av hummer utenfor tillatt lengdekrav$', 'Hummer utenfor lengdekrav'),
        (r'^Fangst og oppbevaring av rognhummer$', 'Rognhummer'),
        (r'^Fiske etter hummer uten gyldig deltakernummer$', 'Hummerfiske uten gyldig deltakernummer'),
        (r'^Fiske etter hummer utenfor tillatt periode$', 'Hummerfiske utenfor tillatt periode'),
        (r'^Fiske i stengt eller forbudsregulert område$', 'Fiske i forbudsområde'),
        (r'^Fiske i fredningsområde$', 'Fiske i fredningsområde'),
        (r'^Fiske i hummerfredningsområde$', 'Fiske i hummerfredningsområde'),
        (r'^Mangelfull merking av vak/blåse$', 'Mangelfull merking av vak/blåse'),
        (r'^Mangelfull merking av teine/ruse$', 'Mangelfull merking av redskap'),
        (r'^Hummerteine uten påbudt fluktåpning$', 'Ulovlig fluktåpning'),
        (r'^Hummerteine uten påbudt rømningshull/råtnetråd$', 'Manglende rømningshull/råtnetråd'),
        (r'^Fiske med flere hummerteiner enn tillatt$', 'Flere hummerteiner enn tillatt'),
    ]
    for pattern, repl in replacements:
        text = re.sub(pattern, repl, text, flags=re.IGNORECASE)
    return text[:120].strip(' .')


def _offence_titles_1_8_25(case_row: Dict[str, Any], findings: list[Dict[str, Any]]) -> list[str]:
    titles: list[str] = []
    seen: set[str] = set()
    for block in _offence_blocks(case_row, findings):
        title = _title_shortener_1_8_25(_offence_title_from_block_1_8_23(block))
        key = title.lower()
        if title and key not in seen:
            seen.add(key)
            titles.append(title)
    return titles


def _offence_title(case_row: Dict[str, Any], findings: list[Dict[str, Any]]) -> str:  # type: ignore[override]
    titles = _offence_titles_1_8_25(case_row, findings)
    if not titles:
        return 'Kontroll av ' + _topic_narrative_1_8_25(case_row)
    return '; '.join(titles)


def _law_excerpt_1_8_23(ref: Dict[str, Any], limit: int = 260) -> str:  # type: ignore[override]
    text = _clean_law_text_1_8_23(ref.get('law_text'))
    if not text:
        return ''
    # Fjern lister, koordinater og områdekataloger. I anmeldelsen skal hjemmelen vise normen,
    # ikke hele kart-/Lovdata-teksten.
    stop_patterns = [
        r'\bNavn på gytefelt\b', r'\bBeskrivelsePunktPosisjon\b', r'\bPunktPosisjon\b',
        r'\bIndre Oslofjord\b', r'\bMossesundet\b', r'\bSletterhausen\b', r'\bHvaler\b',
        r'\bN\s*\d{1,2}[°º]', r'\bØ\s*\d{1,3}[°º]',
    ]
    for pattern in stop_patterns:
        m = re.search(pattern, text, flags=re.IGNORECASE)
        if m and m.start() > 35:
            text = text[:m.start()].strip(' ,.;:')
            break
    sentences = [s.strip() for s in re.split(r'(?<=[.!?])\s+', text) if s.strip()]
    # Ta normalt med én normativ setning. Straffehjemmel kan stå som egen kort hjemmelrad.
    excerpt = sentences[0] if sentences else text
    if len(excerpt) > limit:
        excerpt = excerpt[:limit].rsplit(' ', 1)[0].rstrip(' ,.;:') + '...'
    return excerpt


def _display_ref_row_1_8_23(ref: Dict[str, Any]) -> Dict[str, str]:  # type: ignore[override]
    excerpt = _law_excerpt_1_8_23(ref, 260)
    return {
        'name': str(ref.get('name') or '').strip(),
        'ref': str(ref.get('ref') or '').strip(),
        'law_text': excerpt,
        'excerpt': excerpt,
    }


def _refs_to_text(refs: list[Dict[str, str]]) -> str:  # type: ignore[override]
    chunks: list[str] = []
    for ref in refs:
        head = _legal_ref_head_1_8_23(ref)
        excerpt = str(ref.get('excerpt') or ref.get('law_text') or '').strip()
        if not head and not excerpt:
            continue
        line = head
        if excerpt:
            line = (line + ' - ' if line else '') + excerpt
        chunks.append(line.strip())
    return '\n'.join(chunks).strip()


def build_control_reason(case_row: Dict[str, Any], findings: list[Dict[str, Any]]) -> str:  # type: ignore[override]
    override = str(case_row.get('basis_details') or '').strip()
    basis = _normal_case_basis_1_8_22(case_row.get('case_basis'))
    if override and not _looks_like_old_generated_basis_1_8_22(override):
        cleaned = _clean_standard_text_1_7(override, case_row)
        cleaned = cleaned.replace('kontrollere fiskerikontroll', 'kontrollere aktuelle fiskeri- og redskapsbestemmelser')
        return cleaned
    unit = _case_vessel_unit_1_8_23(case_row)
    when = _case_time_phrase_1_8_23(case_row)
    place = _case_place_1_8_23(case_row)
    topic = _topic_narrative_1_8_25(case_row)
    source = _first_clean_1_7(case_row.get('basis_source_name'))
    if basis == 'tips':
        source_text = f' fra {source}' if source else ''
        text = (f'{unit} gjennomførte den {when} fiskerioppsyn ved {place} på bakgrunn av tips/opplysninger{source_text}. '
                f'Tipsopplysningene dannet grunnlag for å kontrollere {topic}. Rapporten bygger på patruljens egne observasjoner og dokumentasjon sikret på stedet.')
    else:
        text = (f'{unit} gjennomførte den {when} fiskerioppsyn ved {place}. '
                f'Patruljeformålet var å kontrollere {topic} og avklare om redskap, merking, fangst/oppbevaring og relevante områdebestemmelser var i samsvar med gjeldende regelverk.')
    area = _first_clean_1_7(case_row.get('area_name'), case_row.get('area_status'))
    if area and area.lower() not in {'ingen treff', 'ikke oppgitt'}:
        text += f' Kontrollstedet ble vurdert opp mot registrert områdestatus: {area}.'
    return _clean_standard_text_1_7(text, case_row)


def _offence_fact_line_1_8_25(block: Dict[str, Any], idx: int) -> str:
    title = _title_shortener_1_8_25(_offence_title_from_block_1_8_23(block))
    details = _strip_inline_seizure_text_1_8_24(block.get('details') or block.get('allegation') or '')
    details = re.sub(r'^Mulig\s+brudd\s+på\s+[^:]+:\s*', '', details, flags=re.IGNORECASE).strip()
    details = re.sub(r'\bden\s+kontrolltidspunktet\b', 'på kontrolltidspunktet', details, flags=re.IGNORECASE)
    details = re.sub(r'\s{2,}', ' ', details).strip(' ;,.-')
    if details and title.lower() not in details.lower():
        text = f'{title}: {details}'
    else:
        text = title
    return f'{idx}. {_shorten_sentence_1_8_21(_sentence_1_7(text), 280)}'


def _short_avvik_lines_1_8_24(findings: list[Dict[str, Any]], *, limit: int = 240) -> list[str]:  # type: ignore[override]
    avvik = _avvik_1_7(findings)
    if not avvik:
        return ['Det er ikke registrert avvik i kontrollpunktene på tidspunktet rapporten ble laget.']
    rows: list[str] = []
    for idx, item in enumerate(avvik, start=1):
        block = _offence_from_finding({}, item, findings)
        title = _title_shortener_1_8_25(_offence_title_from_block_1_8_23(block))
        note = _strip_inline_seizure_text_1_8_24(_first_clean_1_7(item.get('notes'), item.get('auto_note'), item.get('summary_text')))
        line = title
        if note:
            line += ': ' + _shorten_sentence_1_8_21(note, limit)
        rows.append(f'{idx}. {_sentence_1_7(line)}')
    return rows


def _build_short_complaint(case_row: Dict[str, Any], findings: list[Dict[str, Any]], sources: list[Dict[str, Any]]) -> str:  # type: ignore[override]
    override = str(case_row.get('complaint_override') or '').strip()
    if override:
        return _clean_standard_text_1_7(_strip_doc_heading_1_8_23(override), case_row)
    subject = _subject_name_1_8_25(case_row)
    when = _case_time_phrase_1_8_23(case_row)
    place = _case_place_1_8_23(case_row)
    unit = _case_vessel_unit_1_8_23(case_row)
    topic = _topic_narrative_1_8_25(case_row)
    offences = _offence_blocks(case_row, findings)
    titles = _offence_titles_1_8_25(case_row, findings)
    lines: list[str] = []
    if offences:
        if len(titles) == 1:
            lines.append(f'Med dette anmeldes {subject} for {titles[0].lower()} avdekket {when} ved {place}.')
        else:
            lines.append(f'Med dette anmeldes {subject} for følgende forhold avdekket {when} ved {place}:')
            for idx, title in enumerate(titles, start=1):
                lines.append(f'{idx}. {title}.')
        lines.append('')
        lines.append(f'Forholdet ble avdekket da {unit} gjennomførte fiskerioppsyn/kontroll. Kontrollen gjaldt {topic}.')
        lines.append('')
        lines.append('Kort beskrivelse av forholdet:')
        for idx, block in enumerate(offences, start=1):
            lines.append(_offence_fact_line_1_8_25(block, idx))
        refs = _registered_avvik_ref_rows_1_8_21(case_row, findings)
        if refs:
            lines.append('')
            lines.append('Aktuelle lovhjemler er begrenset til lov-/forskriftshenvisninger som er knyttet til registrerte avvik i kontrollpunktene.')
        evidence_docs = ['egenrapport', 'beslagsrapport', 'illustrasjonsmappe/fotomappe']
        if _has_interview_report_content_1_8_21(case_row):
            evidence_docs.append('avhørsrapport')
        lines.append('')
        lines.append('For nærmere detaljer om faktum og bevissituasjonen vises det til sakens ' + ', '.join(evidence_docs) + '.')
    else:
        lines.append(f'Det ble gjennomført fiskerikontroll {when} ved {place}. Det er ikke registrert avvik som danner grunnlag for anmeldelse i kontrollpunktene på tidspunktet for utkastet.')
    return _clean_standard_text_1_7('\n'.join(lines).strip(), case_row)




def _own_report_basis_1_8_25(case_row: Dict[str, Any], findings: list[Dict[str, Any]]) -> str:
    override = str(case_row.get('basis_details') or '').strip()
    basis = _normal_case_basis_1_8_22(case_row.get('case_basis'))
    if override and not _looks_like_old_generated_basis_1_8_22(override):
        cleaned = _clean_standard_text_1_7(override, case_row)
        # Dersom feltet allerede inneholder tid/sted fra standardtekst, kort det ned i egenrapporten.
        cleaned = re.sub(r'^[^.]*?gjennomførte[^.]*?fiskerioppsyn[^.]*\.\s*', '', cleaned, flags=re.IGNORECASE).strip()
        return cleaned or build_control_reason(case_row, findings)
    topic = _topic_narrative_1_8_25(case_row)
    source = _first_clean_1_7(case_row.get('basis_source_name'))
    if basis == 'tips':
        source_text = f' fra {source}' if source else ''
        return f'Kontrollen ble gjennomført på bakgrunn av tips/opplysninger{source_text}. Tipsopplysningene dannet grunnlag for å kontrollere {topic}. Rapporten bygger på patruljens egne observasjoner og dokumentasjon sikret på stedet.'
    return f'Patruljeformålet var å kontrollere {topic} og avklare om redskap, merking, fangst/oppbevaring og relevante områdebestemmelser var i samsvar med gjeldende regelverk.'

def _build_own_report(case_row: Dict[str, Any], findings: list[Dict[str, Any]]) -> str:  # type: ignore[override]
    override = str(case_row.get('own_report_override') or '').strip()
    if override:
        return _clean_standard_text_1_7(_strip_doc_heading_1_8_23(override), case_row)
    investigator = _first_clean_1_7(case_row.get('investigator_name'), 'rapportskriver')
    unit = _case_vessel_unit_1_8_23(case_row)
    when = _case_time_phrase_1_8_23(case_row)
    place = _case_place_1_8_23(case_row)
    topic = _topic_narrative_1_8_25(case_row)
    crew = _crew_text(case_row)
    subject = _subject_name_1_8_25(case_row, fallback='')
    paragraphs: list[str] = []
    paragraphs.append(f'Den {when} gjennomførte {unit} fiskerioppsyn ved {place}. Jeg, {investigator}, deltok i kontrollen. Kontrolltema var {topic}.')
    if crew and crew != '-':
        paragraphs.append(f'Patruljen/inspeksjonslaget bestod for øvrig av: {crew}.')
    paragraphs.append(_own_report_basis_1_8_25(case_row, findings))
    if subject:
        paragraphs.append(f'Kontrollobjekt/ansvarlig registrert i saken er {subject}.')
    avvik = _avvik_1_7(findings)
    if avvik:
        paragraphs.append('Under kontrollen ble følgende forhold registrert som avvik:\n' + '\n'.join(_short_avvik_lines_1_8_24(findings, limit=260)))
    else:
        paragraphs.append('Det ble ikke registrert avvik i kontrollpunktene på tidspunktet rapporten ble laget.')
    if _seizure_rows_1_7(case_row, findings):
        paragraphs.append('På bakgrunn av observasjonene ble redskap/beslag dokumentert i egen beslagsrapport. Relevante fotografier og kartutsnitt fremgår av illustrasjonsmappe/fotomappe.')
    else:
        paragraphs.append('Relevante fotografier og kartutsnitt fremgår av illustrasjonsmappe/fotomappe der dette er registrert.')
    if _has_interview_report_content_1_8_21(case_row):
        paragraphs.append('Gjennomført avhør/forklaring er protokollert i egen avhørsrapport.')
    notes = _strip_inline_seizure_text_1_8_24(_strip_generated_report_noise_1_8_21(case_row.get('notes')))
    if notes:
        paragraphs.append('Kontrollørs merknad: ' + _shorten_sentence_1_8_21(notes, 420))
    return _clean_standard_text_1_7('\n\n'.join(part for part in paragraphs if part).strip(), case_row)


def _build_interview_report(case_row: Dict[str, Any]) -> str:  # type: ignore[override]
    if not _has_interview_report_content_1_8_21(case_row):
        return ''
    override = str(case_row.get('interview_report_override') or '').strip()
    if override:
        return _clean_standard_text_1_7(_strip_doc_heading_1_8_23(override), case_row)
    entries = _conducted_interview_entries_1_8_21(case_row)
    lines: list[str] = []
    used = 0
    for entry in entries:
        body = _interview_entry_body_1_8_21(entry)
        if not body:
            continue
        used += 1
        name = _first_clean_1_7(entry.get('name'), case_row.get('suspect_name'), f'avhørt person {used}')
        role = _first_clean_1_7(entry.get('role'), 'mistenkt/siktet')
        method = _first_clean_1_7(entry.get('method'), 'ikke oppgitt')
        place = _first_clean_1_7(entry.get('place'), _place_phrase_1_7(case_row))
        start = _fmt_datetime(entry.get('start') or case_row.get('start_time'))
        end = _fmt_datetime(entry.get('end') or case_row.get('end_time'))
        if used > 1:
            lines.append('')
        lines.append(f'Avhør av {name}')
        lines.append(f'{name} ble avhørt som {role}. Avhøret ble gjennomført {start} - {end} ved {place}. Metode: {method}.')
        lines.append('Avhørte ble gjort kjent med saken og sine rettigheter før forklaring ble gitt.')
        lines.append('Forklaring/sammendrag:')
        lines.append(body.strip())
    return _clean_standard_text_1_7('\n'.join(lines).strip(), case_row) if used else ''


def _image_caption_base_1_8_24(item: Dict[str, Any], idx: int) -> str:  # type: ignore[override]
    raw = _first_clean_1_7(item.get('caption'), item.get('original_filename'), item.get('filename'), f'foto {idx}')
    raw = _strip_inline_seizure_text_1_8_24(raw)
    raw = re.sub(r'\s+', ' ', raw).strip(' .')
    if not raw:
        raw = f'foto {idx}'
    low = raw.lower()
    if low.startswith('bilde viser') or low.startswith('foto viser'):
        text = raw[0].upper() + raw[1:]
    else:
        text = 'Bilde viser ' + raw[0].lower() + raw[1:]
    return _sentence_1_7(text)


def _build_illustration_texts(evidence_rows: list[Dict[str, Any]]) -> list[str]:  # type: ignore[override]
    if not evidence_rows:
        return ['Ingen illustrasjoner registrert i saken.']
    texts: list[str] = []
    for idx, item in enumerate(evidence_rows, start=1):
        finding_key = str(item.get('finding_key') or '').strip().lower()
        caption = str(item.get('caption') or '').strip()
        filename = str(item.get('filename') or item.get('generated_path') or '').strip().lower()
        if finding_key == 'oversiktskart':
            if '2km' in filename or '5km' in filename or caption.lower().startswith('detaljert'):
                texts.append('Bilde viser detaljert kartutsnitt med kontrollposisjon og registrerte avviks-/beslagsposisjoner.')
            else:
                texts.append('Bilde viser oversiktskart av kontrollposisjon.')
            continue
        base = _image_caption_base_1_8_24(item, idx).rstrip('.')
        extras: list[str] = []
        seizure = _first_clean_1_7(item.get('seizure_ref'))
        reason = _strip_inline_seizure_text_1_8_24(_first_clean_1_7(item.get('violation_reason')))
        if seizure:
            extras.append(f'beslag {seizure}')
        if reason:
            extras.append('avvik: ' + _shorten_sentence_1_8_21(reason, 90).rstrip('.'))
        if extras:
            base += ' - ' + ' - '.join(extras)
        texts.append(_shorten_sentence_1_8_21(_sentence_1_7(base), 220))
    return texts


def build_summary(case_row: Dict[str, Any], findings: list[Dict[str, Any]]) -> str:  # type: ignore[override]
    if (case_row.get('summary') or '').strip():
        return _clean_standard_text_1_7(case_row.get('summary'), case_row)
    when = _case_time_phrase_1_8_23(case_row)
    place = _case_place_1_8_23(case_row)
    lines: list[str] = [
        f'Kontrollen ble gjennomført {when} ved {place}. Kontrolltema var {_topic_narrative_1_8_25(case_row)}.',
        build_control_reason(case_row, findings),
    ]
    avvik = _avvik_1_7(findings)
    if avvik:
        lines.append('Registrerte avvik:')
        lines.extend(_short_avvik_lines_1_8_24(findings, limit=180))
        lines.append('Dokumentasjon fremgår av egenrapport, beslagsrapport og illustrasjonsmappe/fotomappe. Avhørsrapport tas bare med når avhør er merket gjennomført.')
    else:
        lines.append('Det er ikke registrert avvik i kontrollpunktene.')
    return _clean_standard_text_1_7('\n'.join(lines), case_row)


def build_text_drafts(case_row: Dict[str, Any], findings: list[Dict[str, Any]]) -> Dict[str, str]:  # type: ignore[override]
    return {
        'summary': build_summary(case_row, findings),
        'basis_details': build_control_reason(case_row, findings),
        'notes': '',
        'complaint_preview': _build_short_complaint(case_row, findings, _safe_sources(case_row)),
        'source_label': 'straffesaksmal 1.8.27',
    }


def _draw_sak_section(c: rl_canvas.Canvas, case_row: Dict[str, Any], top: float, location_label: str = 'Åsted', include_identity: bool = False) -> float:  # type: ignore[override]
    l, mid, r = 118, 808, 1128
    y = top
    _draw_section_caption(c, l, y, r, y + 28, 'Sak')
    y += 28
    title = _offence_title(case_row, _safe_findings(case_row))
    title_len = len(title)
    title_row_h = 58
    if title_len > 85:
        title_row_h = 76
    if title_len > 145:
        title_row_h = 96
    row1 = y + title_row_h
    row2 = row1 + 44
    row3 = row2 + 34
    row4 = row3 + 38
    value_size = 8.6 if title_len <= 120 else 7.8
    _draw_label_value(c, l, y, mid, row1, 'Anmeldt forhold', title, value_size=value_size)
    _draw_label_value(c, l, row1, 351, row2, 'Fra dato kl.', _fmt_datetime_packet(case_row.get('start_time')))
    _draw_label_value(c, 351, row1, 579, row2, 'Til dato kl.', _fmt_datetime_packet(case_row.get('end_time')))
    _draw_label_value(c, 579, row1, mid, row2, 'Reg. dato', _fmt_datetime_packet(case_row.get('updated_at') or case_row.get('created_at')))
    _draw_label_value(c, l, row2, mid, row3, 'Sone', 'Skagerrak')
    _draw_label_value(c, l, row3, mid, row4, location_label, _fmt_value(case_row.get('location_name') or _area_name_value(case_row)))
    _draw_label_value(c, mid, y, r, row1, 'Etterforskningsinstans', '')
    _draw_label_value(c, mid, row1, r, row2, 'Stat. bokstav | Stat. gruppe | Modus | Sone', '')
    _draw_label_value(c, mid, row2, r, row3, 'Påtaleansvarlig', '')
    _draw_label_value(c, mid, row3, r, row4, 'Etterforsker', _fmt_value(case_row.get('investigator_name')))
    y = row4
    if include_identity:
        row5 = y + 38
        _draw_label_value(c, l, y, 579, row5, 'Navn', _fmt_value(case_row.get('suspect_name')))
        _draw_label_value(c, 579, y, 808, row5, 'Fødselsnr', _fmt_value(case_row.get('suspect_birthdate')))
        _draw_label_value(c, 808, y, r, row5, 'Rolle', 'Siktet / Mistenkt')
        y = row5
    return y

# 1.8.27a: behold faglige skråstreker som vak/blåse og sanke-/samleteine i rapporttekst.
def _clean_generated_phrase(value: Any) -> str:  # type: ignore[override]
    text = re.sub(r'\s+', ' ', str(value or '')).strip()
    if not text:
        return ''
    text = re.sub(r'\s*/\s*', '/', text)
    text = re.sub(r'\s+,', ',', text)
    text = re.sub(r'\(\s+', '(', text)
    text = re.sub(r'\s+\)', ')', text)
    return text.strip()

# 1.8.27b: vis alle anmeldte forhold som egne linjer i sakshoder når det er flere forhold.
def _offence_title(case_row: Dict[str, Any], findings: list[Dict[str, Any]]) -> str:  # type: ignore[override]
    titles = _offence_titles_1_8_25(case_row, findings)
    if not titles:
        return 'Kontroll av ' + _topic_narrative_1_8_25(case_row)
    if len(titles) == 1:
        return titles[0]
    return '\n'.join('- ' + title for title in titles)

# 1.8.27c: gi sakshodet nok høyde til flere linjer med anmeldt forhold.
def _draw_sak_section(c: rl_canvas.Canvas, case_row: Dict[str, Any], top: float, location_label: str = 'Åsted', include_identity: bool = False) -> float:  # type: ignore[override]
    l, mid, r = 118, 808, 1128
    y = top
    _draw_section_caption(c, l, y, r, y + 28, 'Sak')
    y += 28
    title = _offence_title(case_row, _safe_findings(case_row))
    title_len = len(title)
    title_lines = max(1, len(str(title).split('\n')))
    title_row_h = 58
    if title_len > 85 or title_lines >= 2:
        title_row_h = 88
    if title_len > 145 or title_lines >= 3:
        title_row_h = 122
    if title_lines >= 4:
        title_row_h = 148
    row1 = y + title_row_h
    row2 = row1 + 44
    row3 = row2 + 34
    row4 = row3 + 38
    value_size = 8.3 if title_len <= 120 else 7.6
    _draw_label_value(c, l, y, mid, row1, 'Anmeldt forhold', title, value_size=value_size)
    _draw_label_value(c, l, row1, 351, row2, 'Fra dato kl.', _fmt_datetime_packet(case_row.get('start_time')))
    _draw_label_value(c, 351, row1, 579, row2, 'Til dato kl.', _fmt_datetime_packet(case_row.get('end_time')))
    _draw_label_value(c, 579, row1, mid, row2, 'Reg. dato', _fmt_datetime_packet(case_row.get('updated_at') or case_row.get('created_at')))
    _draw_label_value(c, l, row2, mid, row3, 'Sone', 'Skagerrak')
    _draw_label_value(c, l, row3, mid, row4, location_label, _fmt_value(case_row.get('location_name') or _area_name_value(case_row)))
    _draw_label_value(c, mid, y, r, row1, 'Etterforskningsinstans', '')
    _draw_label_value(c, mid, row1, r, row2, 'Stat. bokstav | Stat. gruppe | Modus | Sone', '')
    _draw_label_value(c, mid, row2, r, row3, 'Påtaleansvarlig', '')
    _draw_label_value(c, mid, row3, r, row4, 'Etterforsker', _fmt_value(case_row.get('investigator_name')))
    y = row4
    if include_identity:
        row5 = y + 38
        _draw_label_value(c, l, y, 579, row5, 'Navn', _fmt_value(case_row.get('suspect_name')))
        _draw_label_value(c, 579, y, 808, row5, 'Fødselsnr', _fmt_value(case_row.get('suspect_birthdate')))
        _draw_label_value(c, 808, y, r, row5, 'Rolle', 'Siktet / Mistenkt')
        y = row5
    return y

# ---- 1.8.27: mer IKV-narativ rapporttekst, bedre patruljeformål og feltflyt ----
# Malene under bygger på føringene i Straffesakshåndboken: anmeldelsen skal gi juristen
# hvem/hva/hvor/når/hvordan og bevissituasjon, uten lange lovsitat. Egenrapporten skal
# være rapportskrivers nøkterne observasjoner, ikke en gjentagelse av hele anmeldelsen.

_GENERIC_TOPIC_PARTS_1_8_26 = {
    '', '-', 'fiskerikontroll', 'kontroll', 'kontrolltype', 'aktuelt fiskeri',
    'fiskeri', 'art', 'redskap', 'annet', 'ukjent', 'ikke valgt'
}


def _topic_part_1_8_26(value: Any) -> str:
    text = re.sub(r'\s+', ' ', str(value or '')).strip()
    if text.lower() in _GENERIC_TOPIC_PARTS_1_8_26:
        return ''
    return text


def _topic_narrative_1_8_25(case_row: Dict[str, Any]) -> str:  # type: ignore[override]
    control = _topic_part_1_8_26(case_row.get('control_type'))
    species = _topic_part_1_8_26(case_row.get('species') or case_row.get('fishery_type'))
    gear = _topic_part_1_8_26(case_row.get('gear_type'))
    parts: list[str] = []
    if control:
        parts.append(control.lower())
    if species:
        if control and 'fiske' in control.lower():
            parts.append('etter ' + species.lower())
        else:
            parts.append(species.lower())
    if gear:
        parts.append('med ' + gear.lower())
    text = ' '.join(parts).strip()
    return text or 'aktuelle fiskeri- og redskapsbestemmelser'


def _formal_topic_sentence_1_8_26(case_row: Dict[str, Any]) -> str:
    topic = _topic_narrative_1_8_25(case_row)
    return topic if topic != 'aktuelle fiskeri- og redskapsbestemmelser' else 'aktuelle fiskeri- og redskapsbestemmelser'


def _basis_area_sentence_1_8_26(case_row: Dict[str, Any]) -> str:
    area = _first_clean_1_7(case_row.get('area_name'), case_row.get('area_status'))
    if area and area.lower() not in {'ingen treff', 'ikke oppgitt', '-', 'ukjent'}:
        return f' Kontrollstedet ble samtidig vurdert opp mot registrert områdestatus: {area}.'
    return ''


def _default_control_purpose_1_8_26(case_row: Dict[str, Any], *, short: bool = False) -> str:
    basis = _normal_case_basis_1_8_22(case_row.get('case_basis'))
    topic = _formal_topic_sentence_1_8_26(case_row)
    source = _first_clean_1_7(case_row.get('basis_source_name'))
    species = str(case_row.get('species') or case_row.get('fishery_type') or '').strip().lower()
    gear = str(case_row.get('gear_type') or '').strip().lower()
    if basis == 'tips':
        source_text = f' fra {source}' if source else ''
        if short:
            return (f'Kontrollen ble gjennomført på bakgrunn av tips/opplysninger{source_text}. '
                    f'Tipset ble brukt som utgangspunkt for kontrollen. Vurderingene i rapporten bygger på patruljens egne observasjoner og dokumentasjon sikret på stedet.')
        return (f'Kontrollen ble gjennomført på bakgrunn av tips/opplysninger{source_text}. '
                f'Tipsopplysningene ga grunnlag for å kontrollere {topic}. De forhold som omtales i rapporten bygger på patruljens egne observasjoner, kontroll av redskapet og dokumentasjon sikret på stedet.')
    if 'hummer' in species:
        body = ('Formålet var å føre kontroll med hummerfiske og avklare om deltakelse/deltakernummer, '
                'merking av vak og redskap, antall teiner, fluktåpninger/rømningshull, lengdemål, fangst/oppbevaring og relevante område- eller tidsbestemmelser var i samsvar med gjeldende regelverk.')
    elif any(word in gear for word in ['teine', 'ruse', 'garn', 'lenke']):
        body = ('Formålet var å føre kontroll med faststående redskap og avklare om vak/blåse, redskapets merking, '
                'utforming, plassering, røktingsforhold, fangst/oppbevaring og ansvarlig bruker/eier var i samsvar med gjeldende regelverk.')
    else:
        body = f'Formålet var å føre kontroll med {topic} og avklare om observasjoner, redskap, merking, fangst/oppbevaring, posisjon og relevante områdebestemmelser var i samsvar med gjeldende regelverk.'
    return body


def build_control_reason(case_row: Dict[str, Any], findings: list[Dict[str, Any]]) -> str:  # type: ignore[override]
    override = str(case_row.get('basis_details') or '').strip()
    if override and not _looks_like_old_generated_basis_1_8_22(override):
        cleaned = _clean_standard_text_1_7(override, case_row)
        cleaned = re.sub(r'kontrollere\s+fiskerikontroll\s*', 'føre kontroll med ', cleaned, flags=re.IGNORECASE)
        cleaned = cleaned.replace('aktuelt fiskeri / redskap', 'aktuelt fiskeri og redskap')
        return cleaned
    unit = _case_vessel_unit_1_8_23(case_row)
    when = _case_time_phrase_1_8_23(case_row)
    place = _case_place_1_8_23(case_row)
    text = f'{unit} gjennomførte den {when} fiskerioppsyn ved {place}. {_default_control_purpose_1_8_26(case_row)}'
    text += _basis_area_sentence_1_8_26(case_row)
    return _clean_standard_text_1_7(text, case_row)


_TITLE_REPLACEMENTS_1_8_26 = [
    (r'^Fangst og oppbevaring av hummer under minstemål$', 'Fangst og oppbevaring av hummer under minstemål'),
    (r'^Fangst og oppbevaring av hummer på eller over maksimalmål$', 'Fangst og oppbevaring av hummer på/over maksimalmål'),
    (r'^Fangst og oppbevaring av hummer utenfor tillatt lengdekrav$', 'Fangst og oppbevaring av hummer utenfor lengdekrav'),
    (r'^Fangst og oppbevaring av rognhummer$', 'Fangst og oppbevaring av rognhummer'),
    (r'^Fiske etter hummer uten gyldig deltakernummer$', 'Fiske etter hummer uten gyldig deltakernummer'),
    (r'^Fiske etter hummer utenfor tillatt periode$', 'Fiske etter hummer utenfor tillatt periode'),
    (r'^Fiske i stengt eller forbudsregulert område$', 'Fiske i forbudsområde'),
    (r'^Fiske i fredningsområde$', 'Fiske i fredningsområde'),
    (r'^Fiske i hummerfredningsområde$', 'Fiske i hummerfredningsområde'),
    (r'^Mangelfull merking av vak/blåse$', 'Mangelfull merking av vak/blåse'),
    (r'^Mangelfull merking av teine/ruse$', 'Manglende merking av redskap'),
    (r'^Hummerteine uten påbudt fluktåpning$', 'Ulovlig fluktåpning'),
    (r'^Hummerteine uten påbudt rømningshull/råtnetråd$', 'Manglende rømningshull/råtnetråd'),
    (r'^Fiske med flere hummerteiner enn tillatt$', 'Fiske med flere hummerteiner enn tillatt'),
]


def _title_shortener_1_8_25(title: Any) -> str:  # type: ignore[override]
    text = re.sub(r'\s+', ' ', str(title or '')).strip(' .')
    for pattern, repl in _TITLE_REPLACEMENTS_1_8_26:
        text = re.sub(pattern, repl, text, flags=re.IGNORECASE)
    # Hold feltet kort, men ikke kutt midt i ord slik at f.eks. «Fiske i ...» blir ufullstendig.
    if len(text) > 150:
        text = text[:150].rsplit(' ', 1)[0].rstrip(' ,.;:') + '...'
    return text.strip(' .')


def _offence_title(case_row: Dict[str, Any], findings: list[Dict[str, Any]]) -> str:  # type: ignore[override]
    titles = _offence_titles_1_8_25(case_row, findings)
    if not titles:
        return 'Kontroll av ' + _topic_narrative_1_8_25(case_row)
    if len(titles) == 1:
        return titles[0]
    return '\n'.join('- ' + title for title in titles)


def _law_excerpt_1_8_23(ref: Dict[str, Any], limit: int = 240) -> str:  # type: ignore[override]
    text = _clean_law_text_1_8_23(ref.get('law_text'))
    if not text:
        return ''
    # Fjern lange tabeller/områdekataloger/koordinater. Anmeldelsen skal vise rettslig norm,
    # ikke være et Lovdata-utdrag.
    cut_patterns = [
        r'\bBestemmelsen lyder\b', r'\bNavn på gytefelt\b', r'\bBeskrivelsePunktPosisjon\b',
        r'\bPunktPosisjon\b', r'\bVidere\s+(?:nord|sør|øst|vest)', r'\bDerfra\s+videre\b',
        r'\bN\s*\d{1,2}[°º]', r'\bØ\s*\d{1,3}[°º]', r'\bE\s*\d{1,3}[°º]',
        r'\bpunkt\s+\d+\b', r'\bkoordinat',
    ]
    for pattern in cut_patterns:
        m = re.search(pattern, text, flags=re.IGNORECASE)
        if m and m.start() > 35:
            text = text[:m.start()].strip(' ,.;:')
            break
    sentences = [s.strip() for s in re.split(r'(?<=[.!?])\s+', text) if s.strip()]
    normative = ''
    for sent in sentences[:4]:
        if re.search(r'\b(skal|forbudt|ikke tillatt|plikter|må|krav|straffes|straffbart)\b', sent, flags=re.IGNORECASE):
            normative = sent
            break
    excerpt = normative or (sentences[0] if sentences else text)
    if len(excerpt) > limit:
        excerpt = excerpt[:limit].rsplit(' ', 1)[0].rstrip(' ,.;:') + '...'
    return excerpt.strip()


def _display_ref_row_1_8_23(ref: Dict[str, Any]) -> Dict[str, str]:  # type: ignore[override]
    excerpt = _law_excerpt_1_8_23(ref, 240)
    return {
        'name': str(ref.get('name') or ref.get('law_name') or '').strip(),
        'ref': str(ref.get('ref') or ref.get('section') or '').strip(),
        'law_text': excerpt,
        'excerpt': excerpt,
    }


def _refs_to_text(refs: list[Dict[str, str]]) -> str:  # type: ignore[override]
    chunks: list[str] = []
    for ref in refs or []:
        head = _legal_ref_head_1_8_23(ref)
        excerpt = str(ref.get('excerpt') or ref.get('law_text') or '').strip()
        if not head and not excerpt:
            continue
        if head and excerpt:
            chunks.append(f'{head}: {excerpt}')
        elif head:
            chunks.append(head)
        else:
            chunks.append(excerpt)
    return '\n'.join(chunks).strip()


def _offence_fact_line_1_8_25(block: Dict[str, Any], idx: int) -> str:  # type: ignore[override]
    title = _title_shortener_1_8_25(_offence_title_from_block_1_8_23(block))
    details = _strip_inline_seizure_text_1_8_24(block.get('details') or block.get('allegation') or '')
    details = _strip_position_phrases_1_8_24(details)
    details = re.sub(r'^Mulig\s+brudd\s+på\s+[^:]+:\s*', '', details, flags=re.IGNORECASE).strip()
    details = re.sub(r'\bden\s+kontrolltidspunktet\b', 'på kontrolltidspunktet', details, flags=re.IGNORECASE)
    details = re.sub(r'\s{2,}', ' ', details).strip(' ;,.-')
    if details and title.lower() not in details.lower():
        text = f'{title}: {details}'
    else:
        text = title
    return f'{idx}. {_shorten_sentence_1_8_21(_sentence_1_7(text), 260)}'


def _short_avvik_lines_1_8_24(findings: list[Dict[str, Any]], *, limit: int = 220) -> list[str]:  # type: ignore[override]
    avvik = _avvik_1_7(findings)
    if not avvik:
        return ['Det er ikke registrert avvik i kontrollpunktene på tidspunktet rapporten ble laget.']
    rows: list[str] = []
    for idx, item in enumerate(avvik, start=1):
        block = _offence_from_finding({}, item, findings)
        title = _title_shortener_1_8_25(_offence_title_from_block_1_8_23(block))
        note = _strip_position_phrases_1_8_24(_strip_inline_seizure_text_1_8_24(_first_clean_1_7(item.get('notes'), item.get('auto_note'), item.get('summary_text'))))
        line = title
        if note:
            line += ': ' + _shorten_sentence_1_8_21(note, limit)
        rows.append(f'{idx}. {_sentence_1_7(line)}')
    return rows


def _evidence_doc_phrase_1_8_26(case_row: Dict[str, Any]) -> str:
    docs = ['egenrapport', 'beslagsrapport', 'illustrasjonsmappe/fotomappe']
    if _has_interview_report_content_1_8_21(case_row):
        docs.append('avhørsrapport')
    return ', '.join(docs)


def _build_short_complaint(case_row: Dict[str, Any], findings: list[Dict[str, Any]], sources: list[Dict[str, Any]]) -> str:  # type: ignore[override]
    override = str(case_row.get('complaint_override') or '').strip()
    if override:
        return _clean_standard_text_1_7(_strip_doc_heading_1_8_23(override), case_row)
    subject = _subject_name_1_8_25(case_row)
    when = _case_time_phrase_1_8_23(case_row)
    place = _case_place_1_8_23(case_row)
    unit = _case_vessel_unit_1_8_23(case_row)
    topic = _topic_narrative_1_8_25(case_row)
    offences = _offence_blocks(case_row, findings)
    titles = _offence_titles_1_8_25(case_row, findings)
    lines: list[str] = []
    if not offences:
        lines.append(f'Det ble gjennomført fiskerikontroll {when} ved {place}. Det er ikke registrert avvik som danner grunnlag for anmeldelse i kontrollpunktene på tidspunktet for utkastet.')
        return _clean_standard_text_1_7('\n'.join(lines), case_row)
    if len(titles) == 1:
        lines.append(f'Med dette anmeldes {subject} for {titles[0].lower()} avdekket {when} ved {place}.')
    else:
        lines.append(f'Med dette anmeldes {subject} for følgende forhold avdekket {when} ved {place}:')
        for idx, title in enumerate(titles, start=1):
            lines.append(f'{idx}. {title}.')
    lines.append('')
    lines.append(f'{"Forholdene" if len(titles) > 1 else "Forholdet"} ble avdekket da {unit} gjennomførte fiskerioppsyn/kontroll med {topic}.')
    lines.append('')
    lines.append('Kort faktumbeskrivelse:')
    for idx, block in enumerate(offences, start=1):
        lines.append(_offence_fact_line_1_8_25(block, idx))
    refs = _registered_avvik_ref_rows_1_8_21(case_row, findings)
    if refs:
        lines.append('')
        lines.append('Aktuelle lovhjemler er begrenset til bestemmelsene som er knyttet til registrerte avvik i kontrollpunktene:')
        for ref in refs[:8]:
            ref_line = _refs_to_text([ref]).strip()
            if ref_line:
                lines.append('- ' + _shorten_sentence_1_8_21(ref_line.replace('\n', ' '), 240).rstrip('.'))
    lines.append('')
    lines.append('Faktiske observasjoner, redskap/beslag, bilder og kart er dokumentert i sakens ' + _evidence_doc_phrase_1_8_26(case_row) + '. Endelig vurdering av skyld og reaksjon ligger til påtalemyndigheten.')
    return _clean_standard_text_1_7('\n'.join(lines).strip(), case_row)


def _own_report_basis_1_8_25(case_row: Dict[str, Any], findings: list[Dict[str, Any]]) -> str:  # type: ignore[override]
    override = str(case_row.get('basis_details') or '').strip()
    if override and not _looks_like_old_generated_basis_1_8_22(override):
        cleaned = _clean_standard_text_1_7(override, case_row)
        cleaned = re.sub(r'^[^.]*?gjennomførte[^.]*?fiskerioppsyn[^.]*\.\s*', '', cleaned, flags=re.IGNORECASE).strip()
        cleaned = re.sub(r'kontrollere\s+fiskerikontroll\s*', 'føre kontroll med ', cleaned, flags=re.IGNORECASE)
        return cleaned or _default_control_purpose_1_8_26(case_row, short=True)
    return _default_control_purpose_1_8_26(case_row, short=True)


def _build_own_report(case_row: Dict[str, Any], findings: list[Dict[str, Any]]) -> str:  # type: ignore[override]
    override = str(case_row.get('own_report_override') or '').strip()
    if override:
        return _clean_standard_text_1_7(_strip_doc_heading_1_8_23(override), case_row)
    investigator = _first_clean_1_7(case_row.get('investigator_name'), 'rapportskriver')
    unit = _case_vessel_unit_1_8_23(case_row)
    when = _case_time_phrase_1_8_23(case_row)
    place = _case_place_1_8_23(case_row)
    topic = _topic_narrative_1_8_25(case_row)
    crew = _crew_text(case_row)
    subject = _subject_name_1_8_25(case_row, fallback='')
    paragraphs: list[str] = []
    paragraphs.append(f'Den {when} gjennomførte {unit} fiskerioppsyn ved {place}. Jeg, {investigator}, deltok i kontrollen. Kontrolltema var {topic}.')
    if crew and crew != '-':
        paragraphs.append(f'Øvrig personell/observatører som deltok: {crew}.')
    paragraphs.append(_own_report_basis_1_8_25(case_row, findings))
    if subject:
        paragraphs.append(f'Kontrollobjekt/ansvarlig som er registrert i saken: {subject}.')
    avvik = _avvik_1_7(findings)
    if avvik:
        paragraphs.append('Under kontrollen ble følgende forhold registrert som avvik:\n' + '\n'.join(_short_avvik_lines_1_8_24(findings, limit=250)))
    else:
        paragraphs.append('Det ble ikke registrert avvik i kontrollpunktene på tidspunktet rapporten ble laget.')
    if _seizure_rows_1_7(case_row, findings):
        paragraphs.append('På bakgrunn av observasjonene ble redskap/beslag dokumentert i egen beslagsrapport. Redskapets posisjon fremgår av beslagsrapporten. Relevante fotografier og kartutsnitt fremgår av illustrasjonsmappe/fotomappe.')
    else:
        paragraphs.append('Relevante fotografier og kartutsnitt fremgår av illustrasjonsmappe/fotomappe der dette er registrert.')
    if _has_interview_report_content_1_8_21(case_row):
        paragraphs.append('Gjennomført avhør/forklaring er protokollert i egen avhørsrapport.')
    notes = _strip_position_phrases_1_8_24(_strip_inline_seizure_text_1_8_24(_strip_generated_report_noise_1_8_21(case_row.get('notes'))))
    if notes:
        paragraphs.append('Kontrollørs merknad: ' + _shorten_sentence_1_8_21(notes, 360))
    return _clean_standard_text_1_7('\n\n'.join(part for part in paragraphs if part).strip(), case_row)


def _build_interview_report(case_row: Dict[str, Any]) -> str:  # type: ignore[override]
    if not _has_interview_report_content_1_8_21(case_row):
        return ''
    override = str(case_row.get('interview_report_override') or '').strip()
    if override:
        return _clean_standard_text_1_7(_strip_doc_heading_1_8_23(override), case_row)
    entries = _conducted_interview_entries_1_8_21(case_row)
    lines: list[str] = []
    used = 0
    for entry in entries:
        body = _interview_entry_body_1_8_21(entry)
        if not body:
            continue
        used += 1
        name = _first_clean_1_7(entry.get('name'), case_row.get('suspect_name'), f'avhørt person {used}')
        role = _first_clean_1_7(entry.get('role'), 'mistenkt/siktet')
        method = _first_clean_1_7(entry.get('method'), 'ikke oppgitt')
        place = _first_clean_1_7(entry.get('place'), _place_phrase_1_7(case_row))
        start = _fmt_datetime(entry.get('start') or case_row.get('start_time'))
        end = _fmt_datetime(entry.get('end') or case_row.get('end_time'))
        if used > 1:
            lines.append('')
        lines.append(f'Avhør av {name}')
        lines.append(f'{name} ble avhørt som {role}. Avhøret ble gjennomført {start} - {end} ved {place}. Metode: {method}.')
        lines.append('Avhørte ble gjort kjent med hva saken gjelder, retten til ikke å forklare seg og retten til å la seg bistå av forsvarer før forklaring ble gitt.')
        lines.append('Forklaring/sammendrag:')
        lines.append(body.strip())
        if end and end != '-':
            lines.append(f'Avhøret ble avsluttet {end}.')
    return _clean_standard_text_1_7('\n'.join(lines).strip(), case_row) if used else ''


def _image_caption_base_1_8_24(item: Dict[str, Any], idx: int) -> str:  # type: ignore[override]
    raw = _first_clean_1_7(item.get('caption'), item.get('original_filename'), item.get('filename'), f'foto {idx}')
    raw = _strip_position_phrases_1_8_24(_strip_inline_seizure_text_1_8_24(raw))
    raw = re.sub(r'\s+', ' ', raw).strip(' .')
    if not raw:
        raw = f'foto {idx}'
    low = raw.lower()
    if low.startswith('bilde viser') or low.startswith('foto viser'):
        text = raw[0].upper() + raw[1:]
    else:
        text = 'Bilde viser ' + raw[0].lower() + raw[1:]
    return _sentence_1_7(text)


def _build_illustration_texts(evidence_rows: list[Dict[str, Any]]) -> list[str]:  # type: ignore[override]
    if not evidence_rows:
        return ['Ingen illustrasjoner registrert i saken.']
    texts: list[str] = []
    for idx, item in enumerate(evidence_rows, start=1):
        finding_key = str(item.get('finding_key') or '').strip().lower()
        caption = str(item.get('caption') or '').strip()
        filename = str(item.get('filename') or item.get('generated_path') or '').strip().lower()
        if finding_key == 'oversiktskart':
            if '2km' in filename or '5km' in filename or caption.lower().startswith('detaljert'):
                texts.append('Bilde viser detaljert kartutsnitt med kontrollposisjon og registrerte avviks-/beslagsposisjoner.')
            else:
                texts.append('Bilde viser oversiktskart av kontrollposisjon.')
            continue
        base = _image_caption_base_1_8_24(item, idx).rstrip('.')
        extras: list[str] = []
        seizure = _first_clean_1_7(item.get('seizure_ref'))
        reason = _strip_position_phrases_1_8_24(_strip_inline_seizure_text_1_8_24(_first_clean_1_7(item.get('violation_reason'))))
        if seizure:
            extras.append(f'beslag {seizure}')
        if reason:
            extras.append('avvik: ' + _shorten_sentence_1_8_21(reason, 80).rstrip('.'))
        if extras:
            base += ' - ' + ' - '.join(extras)
        texts.append(_shorten_sentence_1_8_21(_sentence_1_7(base), 190))
    return texts


def build_summary(case_row: Dict[str, Any], findings: list[Dict[str, Any]]) -> str:  # type: ignore[override]
    if (case_row.get('summary') or '').strip():
        return _clean_standard_text_1_7(case_row.get('summary'), case_row)
    when = _case_time_phrase_1_8_23(case_row)
    place = _case_place_1_8_23(case_row)
    lines: list[str] = [
        f'Kontrollen ble gjennomført {when} ved {place}. Kontrolltema var {_topic_narrative_1_8_25(case_row)}.',
        build_control_reason(case_row, findings),
    ]
    avvik = _avvik_1_7(findings)
    if avvik:
        lines.append('Registrerte avvik:')
        lines.extend(_short_avvik_lines_1_8_24(findings, limit=180))
        lines.append('Dokumentasjon fremgår av egenrapport, beslagsrapport og illustrasjonsmappe/fotomappe. Avhørsrapport tas bare med når avhør er merket gjennomført.')
    else:
        lines.append('Det er ikke registrert avvik i kontrollpunktene.')
    return _clean_standard_text_1_7('\n'.join(lines), case_row)


def build_text_drafts(case_row: Dict[str, Any], findings: list[Dict[str, Any]]) -> Dict[str, str]:  # type: ignore[override]
    return {
        'summary': build_summary(case_row, findings),
        'basis_details': build_control_reason(case_row, findings),
        'notes': '',
        'complaint_preview': _build_short_complaint(case_row, findings, _safe_sources(case_row)),
        'source_label': 'straffesaksmal 1.8.27',
    }


_build_case_packet_before_1_8_26 = build_case_packet


def build_case_packet(case_row: Dict[str, Any], evidence_rows: Iterable[Dict[str, Any]]) -> Dict[str, Any]:  # type: ignore[override]
    packet = _build_case_packet_before_1_8_26(case_row, evidence_rows)
    findings = [dict(item, display_notes=_finding_display_note(item)) for item in _safe_findings(case_row)]
    sources = _safe_sources(case_row)
    image_rows = list(packet.get('evidence') or [])
    has_interview = _has_interview_report_content_1_8_21(case_row)
    packet.update({
        'has_offences': bool(_offence_blocks(case_row, findings)),
        'title': _offence_title(case_row, findings),
        'summary': build_summary(case_row, findings),
        'short_complaint': _build_short_complaint(case_row, findings, sources),
        'own_report': _build_own_report(case_row, findings),
        'interview_report': _build_interview_report(case_row) if has_interview else '',
        'interview_guidance': '',
        'interview_not_conducted': not has_interview,
        'seizure_rows': _stored_seizure_rows_v93(case_row, findings, image_rows),
        'seizure_report': _build_seizure_report(case_row, image_rows),
        'illustration_texts': _build_illustration_texts(image_rows),
        'legal_refs': _registered_avvik_ref_rows_1_8_21(case_row, findings),
        'findings': findings,
        'sources': sources,
        'notes': _build_own_report(case_row, findings),
    })
    return packet


# 1.8.27: sakshodet tåler flere forhold uten å klippe siste ord/linje.
def _draw_sak_section(c: rl_canvas.Canvas, case_row: Dict[str, Any], top: float, location_label: str = 'Åsted', include_identity: bool = False) -> float:  # type: ignore[override]
    l, mid, r = 118, 808, 1128
    y = top
    _draw_section_caption(c, l, y, r, y + 28, 'Sak')
    y += 28
    title = _offence_title(case_row, _safe_findings(case_row))
    title_len = len(title)
    manual_lines = max(1, len(str(title).split('\n')))
    approx_wrap_lines = max(manual_lines, math.ceil(max(1, title_len) / 58))
    title_row_h = max(58, min(220, 36 + approx_wrap_lines * 24))
    row1 = y + title_row_h
    row2 = row1 + 44
    row3 = row2 + 34
    row4 = row3 + 38
    value_size = 8.2 if approx_wrap_lines <= 3 else 7.2
    _draw_label_value(c, l, y, mid, row1, 'Anmeldt forhold', title, value_size=value_size)
    _draw_label_value(c, l, row1, 351, row2, 'Fra dato kl.', _fmt_datetime_packet(case_row.get('start_time')))
    _draw_label_value(c, 351, row1, 579, row2, 'Til dato kl.', _fmt_datetime_packet(case_row.get('end_time')))
    _draw_label_value(c, 579, row1, mid, row2, 'Reg. dato', _fmt_datetime_packet(case_row.get('updated_at') or case_row.get('created_at')))
    _draw_label_value(c, l, row2, mid, row3, 'Sone', _fmt_value(case_row.get('zone_name') or case_row.get('sea_zone') or 'Skagerrak'))
    _draw_label_value(c, l, row3, mid, row4, location_label, _fmt_value(case_row.get('location_name') or _area_name_value(case_row)))
    _draw_label_value(c, mid, y, r, row1, 'Etterforskningsinstans', '')
    _draw_label_value(c, mid, row1, r, row2, 'Stat. bokstav | Stat. gruppe | Modus | Sone', '')
    _draw_label_value(c, mid, row2, r, row3, 'Påtaleansvarlig', '')
    _draw_label_value(c, mid, row3, r, row4, 'Etterforsker', _fmt_value(case_row.get('investigator_name')))
    y = row4
    if include_identity:
        row5 = y + 38
        _draw_label_value(c, l, y, 579, row5, 'Navn', _fmt_value(case_row.get('suspect_name')))
        _draw_label_value(c, 579, y, 808, row5, 'Fødselsnr', _fmt_value(case_row.get('suspect_birthdate')))
        _draw_label_value(c, 808, y, r, row5, 'Rolle', 'Siktet / Mistenkt')
        y = row5
    return y

# 1.8.27a: sikre at hjemler hentes fra faktisk avviksblokk (refs), og ikke tom fallbackrad.
def _registered_avvik_ref_rows_1_8_21(case_row: Dict[str, Any], findings: list[Dict[str, Any]] | None = None) -> list[Dict[str, str]]:  # type: ignore[override]
    findings = findings if findings is not None else _safe_findings(case_row)
    rows: list[Dict[str, str]] = []
    for block in _offence_blocks(case_row, findings):
        for ref in block.get('refs') or block.get('legal_refs') or []:
            if isinstance(ref, dict):
                display = _display_ref_row_1_8_23(ref)
                if display.get('name') or display.get('ref') or display.get('excerpt') or display.get('law_text'):
                    rows.append(display)
    # Enkelte frontend-versjoner lagret hjemler direkte i funnet som legal_refs.
    if not rows:
        for item in findings or []:
            if str(item.get('status') or '').strip().lower() != 'avvik':
                continue
            for ref in item.get('legal_refs') or []:
                if isinstance(ref, dict):
                    display = _display_ref_row_1_8_23(ref)
                    if display.get('name') or display.get('ref') or display.get('excerpt') or display.get('law_text'):
                        rows.append(display)
    return _merge_ref_rows(rows)

# 1.8.27b: slå sammen refs fra både blokk og funn, slik at alle avvikshjemler blir med.
def _registered_avvik_ref_rows_1_8_21(case_row: Dict[str, Any], findings: list[Dict[str, Any]] | None = None) -> list[Dict[str, str]]:  # type: ignore[override]
    findings = findings if findings is not None else _safe_findings(case_row)
    rows: list[Dict[str, str]] = []
    for block in _offence_blocks(case_row, findings):
        for ref in block.get('refs') or block.get('legal_refs') or []:
            if isinstance(ref, dict):
                display = _display_ref_row_1_8_23(ref)
                if display.get('name') or display.get('ref') or display.get('excerpt') or display.get('law_text'):
                    rows.append(display)
    for item in findings or []:
        if str(item.get('status') or '').strip().lower() != 'avvik':
            continue
        for ref in item.get('legal_refs') or []:
            if isinstance(ref, dict):
                display = _display_ref_row_1_8_23(ref)
                if display.get('name') or display.get('ref') or display.get('excerpt') or display.get('law_text'):
                    rows.append(display)
    return _merge_ref_rows(rows)

# 1.8.27c: kompakte saksfelt på egenrapport/beslag/foto får også dynamisk høyde.
def _draw_sak_section_compact(c: rl_canvas.Canvas, case_row: Dict[str, Any], top: float) -> float:  # type: ignore[override]
    l, mid, r = 118, 808, 1128
    y = top
    _draw_section_caption(c, l, y, r, y + 28, 'Sak')
    y += 28
    title = _offence_title(case_row, _safe_findings(case_row))
    title_len = len(title)
    manual_lines = max(1, len(str(title).split('\n')))
    approx_wrap_lines = max(manual_lines, math.ceil(max(1, title_len) / 58))
    title_row_h = max(52, min(170, 30 + approx_wrap_lines * 22))
    row1 = y + title_row_h
    row2 = row1 + 40
    row3 = row2 + 34
    value_size = 8.0 if approx_wrap_lines <= 3 else 7.0
    _draw_label_value(c, l, y, mid, row1, 'Anmeldt forhold', title, value_size=value_size)
    _draw_label_value(c, l, row1, 351, row2, 'Fra dato kl.', _fmt_datetime_packet(case_row.get('start_time')))
    _draw_label_value(c, 351, row1, 579, row2, 'Til dato kl.', _fmt_datetime_packet(case_row.get('end_time')))
    _draw_label_value(c, 579, row1, mid, row2, 'Reg. dato', _fmt_datetime_packet(case_row.get('updated_at') or case_row.get('created_at')))
    _draw_label_value(c, l, row2, mid, row3, 'Sone', _fmt_value(case_row.get('zone_name') or case_row.get('sea_zone') or 'Skagerrak'))
    _draw_label_value(c, mid, y, r, row1, 'Etterforskningsinstans', '')
    _draw_label_value(c, mid, row1, r, row2, 'Stat. gruppe | Modus | Sone', '')
    _draw_label_value(c, mid, row2, r, row3, 'Etterforsker', _fmt_value(case_row.get('investigator_name')))
    return row3

# ---- 1.8.27: mer formelle IKV-tekster basert på tidligere anmeldelser og føringer ----
# Målet er at autogenererte tekster skal være nøkterne, tettskrevne og etterprøvbare:
# - anmeldelsen forklarer hvem/hva/hvor/når/hvordan og bevissituasjonen
# - egenrapporten er rapportskrivers observasjoner, ikke gjentakelse av anmeldelsen
# - lovhjemler er korte utdrag knyttet til registrerte avvik
# - patruljeformål tilpasses patrulje/tips, fiskeri, art, redskap og område

_AUTOGEN_BASIS_MARKERS_1_8_27 = (
    'kontrollere fiskerikontroll',
    'patruljeformålet var å kontrollere',
    'formålet var å føre kontroll med',
    'kontrollen ble gjennomført av',
    'gjennomførte den',
    'tipsopplysningene ga grunnlag',
    'rapporten bygger på patruljens egne observasjoner',
    'kontrollstedet ble samtidig vurdert opp mot registrert områdestatus',
)


def _clean_sentence_join_1_8_27(parts: list[str]) -> str:
    text = ' '.join(str(part or '').strip() for part in parts if str(part or '').strip())
    text = re.sub(r'\s+', ' ', text).strip()
    text = re.sub(r'\s+([,.;:])', r'\1', text)
    text = re.sub(r'\s*/\s*', '/', text)
    return text


def _looks_autogenerated_basis_1_8_27(text: Any) -> bool:
    low = str(text or '').strip().lower()
    if not low:
        return True
    if _looks_like_old_generated_basis_1_8_22(low):
        return True
    return any(marker in low for marker in _AUTOGEN_BASIS_MARKERS_1_8_27)


def _topic_context_1_8_27(case_row: Dict[str, Any]) -> dict[str, str]:
    control = _topic_part_1_8_26(case_row.get('control_type'))
    species = _topic_part_1_8_26(case_row.get('species') or case_row.get('fishery_type'))
    gear = _topic_part_1_8_26(case_row.get('gear_type'))
    topic = _topic_narrative_1_8_25(case_row)
    return {'control': control, 'species': species, 'gear': gear, 'topic': topic}


def _purpose_focus_1_8_27(case_row: Dict[str, Any], findings: list[Dict[str, Any]] | None = None) -> str:
    ctx = _topic_context_1_8_27(case_row)
    species = ctx['species'].lower()
    gear = ctx['gear'].lower()
    keys = {str((item or {}).get('key') or '').lower() for item in (findings or []) if isinstance(item, dict)}
    focus: list[str] = []
    if 'hummer' in species or any(k.startswith('hummer') for k in keys):
        focus.extend([
            'deltakelse/deltakernummer',
            'merking av vak/blåse og redskap',
            'antall teiner',
            'fluktåpninger/rømningshull',
            'fangst og oppbevaring',
        ])
        if any(k in keys for k in {'hummer_lengdekrav', 'hummer_minstemal', 'hummer_maksimalmal'}) or 'hummer' in species:
            focus.append('lengdemål')
        focus.append('relevante periode- og områdebestemmelser')
    elif any(word in gear for word in ['teine', 'ruse', 'garn', 'lenke', 'line']):
        focus.extend([
            'merking av vak/blåse og redskap',
            'redskapets utforming',
            'plassering',
            'fangst/oppbevaring',
            'ansvarlig bruker/eier',
            'relevante områdebestemmelser',
        ])
    else:
        focus.extend([
            'redskap',
            'merking',
            'fangst/oppbevaring',
            'posisjon',
            'relevante områdebestemmelser',
        ])
    return _natural_join(focus)


def _area_context_1_8_27(case_row: Dict[str, Any]) -> str:
    area_name = _first_clean_1_7(case_row.get('area_name'))
    area_status = _first_clean_1_7(case_row.get('area_status'))
    if area_status.lower() in {'ingen treff', 'ikke oppgitt', 'ukjent', '-'}:
        area_status = ''
    if area_name and area_status and area_status.lower() not in area_name.lower():
        return f'{area_name} ({area_status})'
    return area_name or area_status


def _formal_custom_basis_1_8_27(case_row: Dict[str, Any], findings: list[Dict[str, Any]], text: str) -> str:
    cleaned = _clean_standard_text_1_7(text, case_row)
    cleaned = re.sub(r'kontrollere\s+fiskerikontroll\s*', 'føre kontroll med ', cleaned, flags=re.IGNORECASE)
    cleaned = cleaned.replace('aktuelt fiskeri / redskap', 'aktuelt fiskeri og redskap')
    cleaned = re.sub(r'\bPatruljeformålet var å kontrollere\b', 'Formålet var å føre kontroll med', cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r'\s{2,}', ' ', cleaned).strip()
    basis = _normal_case_basis_1_8_22(case_row.get('case_basis'))
    if basis == 'tips' and 'patruljens egne observasjoner' not in cleaned.lower():
        source = _first_clean_1_7(case_row.get('basis_source_name'))
        source_text = f' fra {source}' if source else ''
        cleaned = (f'Kontrollen ble gjennomført på bakgrunn av tips/opplysninger{source_text}. '
                   f'Tipset er brukt som bakgrunn for kontrollen. {cleaned.rstrip(".")}. '
                   f'De faktiske forholdene i rapporten bygger på patruljens egne observasjoner, kontroll av redskapet og dokumentasjon sikret på stedet.')
    return _clean_standard_text_1_7(cleaned, case_row)


def _generated_control_basis_1_8_27(case_row: Dict[str, Any], findings: list[Dict[str, Any]]) -> str:
    basis = _normal_case_basis_1_8_22(case_row.get('case_basis'))
    unit = _case_vessel_unit_1_8_23(case_row)
    when = _case_time_phrase_1_8_23(case_row)
    place = _case_place_1_8_23(case_row)
    ctx = _topic_context_1_8_27(case_row)
    topic = ctx['topic']
    focus = _purpose_focus_1_8_27(case_row, findings)
    area = _area_context_1_8_27(case_row)
    source = _first_clean_1_7(case_row.get('basis_source_name'))

    if basis == 'tips':
        source_text = f' fra {source}' if source else ''
        parts = [
            f'{unit} gjennomførte den {when} fiskerioppsyn ved {place} på bakgrunn av tips/opplysninger{source_text}.',
            f'Tipset ga grunnlag for å kontrollere {topic}.',
            f'Kontrollen ble rettet mot {focus}.',
            'De forhold som omtales i rapporten bygger på patruljens egne observasjoner, kontroll av redskapet og dokumentasjon sikret på stedet.',
        ]
    else:
        parts = [
            f'{unit} gjennomførte den {when} fiskerioppsyn ved {place}.',
            f'Formålet var å føre kontroll med {topic} og avklare om {focus} var i samsvar med gjeldende regelverk.',
        ]
    if area:
        parts.append(f'Kontrollstedet ble vurdert opp mot registrerte områdebestemmelser for {area}.')
    return _clean_standard_text_1_7(' '.join(parts), case_row)


def build_control_reason(case_row: Dict[str, Any], findings: list[Dict[str, Any]]) -> str:  # type: ignore[override]
    explicit = str(case_row.get('basis_details') or '').strip()
    if explicit and not _looks_autogenerated_basis_1_8_27(explicit):
        return _formal_custom_basis_1_8_27(case_row, findings, explicit)
    return _generated_control_basis_1_8_27(case_row, findings)


def _own_report_basis_1_8_25(case_row: Dict[str, Any], findings: list[Dict[str, Any]]) -> str:  # type: ignore[override]
    # Egenrapporten skal ikke gjenta tid/sted fra første avsnitt. Bruk bare formål/bakgrunn.
    explicit = str(case_row.get('basis_details') or '').strip()
    if explicit and not _looks_autogenerated_basis_1_8_27(explicit):
        text = _formal_custom_basis_1_8_27(case_row, findings, explicit)
        text = re.sub(r'^[^.]*?gjennomførte\s+den\s+[^.]*?\.[ ]*', '', text, flags=re.IGNORECASE).strip()
        text = re.sub(r'^Kontrollen ble gjennomført på bakgrunn av tips/opplysninger[^.]*\.[ ]*', 'Kontrollen ble gjennomført på bakgrunn av tips/opplysninger. ', text, flags=re.IGNORECASE).strip()
        return _clean_standard_text_1_7(text or _purpose_sentence_for_own_report_1_8_27(case_row, findings), case_row)
    return _purpose_sentence_for_own_report_1_8_27(case_row, findings)


def _purpose_sentence_for_own_report_1_8_27(case_row: Dict[str, Any], findings: list[Dict[str, Any]]) -> str:
    basis = _normal_case_basis_1_8_22(case_row.get('case_basis'))
    ctx = _topic_context_1_8_27(case_row)
    focus = _purpose_focus_1_8_27(case_row, findings)
    source = _first_clean_1_7(case_row.get('basis_source_name'))
    if basis == 'tips':
        source_text = f' fra {source}' if source else ''
        return _clean_standard_text_1_7(
            f'Kontrollen ble gjennomført på bakgrunn av tips/opplysninger{source_text}. Tipset ble brukt som utgangspunkt for kontrollen. Rapporten bygger på patruljens egne observasjoner, kontroll av redskapet og dokumentasjon sikret på stedet.',
            case_row,
        )
    return _clean_standard_text_1_7(
        f'Formålet var å føre kontroll med {ctx["topic"]} og avklare om {focus} var i samsvar med gjeldende regelverk.',
        case_row,
    )


def _findings_by_offence_title_1_8_27(findings: list[Dict[str, Any]]) -> list[tuple[str, str]]:
    rows: list[tuple[str, str]] = []
    for item in _avvik_1_7(findings):
        block = _offence_from_finding({}, item, findings)
        title = _title_shortener_1_8_25(_offence_title_from_block_1_8_23(block))
        note = _strip_position_phrases_1_8_24(_strip_inline_seizure_text_1_8_24(_first_clean_1_7(item.get('notes'), item.get('auto_note'), item.get('summary_text'), _finding_display_note(item))))
        note = re.sub(r'^' + re.escape(title) + r'[:.\s-]*', '', note, flags=re.IGNORECASE).strip()
        rows.append((title, _shorten_sentence_1_8_21(note, 210) if note else ''))
    return rows


def _short_avvik_lines_1_8_24(findings: list[Dict[str, Any]], *, limit: int = 220) -> list[str]:  # type: ignore[override]
    rows = _findings_by_offence_title_1_8_27(findings)
    if not rows:
        return ['Det er ikke registrert avvik i kontrollpunktene på tidspunktet rapporten ble laget.']
    out: list[str] = []
    for idx, (title, note) in enumerate(rows, start=1):
        text = title
        if note:
            text += ': ' + _shorten_sentence_1_8_21(note, limit)
        out.append(f'{idx}. {_sentence_1_7(text)}')
    return out


def _offence_fact_line_1_8_25(block: Dict[str, Any], idx: int) -> str:  # type: ignore[override]
    title = _title_shortener_1_8_25(_offence_title_from_block_1_8_23(block))
    details = _strip_position_phrases_1_8_24(_strip_inline_seizure_text_1_8_24(block.get('details') or ''))
    details = re.sub(r'^Mulig\s+brudd\s+på\s+[^:]+:\s*', '', details, flags=re.IGNORECASE).strip()
    details = re.sub(r'\bkontrollposisjon[^.]*\.?', '', details, flags=re.IGNORECASE).strip()
    details = re.sub(r'\s{2,}', ' ', details).strip(' ;,.-')
    if details and title.lower() not in details.lower():
        text = f'{title}: {details}'
    else:
        text = title
    return f'{idx}. {_shorten_sentence_1_8_21(_sentence_1_7(text), 300)}'


def _build_short_complaint(case_row: Dict[str, Any], findings: list[Dict[str, Any]], sources: list[Dict[str, Any]]) -> str:  # type: ignore[override]
    override = str(case_row.get('complaint_override') or '').strip()
    if override:
        return _clean_standard_text_1_7(_strip_doc_heading_1_8_23(override), case_row)
    subject = _subject_name_1_8_25(case_row)
    when = _case_time_phrase_1_8_23(case_row)
    place = _case_place_1_8_23(case_row)
    unit = _case_vessel_unit_1_8_23(case_row)
    topic = _topic_narrative_1_8_25(case_row)
    offences = _offence_blocks(case_row, findings)
    titles = _offence_titles_1_8_25(case_row, findings)

    if not offences:
        return _clean_standard_text_1_7(
            f'Det ble gjennomført fiskerikontroll {when} ved {place}. Det er ikke registrert avvik som danner grunnlag for anmeldelse i kontrollpunktene på tidspunktet for utkastet.',
            case_row,
        )

    lines: list[str] = []
    if len(titles) == 1:
        lines.append(f'Med dette anmeldes {subject} for {titles[0].lower()} avdekket {when} ved {place}.')
    else:
        lines.append(f'Med dette anmeldes {subject} for følgende forhold avdekket {when} ved {place}:')
        for idx, title in enumerate(titles, start=1):
            lines.append(f'{idx}. {title}.')
    lines.append('')
    lines.append(f'{"Forholdene" if len(titles) > 1 else "Forholdet"} ble avdekket da {unit} gjennomførte fiskerioppsyn/kontroll med {topic}.')
    lines.append('')
    lines.append('Kort beskrivelse av faktum:')
    for idx, block in enumerate(offences, start=1):
        lines.append(_offence_fact_line_1_8_25(block, idx))
    lines.append('')
    lines.append('Aktuelle lovhjemler er begrenset til bestemmelsene som er knyttet til registrerte avvik i kontrollpunktene.')
    lines.append('For nærmere detaljer om de faktiske observasjonene, redskap/beslag og sikret bildedokumentasjon vises det til sakens ' + _evidence_doc_phrase_1_8_26(case_row) + '.')
    return _clean_standard_text_1_7('\n'.join(lines).strip(), case_row)


def _build_own_report(case_row: Dict[str, Any], findings: list[Dict[str, Any]]) -> str:  # type: ignore[override]
    override = str(case_row.get('own_report_override') or '').strip()
    if override:
        return _clean_standard_text_1_7(_strip_doc_heading_1_8_23(override), case_row)
    investigator = _first_clean_1_7(case_row.get('investigator_name'), 'rapportskriver')
    unit = _case_vessel_unit_1_8_23(case_row)
    when = _case_time_phrase_1_8_23(case_row)
    place = _case_place_1_8_23(case_row)
    topic = _topic_narrative_1_8_25(case_row)
    crew = _crew_text(case_row)
    subject = _subject_name_1_8_25(case_row, fallback='')
    paragraphs: list[str] = []
    paragraphs.append(f'Den {when} gjennomførte {unit} fiskerioppsyn ved {place}. Jeg, {investigator}, deltok i kontrollen. Kontrolltema var {topic}.')
    if crew and crew != '-':
        paragraphs.append(f'Inspeksjonslaget/øvrig personell som er registrert i saken: {crew}.')
    paragraphs.append(_own_report_basis_1_8_25(case_row, findings))
    if subject:
        paragraphs.append(f'Kontrollobjekt/ansvarlig registrert i saken er {subject}.')
    avvik_lines = _short_avvik_lines_1_8_24(findings, limit=260)
    if _avvik_1_7(findings):
        paragraphs.append('Under kontrollen ble følgende forhold registrert som avvik:\n' + '\n'.join(avvik_lines))
    else:
        paragraphs.append('Det ble ikke registrert avvik i kontrollpunktene på tidspunktet rapporten ble laget.')
    if _seizure_rows_1_7(case_row, findings):
        paragraphs.append('På bakgrunn av observasjonene ble redskap/beslag dokumentert i egen beslagsrapport. Redskapets posisjon fremgår av beslagsrapporten. Relevante fotografier og kartutsnitt fremgår av illustrasjonsmappe/fotomappe.')
    else:
        paragraphs.append('Relevante fotografier og kartutsnitt fremgår av illustrasjonsmappe/fotomappe der dette er registrert.')
    if _has_interview_report_content_1_8_21(case_row):
        paragraphs.append('Gjennomført avhør/forklaring er protokollert i egen avhørsrapport.')
    notes = _strip_position_phrases_1_8_24(_strip_inline_seizure_text_1_8_24(_strip_generated_report_noise_1_8_21(case_row.get('notes'))))
    if notes:
        paragraphs.append('Kontrollørs merknad: ' + _shorten_sentence_1_8_21(notes, 360))
    return _clean_standard_text_1_7('\n\n'.join(part for part in paragraphs if part).strip(), case_row)


def build_summary(case_row: Dict[str, Any], findings: list[Dict[str, Any]]) -> str:  # type: ignore[override]
    if (case_row.get('summary') or '').strip():
        return _clean_standard_text_1_7(case_row.get('summary'), case_row)
    when = _case_time_phrase_1_8_23(case_row)
    place = _case_place_1_8_23(case_row)
    lines: list[str] = [
        f'Kontrollen ble gjennomført {when} ved {place}. Kontrolltema var {_topic_narrative_1_8_25(case_row)}.',
        _own_report_basis_1_8_25(case_row, findings),
    ]
    if _avvik_1_7(findings):
        lines.append('Registrerte avvik:')
        lines.extend(_short_avvik_lines_1_8_24(findings, limit=180))
        lines.append('Dokumentasjon fremgår av egenrapport, beslagsrapport og illustrasjonsmappe/fotomappe. Avhørsrapport tas bare med når avhør er merket gjennomført.')
    else:
        lines.append('Det er ikke registrert avvik i kontrollpunktene.')
    return _clean_standard_text_1_7('\n'.join(lines), case_row)


def build_text_drafts(case_row: Dict[str, Any], findings: list[Dict[str, Any]]) -> Dict[str, str]:  # type: ignore[override]
    return {
        'summary': build_summary(case_row, findings),
        'basis_details': build_control_reason(case_row, findings),
        'notes': '',
        'complaint_preview': _build_short_complaint(case_row, findings, _safe_sources(case_row)),
        'source_label': 'straffesaksmal 1.8.27',
    }

# 1.8.27a: fjern dobbeltføring inne i kort faktumbeskrivelse.
def _dedupe_fact_fragments_1_8_27(text: Any) -> str:
    raw = re.sub(r'\s+', ' ', str(text or '')).strip(' ;,.-')
    if not raw:
        return ''
    parts = re.split(r'\s*(?:;|\.\s+|\n)\s*', raw)
    out: list[str] = []
    seen: set[str] = set()
    for part in parts:
        frag = re.sub(r'\s+', ' ', part).strip(' ;,.-')
        if not frag:
            continue
        key = re.sub(r'[^a-z0-9æøå]+', '', frag.lower())
        if key in seen:
            continue
        seen.add(key)
        out.append(frag)
    return '; '.join(out)


def _offence_fact_line_1_8_25(block: Dict[str, Any], idx: int) -> str:  # type: ignore[override]
    title = _title_shortener_1_8_25(_offence_title_from_block_1_8_23(block))
    details = _strip_position_phrases_1_8_24(_strip_inline_seizure_text_1_8_24(block.get('details') or ''))
    details = re.sub(r'^Mulig\s+brudd\s+på\s+[^:]+:\s*', '', details, flags=re.IGNORECASE).strip()
    details = re.sub(r'\bkontrollposisjon[^.]*\.?', '', details, flags=re.IGNORECASE).strip()
    details = _dedupe_fact_fragments_1_8_27(details)
    if details and title.lower() not in details.lower():
        text = f'{title}: {details}'
    else:
        text = title
    return f'{idx}. {_shorten_sentence_1_8_21(_sentence_1_7(text), 300)}'

# 1.8.27b: kortere avvikslinjer i egenrapport/oppsummering, uten dobbeltføring.
def _finding_title_1_8_27(item: Dict[str, Any]) -> str:
    dev = item.get('deviation') if isinstance(item.get('deviation'), dict) else {}
    candidates = [
        dev.get('title') if isinstance(dev, dict) else '',
        item.get('label'),
        item.get('title'),
        item.get('key'),
    ]
    title = _first_clean_1_7(*candidates)
    return _title_shortener_1_8_25(title or 'Avvik')


def _finding_note_for_report_1_8_27(item: Dict[str, Any], title: str) -> str:
    dev = item.get('deviation') if isinstance(item.get('deviation'), dict) else {}
    note = _first_clean_1_7(
        item.get('notes'),
        item.get('auto_note'),
        item.get('summary_text'),
        dev.get('details') if isinstance(dev, dict) else '',
        _finding_display_note(item),
    )
    note = _strip_position_phrases_1_8_24(_strip_inline_seizure_text_1_8_24(note))
    note = re.sub(r'^' + re.escape(str(title or '')) + r'[:.\s-]*', '', note, flags=re.IGNORECASE).strip()
    note = _dedupe_fact_fragments_1_8_27(note)
    if title and note and re.sub(r'[^a-z0-9æøå]+', '', note.lower()) == re.sub(r'[^a-z0-9æøå]+', '', title.lower()):
        return ''
    return note


def _findings_by_offence_title_1_8_27(findings: list[Dict[str, Any]]) -> list[tuple[str, str]]:  # type: ignore[override]
    rows: list[tuple[str, str]] = []
    for item in _avvik_1_7(findings):
        title = _finding_title_1_8_27(item)
        note = _finding_note_for_report_1_8_27(item, title)
        rows.append((title, _shorten_sentence_1_8_21(note, 210) if note else ''))
    return rows

# ---- 1.8.30: politifaglige standardtekster, objektiv/kildebevisst rapportstil ----
# Bygger videre på IKV-malene: anmeldelsen skal være kort og forklare hvem/hva/hvor/når,
# mens egenrapporten skal være rapportskrivers nøkterne observasjonsrapport med notoritet.

_AUTOGEN_BASIS_MARKERS_1_8_30 = _AUTOGEN_BASIS_MARKERS_1_8_27 + (
    'formålet var å kontrollere',
    'kontrollere kontroll',
    'gjennomføre kontroll av kontroll',
    'rapportgrunnlag',
)

_BAD_REPORT_PHRASES_1_8_30 = (
    'skyldig',
    'åpenbart ulovlig',
    'grovt lovbrudd',
    'bevist',
    'han lyver',
    'hun lyver',
)


def _compact_ws_1_8_30(value: Any) -> str:
    text = re.sub(r'\s+', ' ', str(value or '')).strip()
    text = re.sub(r'\s+([,.;:])', r'\1', text)
    text = re.sub(r'\s*/\s*', '/', text)
    return text


def _sanitize_formal_text_1_8_30(value: Any) -> str:
    text = _compact_ws_1_8_30(value)
    replacements = [
        (r'kontrollere\s+fiskerikontroll', 'føre kontroll med'),
        (r'kontrollere\s+kontroll', 'føre kontroll med'),
        (r'gjennomføre\s+kontroll\s+av\s+kontroll', 'gjennomføre kontroll med'),
        (r'aktuelt\s+fiskeri\s*/\s*redskap', 'aktuelt fiskeri og redskap'),
        (r'Patruljeformålet\s+var\s+å\s+kontrollere', 'Formålet var å føre kontroll med'),
        (r'Formålet\s+var\s+å\s+kontrollere', 'Formålet var å føre kontroll med'),
    ]
    for pattern, repl in replacements:
        text = re.sub(pattern, repl, text, flags=re.IGNORECASE)
    text = re.sub(r'føre\s+kontroll\s+med\s+med\s+', 'føre kontroll med ', text, flags=re.IGNORECASE)
    text = re.sub(r'\s{2,}', ' ', text).strip(' ;,')
    return text


def _looks_autogenerated_basis_1_8_30(text: Any) -> bool:
    low = str(text or '').strip().lower()
    if not low:
        return True
    if _looks_autogenerated_basis_1_8_27(low):
        return True
    return any(marker in low for marker in _AUTOGEN_BASIS_MARKERS_1_8_30)


def _case_when_1_8_30(case_row: Dict[str, Any]) -> str:
    when = _case_time_phrase_1_8_23(case_row)
    return when if when and when != '-' else 'kontrolltidspunktet'


def _case_place_1_8_30(case_row: Dict[str, Any]) -> str:
    place = _case_place_1_8_23(case_row)
    return place if place and place != '-' else 'kontrollstedet'


def _topic_narrative_1_8_30(case_row: Dict[str, Any]) -> str:
    control = _topic_part_1_8_26(case_row.get('control_type'))
    species = _topic_part_1_8_26(case_row.get('species') or case_row.get('fishery_type'))
    gear = _topic_part_1_8_26(case_row.get('gear_type'))
    parts: list[str] = []
    if control:
        parts.append(control.lower())
    if species:
        if control and 'fiske' in control.lower():
            parts.append('etter ' + species.lower())
        else:
            parts.append(species.lower())
    if gear:
        parts.append('med ' + gear.lower())
    topic = _compact_ws_1_8_30(' '.join(parts)).strip(' .')
    return topic or 'aktuelle fiskeri- og redskapsbestemmelser'


def _subject_name_1_8_30(case_row: Dict[str, Any], *, fallback: str = 'ukjent gjerningsperson') -> str:
    return _first_clean_1_7(
        case_row.get('suspect_name'),
        case_row.get('responsible_name'),
        case_row.get('vessel_name'),
        fallback,
    )


def _case_vessel_unit_1_8_30(case_row: Dict[str, Any]) -> str:
    unit = _case_vessel_unit_1_8_23(case_row)
    return unit if unit and unit != '-' else 'Kystvakten'


def _source_sentence_1_8_30(case_row: Dict[str, Any]) -> str:
    source = _first_clean_1_7(case_row.get('basis_source_name'))
    return f' fra {source}' if source else ''


def _purpose_focus_1_8_30(case_row: Dict[str, Any], findings: list[Dict[str, Any]] | None = None) -> str:
    species = str(case_row.get('species') or case_row.get('fishery_type') or '').lower()
    gear = str(case_row.get('gear_type') or '').lower()
    keys = {str((item or {}).get('key') or '').lower() for item in (findings or []) if isinstance(item, dict)}
    titles = ' '.join(_finding_title_1_8_27(item).lower() for item in (findings or []) if isinstance(item, dict))
    focus: list[str] = []

    def add(text: str) -> None:
        if text and text not in focus:
            focus.append(text)

    if 'hummer' in species or 'hummer' in titles or any(k.startswith('hummer') for k in keys):
        add('deltakelse/deltakernummer')
        add('merking av vak/blåse og redskap')
        add('teinenes antall og utforming')
        if any(word in titles for word in ['flukt', 'rømningshull', 'råtnetråd']) or not findings:
            add('fluktåpninger/rømningshull')
        if any(word in titles for word in ['lengde', 'minstemål', 'maksimalmål']) or not findings:
            add('lengdemål')
        add('fangst og oppbevaring')
        add('relevante periode- og områdebestemmelser')
    elif any(word in gear for word in ['teine', 'ruse', 'garn', 'lenke', 'line']):
        add('merking av vak/blåse og redskap')
        add('redskapets utforming og plassering')
        add('fangst/oppbevaring')
        add('ansvarlig bruker/eier')
        add('relevante områdebestemmelser')
    else:
        add('redskap, merking og fangst/oppbevaring')
        add('posisjon og relevante områdebestemmelser')
    return _natural_join(focus)


def _area_sentence_1_8_30(case_row: Dict[str, Any]) -> str:
    area = _area_context_1_8_27(case_row)
    if not area:
        return ''
    return f' Kontrollstedet ble vurdert opp mot registrerte områdebestemmelser for {area}.'


def _clean_custom_basis_1_8_30(case_row: Dict[str, Any], findings: list[Dict[str, Any]], text: Any) -> str:
    cleaned = _sanitize_formal_text_1_8_30(_clean_standard_text_1_7(text, case_row))
    if not cleaned:
        return _generated_control_basis_1_8_30(case_row, findings)
    basis = _normal_case_basis_1_8_22(case_row.get('case_basis'))
    if basis == 'tips' and 'patruljens egne observasjoner' not in cleaned.lower():
        cleaned = (f'Kontrollen ble gjennomført på bakgrunn av tips/opplysninger{_source_sentence_1_8_30(case_row)}. '
                   f'{cleaned.rstrip(".")}. De forhold som omtales i rapporten bygger på patruljens egne observasjoner og dokumentasjon sikret under kontrollen.')
    return _clean_standard_text_1_7(cleaned, case_row)


def _generated_control_basis_1_8_30(case_row: Dict[str, Any], findings: list[Dict[str, Any]]) -> str:
    basis = _normal_case_basis_1_8_22(case_row.get('case_basis'))
    unit = _case_vessel_unit_1_8_30(case_row)
    when = _case_when_1_8_30(case_row)
    place = _case_place_1_8_30(case_row)
    topic = _topic_narrative_1_8_30(case_row)
    focus = _purpose_focus_1_8_30(case_row, findings)
    if basis == 'tips':
        text = (f'{unit} gjennomførte den {when} fiskerioppsyn ved {place} på bakgrunn av mottatte tips/opplysninger{_source_sentence_1_8_30(case_row)}. '
                f'Tipsopplysningene ga grunnlag for å kontrollere {topic}. Kontrollen ble rettet mot {focus}. '
                'De forhold som omtales i rapporten bygger på patruljens egne observasjoner og dokumentasjon sikret under kontrollen.')
    else:
        text = (f'{unit} gjennomførte den {when} fiskerioppsyn ved {place}. '
                f'Formålet var å føre kontroll med {topic} og avklare om {focus} var i samsvar med gjeldende regelverk.')
    text += _area_sentence_1_8_30(case_row)
    return _clean_standard_text_1_7(_sanitize_formal_text_1_8_30(text), case_row)


def build_control_reason(case_row: Dict[str, Any], findings: list[Dict[str, Any]]) -> str:  # type: ignore[override]
    explicit = str(case_row.get('basis_details') or '').strip()
    if explicit and not _looks_autogenerated_basis_1_8_30(explicit):
        return _clean_custom_basis_1_8_30(case_row, findings, explicit)
    return _generated_control_basis_1_8_30(case_row, findings)


def _own_report_basis_1_8_25(case_row: Dict[str, Any], findings: list[Dict[str, Any]]) -> str:  # type: ignore[override]
    explicit = str(case_row.get('basis_details') or '').strip()
    if explicit and not _looks_autogenerated_basis_1_8_30(explicit):
        cleaned = _clean_custom_basis_1_8_30(case_row, findings, explicit)
        cleaned = re.sub(r'^[^.]*?gjennomførte\s+den\s+[^.]*?fiskerioppsyn\s+ved\s+[^.]*?\.\s*', '', cleaned, flags=re.IGNORECASE).strip()
        return cleaned or _generated_control_basis_1_8_30(case_row, findings)
    basis = _normal_case_basis_1_8_22(case_row.get('case_basis'))
    topic = _topic_narrative_1_8_30(case_row)
    focus = _purpose_focus_1_8_30(case_row, findings)
    if basis == 'tips':
        return _clean_standard_text_1_7(
            f'Kontrollen ble gjennomført på bakgrunn av mottatte tips/opplysninger{_source_sentence_1_8_30(case_row)}. Tipsopplysningene ble brukt som utgangspunkt for kontrollen av {topic}. De forhold som omtales nedenfor bygger på kontrollørens egne observasjoner, kontroll av redskapet og dokumentasjon sikret under kontrollen.',
            case_row,
        )
    return _clean_standard_text_1_7(
        f'Formålet var å føre kontroll med {topic} og avklare om {focus} var i samsvar med gjeldende regelverk.',
        case_row,
    )


def _norm_key_1_8_30(value: Any) -> str:
    return re.sub(r'[^a-z0-9æøå]+', '', str(value or '').lower())


def _dedupe_report_lines_1_8_30(rows: list[str]) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for row in rows:
        text = _compact_ws_1_8_30(row).strip(' ;,.-')
        if not text:
            continue
        key = _norm_key_1_8_30(text)
        if key in seen:
            continue
        seen.add(key)
        out.append(text)
    return out


def _finding_note_for_report_1_8_30(item: Dict[str, Any], title: str) -> str:
    note = _finding_note_for_report_1_8_27(item, title)
    note = re.sub(r'\bkontrollposisjon[^.]*\.?', '', note, flags=re.IGNORECASE)
    note = re.sub(r'\bposisjon\s+[NØEWA-Z0-9°\'" .,:;-]+', '', note, flags=re.IGNORECASE)
    note = _dedupe_fact_fragments_1_8_27(note)
    return _shorten_sentence_1_8_21(note, 220).rstrip('.')


def _avvik_rows_1_8_30(findings: list[Dict[str, Any]]) -> list[tuple[str, str]]:
    rows: list[tuple[str, str]] = []
    seen: set[str] = set()
    for item in _avvik_1_7(findings):
        title = _finding_title_1_8_27(item)
        note = _finding_note_for_report_1_8_30(item, title)
        key = _norm_key_1_8_30(title + '|' + note)
        if key in seen:
            continue
        seen.add(key)
        rows.append((title, note))
    return rows


def _short_avvik_lines_1_8_24(findings: list[Dict[str, Any]], *, limit: int = 220) -> list[str]:  # type: ignore[override]
    rows = _avvik_rows_1_8_30(findings)
    if not rows:
        return ['Det er ikke registrert avvik i kontrollpunktene på tidspunktet rapporten ble laget.']
    out: list[str] = []
    for idx, (title, note) in enumerate(rows, start=1):
        line = title
        if note:
            line += ': ' + _shorten_sentence_1_8_21(note, limit).rstrip('.')
        out.append(f'{idx}. {_sentence_1_7(line)}')
    return out


def _registered_avvik_ref_rows_1_8_21(case_row: Dict[str, Any], findings: list[Dict[str, Any]] | None = None) -> list[Dict[str, str]]:  # type: ignore[override]
    findings = findings if findings is not None else _safe_findings(case_row)
    rows: list[Dict[str, str]] = []
    for block in _offence_blocks(case_row, findings):
        for ref in block.get('refs') or block.get('legal_refs') or []:
            if isinstance(ref, dict):
                display = _display_ref_row_1_8_23(ref)
                if display.get('name') or display.get('ref') or display.get('excerpt') or display.get('law_text'):
                    rows.append(display)
    for item in findings or []:
        if str(item.get('status') or '').strip().lower() != 'avvik':
            continue
        for key in ('legal_refs', 'refs', 'sources'):
            for ref in item.get(key) or []:
                if isinstance(ref, dict):
                    display = _display_ref_row_1_8_23(ref)
                    if display.get('name') or display.get('ref') or display.get('excerpt') or display.get('law_text'):
                        rows.append(display)
    return _merge_ref_rows(rows)


def _legal_head_list_1_8_30(case_row: Dict[str, Any], findings: list[Dict[str, Any]], *, max_items: int = 4) -> str:
    refs = _registered_avvik_ref_rows_1_8_21(case_row, findings)
    heads: list[str] = []
    seen: set[str] = set()
    for ref in refs:
        head = _legal_ref_head_1_8_23(ref).strip(' :')
        if not head:
            continue
        key = head.lower()
        if key in seen:
            continue
        seen.add(key)
        heads.append(head)
        if len(heads) >= max_items:
            break
    return _natural_join(heads) if heads else 'relevante bestemmelser i fiskeriregelverket'


def _law_excerpt_1_8_23(ref: Dict[str, Any], limit: int = 200) -> str:  # type: ignore[override]
    text = _clean_law_text_1_8_23(ref.get('law_text') or ref.get('excerpt'))
    if not text:
        return ''
    for pattern in [
        r'\bBestemmelsen lyder\b', r'\bNavn på gytefelt\b', r'\bBeskrivelsePunktPosisjon\b',
        r'\bPunktPosisjon\b', r'\bVidere\s+(?:nord|sør|øst|vest)', r'\bDerfra\s+videre\b',
        r'\bN\s*\d{1,2}[°º]', r'\bØ\s*\d{1,3}[°º]', r'\bE\s*\d{1,3}[°º]',
        r'\bpunkt\s+\d+\b', r'\bkoordinat', r'\btabell\b',
    ]:
        m = re.search(pattern, text, flags=re.IGNORECASE)
        if m and m.start() > 20:
            text = text[:m.start()].strip(' ,.;:')
            break
    sentences = [s.strip() for s in re.split(r'(?<=[.!?])\s+', text) if s.strip()]
    normative = ''
    for sent in sentences[:5]:
        if re.search(r'\b(skal|forbudt|ikke tillatt|plikter|må|krav|straffes|straffbart|tillatt|forbud)', sent, flags=re.IGNORECASE):
            normative = sent
            break
    excerpt = normative or (sentences[0] if sentences else text)
    excerpt = _compact_ws_1_8_30(excerpt)
    if len(excerpt) > limit:
        excerpt = excerpt[:limit].rsplit(' ', 1)[0].rstrip(' ,.;:') + '...'
    return excerpt.strip()


def _display_ref_row_1_8_23(ref: Dict[str, Any]) -> Dict[str, str]:  # type: ignore[override]
    excerpt = _law_excerpt_1_8_23(ref, 200)
    return {
        'name': str(ref.get('name') or ref.get('law_name') or '').strip(),
        'ref': str(ref.get('ref') or ref.get('section') or '').strip(),
        'law_text': excerpt,
        'excerpt': excerpt,
    }


def _refs_to_text(refs: list[Dict[str, str]]) -> str:  # type: ignore[override]
    chunks: list[str] = []
    for ref in refs or []:
        head = _legal_ref_head_1_8_23(ref)
        excerpt = str(ref.get('excerpt') or ref.get('law_text') or '').strip()
        if head and excerpt:
            chunks.append(f'{head}: {excerpt}')
        elif head:
            chunks.append(head)
        elif excerpt:
            chunks.append(excerpt)
    return '\n'.join(chunks).strip()


def _offence_fact_line_1_8_25(block: Dict[str, Any], idx: int) -> str:  # type: ignore[override]
    title = _title_shortener_1_8_25(_offence_title_from_block_1_8_23(block))
    details = _strip_position_phrases_1_8_24(_strip_inline_seizure_text_1_8_24(block.get('details') or block.get('allegation') or ''))
    details = re.sub(r'^Mulig\s+brudd\s+på\s+[^:]+:\s*', '', details, flags=re.IGNORECASE).strip()
    details = re.sub(r'\bkontrollposisjon[^.]*\.?', '', details, flags=re.IGNORECASE).strip()
    details = _dedupe_fact_fragments_1_8_27(details)
    if details and _norm_key_1_8_30(title) not in _norm_key_1_8_30(details):
        text = f'{title}: {details}'
    else:
        text = title
    return f'{idx}. {_shorten_sentence_1_8_21(_sentence_1_7(text), 260)}'


def _build_short_complaint(case_row: Dict[str, Any], findings: list[Dict[str, Any]], sources: list[Dict[str, Any]]) -> str:  # type: ignore[override]
    override = str(case_row.get('complaint_override') or '').strip()
    if override:
        return _clean_standard_text_1_7(_strip_doc_heading_1_8_23(override), case_row)
    subject = _subject_name_1_8_30(case_row)
    when = _case_when_1_8_30(case_row)
    place = _case_place_1_8_30(case_row)
    unit = _case_vessel_unit_1_8_30(case_row)
    topic = _topic_narrative_1_8_30(case_row)
    offences = _offence_blocks(case_row, findings)
    titles = _offence_titles_1_8_25(case_row, findings)
    avvik_rows = _avvik_rows_1_8_30(findings)

    if not offences and not avvik_rows:
        return _clean_standard_text_1_7(
            f'Det ble gjennomført fiskerikontroll {when} ved {place}. Det er ikke registrert avvik som danner grunnlag for anmeldelse i kontrollpunktene på tidspunktet for utkastet.',
            case_row,
        )

    lines: list[str] = []
    if len(titles) <= 1:
        title = titles[0] if titles else (avvik_rows[0][0] if avvik_rows else 'mulig overtredelse av fiskeriregelverket')
        lines.append(f'Med dette anmeldes {subject} for {title.lower()} avdekket {when} ved {place}.')
    else:
        lines.append(f'Med dette anmeldes {subject} for følgende forhold avdekket {when} ved {place}:')
        for idx, title in enumerate(titles, start=1):
            lines.append(f'{idx}. {title}.')
    lines.append('')
    intro = f'Forholdene ble avdekket da {unit} gjennomførte fiskerioppsyn/kontroll med {topic}.' if len(titles) > 1 else f'Forholdet ble avdekket da {unit} gjennomførte fiskerioppsyn/kontroll med {topic}.'
    if _normal_case_basis_1_8_22(case_row.get('case_basis')) == 'tips':
        intro += ' Kontrollen ble gjennomført på bakgrunn av mottatte tips/opplysninger. De faktiske forholdene bygger på patruljens egne observasjoner og dokumentasjon sikret under kontrollen.'
    lines.append(intro)
    lines.append('')
    lines.append('Kort faktumbeskrivelse:')
    if offences:
        for idx, block in enumerate(offences, start=1):
            lines.append(_offence_fact_line_1_8_25(block, idx))
    else:
        for idx, (title, note) in enumerate(avvik_rows, start=1):
            text = title + (': ' + note if note else '')
            lines.append(f'{idx}. {_sentence_1_7(_shorten_sentence_1_8_21(text, 260))}')
    lines.append('')
    lines.append(f'Forholdet kan etter sin art være relevant for vurdering etter {_legal_head_list_1_8_30(case_row, findings)}. Endelig rettslig vurdering tilligger påtalemyndigheten.')
    lines.append('For nærmere detaljer om faktiske observasjoner, redskap/beslag og sikret bildedokumentasjon vises det til sakens ' + _evidence_doc_phrase_1_8_26(case_row) + '.')
    return _clean_standard_text_1_7('\n'.join(lines).strip(), case_row)


def _control_execution_sentence_1_8_30(case_row: Dict[str, Any], findings: list[Dict[str, Any]]) -> str:
    topic = _topic_narrative_1_8_30(case_row)
    gear = _first_clean_1_7(case_row.get('gear_type'))
    if gear:
        return f'Kontrollen ble gjennomført ved at aktuelt redskap/kontrollobjekt ble kontrollert opp mot registrerte kontrollpunkter for {topic}.'
    return f'Kontrollen ble gjennomført opp mot registrerte kontrollpunkter for {topic}.'


def _build_own_report(case_row: Dict[str, Any], findings: list[Dict[str, Any]]) -> str:  # type: ignore[override]
    override = str(case_row.get('own_report_override') or '').strip()
    if override:
        return _clean_standard_text_1_7(_strip_doc_heading_1_8_23(override), case_row)
    investigator = _first_clean_1_7(case_row.get('investigator_name'), 'rapportskriver')
    unit = _case_vessel_unit_1_8_30(case_row)
    when = _case_when_1_8_30(case_row)
    place = _case_place_1_8_30(case_row)
    topic = _topic_narrative_1_8_30(case_row)
    crew = _crew_text(case_row)
    subject = _subject_name_1_8_30(case_row, fallback='')
    paragraphs: list[str] = []
    paragraphs.append(f'Den {when} gjennomførte {unit} fiskerioppsyn ved {place}. Jeg, {investigator}, deltok i kontrollen. Kontrolltema var {topic}.')
    if crew and crew != '-':
        paragraphs.append(f'Øvrig personell/observatører som deltok i kontrollen: {crew}.')
    paragraphs.append(_own_report_basis_1_8_25(case_row, findings))
    paragraphs.append(_control_execution_sentence_1_8_30(case_row, findings))
    if subject:
        paragraphs.append(f'Kontrollobjekt/ansvarlig registrert i saken: {subject}.')
    avvik_rows = _avvik_rows_1_8_30(findings)
    if avvik_rows:
        paragraphs.append('Kontrollør registrerte følgende avvik:\n' + '\n'.join(_short_avvik_lines_1_8_24(findings, limit=250)))
    else:
        paragraphs.append('Det er ikke registrert avvik i kontrollpunktene på tidspunktet rapporten ble laget.')
    if _seizure_rows_1_7(case_row, findings):
        paragraphs.append('Redskap/beslag er ført i egen beslagsrapport. Posisjon for det enkelte beslag fremgår der. Relevante fotografier og kartutsnitt fremgår av illustrasjonsmappe/fotomappe.')
    else:
        paragraphs.append('Relevante fotografier og kartutsnitt fremgår av illustrasjonsmappe/fotomappe der dette er registrert.')
    if _has_interview_report_content_1_8_21(case_row):
        paragraphs.append('Gjennomført avhør/forklaring er protokollert i egen avhørsrapport.')
    notes = _strip_position_phrases_1_8_24(_strip_inline_seizure_text_1_8_24(_strip_generated_report_noise_1_8_21(case_row.get('notes'))))
    if notes:
        paragraphs.append('Kontrollørs merknad: ' + _shorten_sentence_1_8_21(notes, 340))
    text = '\n\n'.join(_dedupe_report_lines_1_8_30([p for p in paragraphs if p]))
    for bad in _BAD_REPORT_PHRASES_1_8_30:
        text = re.sub(r'\b' + re.escape(bad) + r'\b', '', text, flags=re.IGNORECASE)
    return _clean_standard_text_1_7(text.strip(), case_row)


def _build_interview_report(case_row: Dict[str, Any]) -> str:  # type: ignore[override]
    if not _has_interview_report_content_1_8_21(case_row):
        return ''
    override = str(case_row.get('interview_report_override') or '').strip()
    if override:
        return _clean_standard_text_1_7(_strip_doc_heading_1_8_23(override), case_row)
    entries = _conducted_interview_entries_1_8_21(case_row)
    lines: list[str] = []
    used = 0
    for entry in entries:
        body = _interview_entry_body_1_8_21(entry)
        if not body:
            continue
        used += 1
        name = _first_clean_1_7(entry.get('name'), case_row.get('suspect_name'), f'avhørt person {used}')
        role = _first_clean_1_7(entry.get('role'), 'mistenkt/siktet')
        method = _first_clean_1_7(entry.get('method'), 'ikke oppgitt')
        place = _first_clean_1_7(entry.get('place'), _case_place_1_8_30(case_row))
        start = _fmt_datetime(entry.get('start') or case_row.get('start_time'))
        end = _fmt_datetime(entry.get('end') or case_row.get('end_time'))
        if used > 1:
            lines.append('')
        lines.append(f'Avhør av {name}')
        lines.append(f'{name} ble avhørt som {role}. Avhøret ble gjennomført {start} ved {place}. Metode: {method}.')
        lines.append('Før forklaring ble gitt, ble avhørte gjort kjent med hva saken gjelder, retten til ikke å forklare seg og retten til å la seg bistå av forsvarer.')
        lines.append('Forklaring/sammendrag:')
        lines.append(body.strip())
        if end and end != '-':
            lines.append(f'Avhøret ble avsluttet {end}.')
    return _clean_standard_text_1_7('\n'.join(lines).strip(), case_row) if used else ''


def _image_caption_base_1_8_24(item: Dict[str, Any], idx: int) -> str:  # type: ignore[override]
    raw = _first_clean_1_7(item.get('caption'), item.get('original_filename'), item.get('filename'), f'foto {idx}')
    raw = _strip_position_phrases_1_8_24(_strip_inline_seizure_text_1_8_24(raw))
    raw = re.sub(r'\s+', ' ', raw).strip(' .')
    if not raw:
        raw = f'foto {idx}'
    low = raw.lower()
    if low.startswith('bilde viser'):
        return _sentence_1_7(raw[0].upper() + raw[1:])
    if low.startswith('foto viser'):
        raw = raw[5:].strip()
    return _sentence_1_7('Bilde viser ' + raw[0].lower() + raw[1:])


def _build_illustration_texts(evidence_rows: list[Dict[str, Any]]) -> list[str]:  # type: ignore[override]
    if not evidence_rows:
        return ['Ingen illustrasjoner registrert i saken.']
    texts: list[str] = []
    for idx, item in enumerate(evidence_rows, start=1):
        finding_key = str(item.get('finding_key') or '').strip().lower()
        caption = str(item.get('caption') or '').strip()
        filename = str(item.get('filename') or item.get('generated_path') or '').strip().lower()
        if finding_key == 'oversiktskart':
            if '2km' in filename or '5km' in filename or caption.lower().startswith('detaljert'):
                texts.append('Detaljert kartutsnitt med registrert avviks-/beslagsposisjon.')
            else:
                texts.append('Oversiktskart av kontrollposisjon.')
            continue
        base = _image_caption_base_1_8_24(item, idx).rstrip('.')
        extras: list[str] = []
        seizure = _first_clean_1_7(item.get('seizure_ref'))
        reason = _strip_position_phrases_1_8_24(_strip_inline_seizure_text_1_8_24(_first_clean_1_7(item.get('violation_reason'))))
        if seizure:
            extras.append(f'beslag {seizure}')
        if reason:
            extras.append('avvik: ' + _shorten_sentence_1_8_21(reason, 75).rstrip('.'))
        if extras:
            base += ' - ' + ' - '.join(extras)
        texts.append(_shorten_sentence_1_8_21(_sentence_1_7(base), 170))
    return texts


def build_summary(case_row: Dict[str, Any], findings: list[Dict[str, Any]]) -> str:  # type: ignore[override]
    if (case_row.get('summary') or '').strip():
        return _clean_standard_text_1_7(case_row.get('summary'), case_row)
    when = _case_when_1_8_30(case_row)
    place = _case_place_1_8_30(case_row)
    lines: list[str] = [
        f'Kontrollen ble gjennomført {when} ved {place}. Kontrolltema var {_topic_narrative_1_8_30(case_row)}.',
        _own_report_basis_1_8_25(case_row, findings),
    ]
    if _avvik_1_7(findings):
        lines.append('Registrerte avvik:')
        lines.extend(_short_avvik_lines_1_8_24(findings, limit=170))
        lines.append('Dokumentasjon fremgår av egenrapport, beslagsrapport og illustrasjonsmappe/fotomappe. Avhørsrapport tas bare med når avhør er merket gjennomført.')
    else:
        lines.append('Det er ikke registrert avvik i kontrollpunktene.')
    return _clean_standard_text_1_7('\n'.join(lines), case_row)


def build_text_drafts(case_row: Dict[str, Any], findings: list[Dict[str, Any]]) -> Dict[str, str]:  # type: ignore[override]
    return {
        'summary': build_summary(case_row, findings),
        'basis_details': build_control_reason(case_row, findings),
        'notes': '',
        'complaint_preview': _build_short_complaint(case_row, findings, _safe_sources(case_row)),
        'source_label': 'straffesaksmal 1.8.30',
    }

# 1.8.30a: justeringer etter test - behold avsnitt/linjeskift og fjern koordinater i bildetekster.

def _purpose_focus_1_8_30(case_row: Dict[str, Any], findings: list[Dict[str, Any]] | None = None) -> str:  # type: ignore[override]
    species = str(case_row.get('species') or case_row.get('fishery_type') or '').lower()
    gear = str(case_row.get('gear_type') or '').lower()
    keys = {str((item or {}).get('key') or '').lower() for item in (findings or []) if isinstance(item, dict)}
    titles = ' '.join(_finding_title_1_8_27(item).lower() for item in (findings or []) if isinstance(item, dict))
    focus: list[str] = []
    def add(text: str) -> None:
        if text and text not in focus:
            focus.append(text)
    if 'hummer' in species or 'hummer' in titles or any(k.startswith('hummer') for k in keys):
        add('deltakelse/deltakernummer')
        add('merking av vak/blåse og redskap')
        add('teinenes antall og utforming')
        if any(word in titles for word in ['flukt', 'rømningshull', 'råtnetråd']) or not findings:
            add('fluktåpninger/rømningshull')
        if any(word in titles for word in ['lengde', 'minstemål', 'maksimalmål']) or not findings:
            add('lengdemål')
        add('fangst/oppbevaring')
        add('relevante periode- og områdebestemmelser')
    elif any(word in gear for word in ['teine', 'ruse', 'garn', 'lenke', 'line']):
        add('merking av vak/blåse og redskap')
        add('redskapets utforming og plassering')
        add('fangst/oppbevaring')
        add('ansvarlig bruker/eier')
        add('relevante områdebestemmelser')
    else:
        add('redskap, merking og fangst/oppbevaring')
        add('posisjon og relevante områdebestemmelser')
    return _natural_join(focus)


def _strip_coords_1_8_30(value: Any) -> str:
    text = str(value or '')
    text = re.sub(r'\b(?:posisjon|kontrollposisjon|start|slutt)\s*[:\-]?\s*[NS]\s*\d+[^.;\n]*(?:[ØEWA]\s*\d+[^.;\n]*)?', '', text, flags=re.IGNORECASE)
    text = re.sub(r'\b[NS]\s*\d{1,2}\s*[°º]?\s*\d{1,2}[^.;\n]{0,35}\s*[ØEWA]\s*\d{1,3}\s*[°º]?\s*\d{1,2}[^.;\n]{0,20}', '', text, flags=re.IGNORECASE)
    text = re.sub(r'\s+', ' ', text).strip(' ;,.-')
    return text


def _finding_note_for_report_1_8_30(item: Dict[str, Any], title: str) -> str:  # type: ignore[override]
    note = _finding_note_for_report_1_8_27(item, title)
    note = _strip_coords_1_8_30(_strip_position_phrases_1_8_24(_strip_inline_seizure_text_1_8_24(note)))
    note = re.sub(r'^' + re.escape(str(title or '')) + r'[:.\s-]*', '', note, flags=re.IGNORECASE).strip()
    note = _dedupe_fact_fragments_1_8_27(note)
    return _shorten_sentence_1_8_21(note, 220).rstrip('.')


def _dedupe_paragraphs_1_8_30(paragraphs: list[str]) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for part in paragraphs:
        text = str(part or '').strip()
        if not text:
            continue
        key = _norm_key_1_8_30(text)
        if key in seen:
            continue
        seen.add(key)
        out.append(text)
    return out


def _build_short_complaint(case_row: Dict[str, Any], findings: list[Dict[str, Any]], sources: list[Dict[str, Any]]) -> str:  # type: ignore[override]
    override = str(case_row.get('complaint_override') or '').strip()
    if override:
        return _clean_standard_text_1_7(_strip_doc_heading_1_8_23(override), case_row)
    subject = _subject_name_1_8_30(case_row)
    when = _case_when_1_8_30(case_row)
    place = _case_place_1_8_30(case_row)
    unit = _case_vessel_unit_1_8_30(case_row)
    topic = _topic_narrative_1_8_30(case_row)
    offences = _offence_blocks(case_row, findings)
    titles = _offence_titles_1_8_25(case_row, findings)
    avvik_rows = _avvik_rows_1_8_30(findings)
    count = max(len(titles), len(avvik_rows), len(offences))
    if not offences and not avvik_rows:
        return _clean_standard_text_1_7(
            f'Det ble gjennomført fiskerikontroll {when} ved {place}. Det er ikke registrert avvik som danner grunnlag for anmeldelse i kontrollpunktene på tidspunktet for utkastet.',
            case_row,
        )
    lines: list[str] = []
    if count <= 1:
        title = titles[0] if titles else (avvik_rows[0][0] if avvik_rows else 'mulig overtredelse av fiskeriregelverket')
        lines.append(f'Med dette anmeldes {subject} for {title.lower()} avdekket {when} ved {place}.')
    else:
        lines.append(f'Med dette anmeldes {subject} for følgende forhold avdekket {when} ved {place}:')
        for idx, title in enumerate(titles or [row[0] for row in avvik_rows], start=1):
            lines.append(f'{idx}. {title}.')
    lines.append('')
    intro = f'Forholdene ble avdekket da {unit} gjennomførte fiskerioppsyn/kontroll med {topic}.' if count > 1 else f'Forholdet ble avdekket da {unit} gjennomførte fiskerioppsyn/kontroll med {topic}.'
    if _normal_case_basis_1_8_22(case_row.get('case_basis')) == 'tips':
        intro += ' Kontrollen ble gjennomført på bakgrunn av mottatte tips/opplysninger. De faktiske forholdene bygger på patruljens egne observasjoner og dokumentasjon sikret under kontrollen.'
    lines.append(intro)
    lines.append('')
    lines.append('Kort faktumbeskrivelse:')
    if offences:
        for idx, block in enumerate(offences, start=1):
            lines.append(_offence_fact_line_1_8_25(block, idx))
    else:
        for idx, (title, note) in enumerate(avvik_rows, start=1):
            text = title + (': ' + note if note else '')
            lines.append(f'{idx}. {_sentence_1_7(_shorten_sentence_1_8_21(text, 260))}')
    lines.append('')
    if count > 1:
        lines.append(f'Forholdene kan etter sin art være relevante for vurdering etter {_legal_head_list_1_8_30(case_row, findings)}. Endelig rettslig vurdering tilligger påtalemyndigheten.')
    else:
        lines.append(f'Forholdet kan etter sin art være relevant for vurdering etter {_legal_head_list_1_8_30(case_row, findings)}. Endelig rettslig vurdering tilligger påtalemyndigheten.')
    lines.append('For nærmere detaljer om faktiske observasjoner, redskap/beslag og sikret bildedokumentasjon vises det til sakens ' + _evidence_doc_phrase_1_8_26(case_row) + '.')
    return _clean_standard_text_1_7('\n'.join(lines).strip(), case_row)


def _build_own_report(case_row: Dict[str, Any], findings: list[Dict[str, Any]]) -> str:  # type: ignore[override]
    override = str(case_row.get('own_report_override') or '').strip()
    if override:
        return _clean_standard_text_1_7(_strip_doc_heading_1_8_23(override), case_row)
    investigator = _first_clean_1_7(case_row.get('investigator_name'), 'rapportskriver')
    unit = _case_vessel_unit_1_8_30(case_row)
    when = _case_when_1_8_30(case_row)
    place = _case_place_1_8_30(case_row)
    topic = _topic_narrative_1_8_30(case_row)
    crew = _crew_text(case_row)
    subject = _subject_name_1_8_30(case_row, fallback='')
    paragraphs: list[str] = []
    paragraphs.append(f'Den {when} gjennomførte {unit} fiskerioppsyn ved {place}. Jeg, {investigator}, deltok i kontrollen. Kontrolltema var {topic}.')
    if crew and crew != '-':
        paragraphs.append(f'Øvrig personell/observatører som deltok i kontrollen: {crew}.')
    paragraphs.append(_own_report_basis_1_8_25(case_row, findings))
    paragraphs.append(_control_execution_sentence_1_8_30(case_row, findings))
    if subject:
        paragraphs.append(f'Kontrollobjekt/ansvarlig registrert i saken: {subject}.')
    avvik_rows = _avvik_rows_1_8_30(findings)
    if avvik_rows:
        paragraphs.append('Kontrollør registrerte følgende avvik:\n' + '\n'.join(_short_avvik_lines_1_8_24(findings, limit=250)))
    else:
        paragraphs.append('Det er ikke registrert avvik i kontrollpunktene på tidspunktet rapporten ble laget.')
    if _seizure_rows_1_7(case_row, findings):
        paragraphs.append('Redskap/beslag er ført i egen beslagsrapport. Posisjon for det enkelte beslag fremgår der. Relevante fotografier og kartutsnitt fremgår av illustrasjonsmappe/fotomappe.')
    else:
        paragraphs.append('Relevante fotografier og kartutsnitt fremgår av illustrasjonsmappe/fotomappe der dette er registrert.')
    if _has_interview_report_content_1_8_21(case_row):
        paragraphs.append('Gjennomført avhør/forklaring er protokollert i egen avhørsrapport.')
    notes = _strip_coords_1_8_30(_strip_position_phrases_1_8_24(_strip_inline_seizure_text_1_8_24(_strip_generated_report_noise_1_8_21(case_row.get('notes')))))
    if notes:
        paragraphs.append('Kontrollørs merknad: ' + _shorten_sentence_1_8_21(notes, 340))
    text = '\n\n'.join(_dedupe_paragraphs_1_8_30(paragraphs))
    for bad in _BAD_REPORT_PHRASES_1_8_30:
        text = re.sub(r'\b' + re.escape(bad) + r'\b', '', text, flags=re.IGNORECASE)
    return _clean_standard_text_1_7(text.strip(), case_row)


def _image_caption_base_1_8_24(item: Dict[str, Any], idx: int) -> str:  # type: ignore[override]
    raw = _first_clean_1_7(item.get('caption'), item.get('original_filename'), item.get('filename'), f'foto {idx}')
    raw = _strip_coords_1_8_30(_strip_position_phrases_1_8_24(_strip_inline_seizure_text_1_8_24(raw)))
    raw = re.sub(r'\s+', ' ', raw).strip(' .')
    if not raw:
        raw = f'foto {idx}'
    low = raw.lower()
    if low.startswith('bilde viser'):
        return _sentence_1_7(raw[0].upper() + raw[1:])
    if low.startswith('foto viser'):
        raw = raw[5:].strip()
    return _sentence_1_7('Bilde viser ' + raw[0].lower() + raw[1:])
