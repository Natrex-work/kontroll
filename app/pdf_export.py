from __future__ import annotations

import html
import io
import json
import math
import re
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
    'patruljeobservasjon': 'Patruljeobservasjon',
    'tips': 'Tips',
    'anmeldelse': 'Anmeldelse',
    'annen_omstendighet': 'Annen omstendighet',
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
        ('#24527b', 'Radius ca. 50 km'),
        ('#c1121f', 'Kontrollposisjon'),
        ('#f4a261', 'Frednings-/reguleringsområde'),
        ('#e63946', 'Stengt / forbudsområde'),
    ]
    for idx, (color, label) in enumerate(legend):
        y = legend_y + 40 + idx * 20
        draw.rectangle((legend_x + 18, y + 4, legend_x + 34, y + 14), fill=color, outline=color)
        draw.text((legend_x + 44, y), label, fill='#33485c')

    outpath = output_dir / f"{str(case_row.get('case_number') or 'sak').replace(' ', '_')}_overview_map.png"
    img.save(outpath)
    return {
        'filename': outpath.name,
        'original_filename': outpath.name,
        'caption': 'Oversiktskart kontrollposisjon (ca. 50 km radius)',
        'finding_key': 'oversiktskart',
        'law_text': str(case_row.get('area_status') or case_row.get('area_name') or '').strip(),
        'violation_reason': 'Automatisk generert kartoversikt med kontrollposisjon og nærliggende regulerte områder.',
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
    if fetched == 0:
        return None

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
    legend = [((36,82,123), 'Radius ca. 50 km'), ((193,18,31), 'Kontrollposisjon'), ((244,162,97), 'Frednings-/reguleringsområde'), ((230,57,70), 'Stengt / forbudsområde')]
    for idx, (col, label) in enumerate(legend):
        y = 132 + idx * 18
        draw2.rectangle((904, y + 4, 918, y + 14), fill=col + (255,), outline=col + (255,))
        draw2.text((926, y), label, fill=(51,72,92,255))
    draw2.rounded_rectangle((18, 776, 470, 804), radius=10, fill=(255,255,255,225), outline=(180,194,209,255))
    draw2.text((30, 784), 'Kartbakgrunn © OpenStreetMap-bidragsytere', fill=(66, 82, 100, 255))

    outpath = output_dir / f"{str(case_row.get('case_number') or 'sak').replace(' ', '_')}_overview_map.png"
    out.convert('RGB').save(outpath)
    return {
        'filename': outpath.name,
        'original_filename': outpath.name,
        'caption': 'Oversiktskart kontrollposisjon (ca. 50 km radius)',
        'finding_key': 'oversiktskart',
        'law_text': str(case_row.get('area_status') or case_row.get('area_name') or '').strip(),
        'violation_reason': 'Automatisk generert kartoversikt med kontrollposisjon, stedsnavn og nærliggende regulerte områder.',
        'created_at': datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC'),
        'generated_path': str(outpath),
        'preview_url': (f"/cases/{case_row.get('id')}/generated/{outpath.name}" if case_row.get('id') is not None else None),
    }


def _generate_overview_map_image(case_row: Dict[str, Any], output_dir: Path, radius_km: float = 50.0) -> dict[str, Any] | None:
    tile_map = _generate_tile_overview_map_image(case_row, output_dir, radius_km=radius_km)
    if tile_map is not None:
        return tile_map
    return _generate_vector_overview_map_image(case_row, output_dir, radius_km=radius_km)


def _styles():
    styles = getSampleStyleSheet()
    styles.add(ParagraphStyle(name='Small', fontSize=8, leading=10))
    styles.add(ParagraphStyle(name='Section', fontSize=15, leading=18, spaceAfter=8, spaceBefore=8))
    styles.add(ParagraphStyle(name='BodyTall', fontSize=10, leading=14, spaceBefore=2, spaceAfter=6))
    styles.add(ParagraphStyle(name='MonoSmall', fontName='Courier', fontSize=8, leading=10))
    styles.add(ParagraphStyle(name='MetaTitle', fontSize=11, leading=13, textColor=colors.HexColor('#0f2740'), spaceBefore=6, spaceAfter=4))
    return styles


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
        note = str(row.get('note') or '').strip()
        bit = f'{ref}: {length} cm' if length else ref
        if delta_text:
            bit += f' – {delta_text}'
        extras = []
        if photo:
            extras.append(f'bildereferanse {photo}')
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
    if start:
        parts.append(f'Startposisjon: {start}')
    if end:
        parts.append(f'Sluttposisjon: {end}')
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
    area_name = str(case_row.get('area_name') or case_row.get('area_status') or 'aktuelt område').strip()
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
    area_name = _clean_generated_phrase(_area_name_value(case_row) or item.get('area_name') or item.get('name') or item.get('label') or 'aktuelt område')
    area_status = _clean_generated_phrase(_area_status_value(case_row) or item.get('area_status') or item.get('status') or '')
    gear_text = _clean_generated_phrase(case_row.get('gear_type') or item.get('gear_type') or 'redskapet') or 'redskapet'

    if clean:
        clean = re.sub(r'^I oppgitt posisjon ble .*? kontrollert i [^.]+\.?\s*', '', clean, flags=re.IGNORECASE)
        clean = re.sub(r'^Posisjonen ligger i [^.]+\.?\s*', '', clean, flags=re.IGNORECASE)
        clean = re.sub(r'^Valgt redskap \(([^)]+)\) er ikke blant redskapene som er tillatt i området\.?', r'Følgende redskap er ikke tillatt i dette området: .', clean, flags=re.IGNORECASE)
        clean = re.sub(r'^Valgt redskap \(([^)]+)\) må vurderes som ulovlig eller særskilt regulert i området\.?', r'Følgende redskap er forbudt eller særskilt regulert i dette området: .', clean, flags=re.IGNORECASE)
        clean = re.sub(r'^Dette redskapet er ikke tillatt i hummerfredningsområdet\.?', f'Følgende redskap er ikke tillatt i hummerfredningsområdet: {gear_text.lower()}.', clean, flags=re.IGNORECASE)
        clean = re.sub(r'^Området er registrert som ([^.]+)\.?', r'Området er registrert som .', clean, flags=re.IGNORECASE)
        clean = re.sub(r'^For dette området gjaldt følgende reguleringer og begrensninger:\s*', '', clean, flags=re.IGNORECASE)
        clean = _sentenceize(clean)

    intro = f'I oppgitt posisjon ble {gear_text.lower()} observert og kontrollert'
    if area_name:
        intro += f' der det befant seg i området {area_name}'
        if area_status:
            intro += f' ({area_status})'
    intro = _sentenceize(intro)
    if clean:
        return f"{intro} For dette området gjaldt følgende reguleringer og begrensninger: {clean.rstrip('.')} .".replace(' .', '.')
    return f"{intro} For dette området gjaldt følgende reguleringer og begrensninger."


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

def _basis_opening_phrase(case_row: Dict[str, Any]) -> str:
    basis = (case_row.get('case_basis') or 'patruljeobservasjon').strip()
    raw_source = str(case_row.get('basis_source_name') or '').strip()
    normalized = raw_source.lower()
    default_sources = {
        '',
        'kystvaktpatrulje',
        'kv patrulje',
        'kystvakten lettbåt',
        'kystvaktens lettbåt',
    }
    if basis not in {'tips', 'anmeldelse'} and normalized not in default_sources:
        return f'Det ble fra lettbåt fra {raw_source} gjennomført'
    return 'Det ble fra Kystvakten lettbåt gjennomført'



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
        return f'{opening} kontroll på grunnlag av annen omstendighet rettet mot {theme.lower()}{area_text}. Formålet var å avklare faktum, identifisere involverte og kontrollere relevante lovkrav.'
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
        bits.append(f"posisjon {_fmt_value(case_row.get('latitude'))}, {_fmt_value(case_row.get('longitude'))}")
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
            lines.append(f"Opplysningene ble registrert med kilde: {str(case_row.get('basis_source_name')).strip()}.")
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
            texts.append(f"Illustrasjon {idx}: Oversiktskart med kontrollposisjon og cirka 50 km radius. {reason}".strip())
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
    overview_item = _generate_overview_map_image(case_row, GENERATED_DIR)
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
            ('Vitne', _fmt_value(case_row.get('witness_name'))),
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
            ('Kilde / tipsgiver', _fmt_value(case_row.get('basis_source_name'))),
            ('Grunnlagsdetaljer', _fmt_value(case_row.get('basis_details'))),
            ('Status', _fmt_value(case_row.get('status'))),
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
        author=case_row.get('investigator_name') or 'KV Kontroll',
    )
    story: List[Any] = []

    story.append(Paragraph('Kystvakt - anmeldelsespakke', styles['Title']))
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


def _draw_template(c: rl_canvas.Canvas, template_name: str) -> None:
    path = _TEMPLATE_DIR / template_name
    if path.exists():
        c.drawImage(ImageReader(str(path)), 0, 0, width=_PAGE_W, height=_PAGE_H, preserveAspectRatio=False, mask='auto')


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
    _draw_text_px(c, 'KV NORNEN', 814, 262, 1120, 294, font_name='Helvetica', font_size=8.5)


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
    cx = l
    for idx, head in enumerate(headers):
        _draw_label_value(c, x_positions[idx], t, x_positions[idx + 1], t + row_h, head, '', value_size=font_size)
    y = t + row_h
    for row in rows:
        for idx, cell in enumerate(row):
            _draw_label_value(c, x_positions[idx], y, x_positions[idx + 1], y + row_h, '', cell, value_size=font_size)
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
    y = _person_box(c, 'Anmelder', y, _fmt_value(case_row.get('complainant_name') or 'Kystvakten'), 'Havnegata 31', '8400 Sortland', '76 11 22 22', relation='Anmelder', extra_left='Kystvakten, Havnegata 31, 8400 Sortland', extra_mid='-', extra_right='986 147 756')
    y = _draw_lines_block(c, 'Etterforskere', y, [_fmt_value(case_row.get('investigator_name')) + ', Havnegata 31, 8400 Sortland, 76 11 22 22'])
    witness_lines = []
    crew = [str((x or {}).get('name') or '').strip() for x in _safe_list_json(case_row.get('crew_json')) if str((x or {}).get('name') or '').strip()]
    if case_row.get('witness_name'):
        witness_lines.append(f"{case_row.get('witness_name')}, Havnegata 31, 8400 Sortland, 76 11 22 22")
    witness_lines.extend([name for name in crew if name != case_row.get('witness_name')])
    y = _draw_lines_block(c, 'Vitner', y, witness_lines or ['-'])
    externals = [str(x).strip() for x in _safe_list_json(case_row.get('external_actors_json')) if str(x).strip()]
    y = _draw_lines_block(c, 'Andre involverte', y, externals or ['-'])
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
            _draw_section_caption(c, 118, 1554, 1128, 1616, 'Signatur')
            _draw_text_px(c, _fmt_value(case_row.get('complainant_signature') or case_row.get('complainant_name') or case_row.get('investigator_name')), 124, 1572, 400, 1608, font_name='Helvetica', font_size=9.0)


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


def _draw_seizure_page(c: rl_canvas.Canvas, case_row: Dict[str, Any], packet: Dict[str, Any]) -> None:
    _draw_template(c, 'page-07.png')
    _header_meta_box(c, case_row, '05', 1, 1)
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
    _draw_label_value(c, 808, y + 96, 1128, y + 140, 'Tjenestested', 'KV NORNEN')
    _draw_label_value(c, 118, y + 140, 1128, y + 176, 'Vitner', _fmt_value(case_row.get('witness_name')))
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
    _draw_label_value(c, 623, 1538, 1128, 1604, 'Vitnets underskrift', _fmt_value(case_row.get('witness_signature') or case_row.get('witness_name')))


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


def _draw_illustration_pages(c: rl_canvas.Canvas, case_row: Dict[str, Any], packet: Dict[str, Any]) -> None:
    evidence = list(packet.get('evidence') or [])
    if not evidence:
        evidence = [{'caption': 'Ingen illustrasjoner registrert', 'filename': '', 'generated_path': ''}]
    chunks = [evidence[i:i + 2] for i in range(0, len(evidence), 2)]
    total = len(chunks)
    for idx, chunk in enumerate(chunks, start=1):
        _draw_template(c, 'page-08.png' if idx == 1 else 'page-09.png')
        _header_meta_box(c, case_row, '06', idx, total)
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
    c.setAuthor(case_row.get('investigator_name') or 'KV Kontroll')

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


def _draw_seizure_page(c: rl_canvas.Canvas, case_row: Dict[str, Any], packet: Dict[str, Any]) -> None:  # type: ignore[override]
    _draw_template(c, 'page-07.png')
    _header_meta_box(c, case_row, '05', 1, 1)
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
    _draw_label_value(c, 808, y + 96, 1128, y + 140, 'Tjenestested', 'KV NORNEN')
    _draw_label_value(c, 118, y + 140, 1128, y + 176, 'Vitner', _fmt_value(case_row.get('witness_name')))
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
    _draw_label_value(c, 623, 1538, 1128, 1604, 'Vitnets underskrift', _fmt_value(case_row.get('witness_signature') or case_row.get('witness_name')))


def _draw_illustration_pages(c: rl_canvas.Canvas, case_row: Dict[str, Any], packet: Dict[str, Any]) -> None:  # type: ignore[override]
    evidence = list(packet.get('evidence') or []) or [{'caption': 'Ingen illustrasjoner registrert', 'filename': '', 'generated_path': ''}]
    chunks = [evidence[i:i + 2] for i in range(0, len(evidence), 2)]
    total = len(chunks)
    for idx, chunk in enumerate(chunks, start=1):
        _draw_template(c, 'page-08.png' if idx == 1 else 'page-09.png')
        _header_meta_box(c, case_row, '06', idx, total)
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
    c.setAuthor(case_row.get('investigator_name') or 'KV Kontroll')
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
    canvas.drawString(doc.leftMargin, A4[1] - 1.2 * cm, 'POLITI / KYSTVAKTEN')
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
