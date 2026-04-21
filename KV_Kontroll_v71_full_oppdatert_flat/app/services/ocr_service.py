from __future__ import annotations

from io import BytesIO
import re
from typing import Any

from PIL import Image, ImageEnhance, ImageOps
import pytesseract
from pytesseract import TesseractError, TesseractNotFoundError

from .. import registry

try:  # pragma: no cover - optional runtime enhancement for HEIC/HEIF support
    from pillow_heif import register_heif_opener
except Exception:  # pragma: no cover
    register_heif_opener = None

if register_heif_opener is not None:  # pragma: no cover - depends on optional package
    try:
        register_heif_opener()
    except Exception:
        pass

TEXT_SCORE_RE = re.compile(r'[A-Za-zÆØÅæøå0-9]')
PHONE_HINT_RE = re.compile(r'(?:\+?47\s*)?\d[\d\s]{6,}')
POST_HINT_RE = re.compile(r'\b\d{4}\s+[A-ZÆØÅa-zæøå][A-Za-zÆØÅæøå\- ]{2,30}\b')
VESSEL_HINT_RE = re.compile(r'\b[A-ZÆØÅ]{1,4}[- ]?[A-ZÆØÅ]{1,4}[- ]?\d{2,4}\b')
NAME_HINT_RE = re.compile(r'\b[A-ZÆØÅ][A-Za-zÆØÅæøå\-]+(?:\s+[A-ZÆØÅ][A-Za-zÆØÅæøå\-]+){1,3}\b')


def _score_text(text: str) -> int:
    cleaned = str(text or '').strip()
    if not cleaned:
        return 0
    alpha_num = len(TEXT_SCORE_RE.findall(cleaned))
    line_count = len([line for line in cleaned.splitlines() if line.strip()])
    score = alpha_num * 4 + min(len(cleaned), 500) + min(line_count, 10) * 6
    if PHONE_HINT_RE.search(cleaned):
        score += 40
    if POST_HINT_RE.search(cleaned):
        score += 35
    if VESSEL_HINT_RE.search(cleaned):
        score += 30
    if len(NAME_HINT_RE.findall(cleaned)) >= 1:
        score += 20
    return score


def _hint_quality(hints: dict[str, str]) -> int:
    score = 0
    if hints.get('vessel_reg'):
        score += 60
    if hints.get('hummer_participant_no'):
        score += 60
    if hints.get('name'):
        score += 60
    if hints.get('address'):
        score += 45
    if hints.get('post_place'):
        score += 40
    if hints.get('phone'):
        score += 50
    return score


def _compose_text_from_hints(hints: dict[str, str], fallback_text: str = '') -> str:
    lines: list[str] = []
    if hints.get('vessel_reg'):
        lines.append(str(hints['vessel_reg']).strip())
    elif hints.get('hummer_participant_no'):
        lines.append(str(hints['hummer_participant_no']).strip())
    if hints.get('name'):
        lines.append(str(hints['name']).strip())
    if hints.get('address'):
        lines.append(str(hints['address']).strip())
    if hints.get('post_place'):
        lines.append(str(hints['post_place']).strip())
    if hints.get('phone'):
        lines.append('TLF. ' + str(hints['phone']).strip())
    if len(lines) >= 3:
        return '\n'.join(line for line in lines if line).strip()
    return str(fallback_text or '').strip()


def _load_image(content: bytes) -> Image.Image:
    image = Image.open(BytesIO(content))
    image.load()
    image = ImageOps.exif_transpose(image)
    if 'A' in image.getbands():
        background = Image.new('RGB', image.size, '#ffffff')
        background.paste(image, mask=image.getchannel('A'))
        image = background
    elif image.mode != 'RGB':
        image = image.convert('RGB')
    max_side = 2200
    min_side = 1200
    width, height = image.size
    longest = max(width, height)
    if longest > max_side:
        image.thumbnail((max_side, max_side), Image.Resampling.LANCZOS)
    elif longest < min_side:
        scale = min(min_side / max(longest, 1), 2.0)
        image = image.resize((max(1, int(round(width * scale))), max(1, int(round(height * scale)))), Image.Resampling.LANCZOS)
    return image


def _pad_label_crop(image: Image.Image, *, pct: float = 0.03) -> Image.Image:
    w, h = image.size
    pad_y = max(8, int(round(h * pct)))
    pad_x = max(8, int(round(w * pct)))
    canvas = Image.new('RGB', (w + pad_x * 2, h + pad_y * 2), '#ffffff')
    canvas.paste(image, (pad_x, pad_y))
    return canvas


def _fallback_center_label_crops(image: Image.Image) -> list[Image.Image]:
    w, h = image.size
    crops: list[Image.Image] = []
    windows = [
        (0.15, 0.10, 0.85, 0.52),
        (0.10, 0.15, 0.90, 0.58),
        (0.18, 0.18, 0.82, 0.62),
    ]
    for left_r, top_r, right_r, bottom_r in windows:
        left = int(round(w * left_r))
        top = int(round(h * top_r))
        right = int(round(w * right_r))
        bottom = int(round(h * bottom_r))
        if right - left < 180 or bottom - top < 70:
            continue
        crops.append(_pad_label_crop(image.crop((left, top, right, bottom))))
    return crops


def _detect_label_crop(image: Image.Image) -> Image.Image | None:
    work = image.copy()
    max_side = 900
    if max(work.size) > max_side:
        work.thumbnail((max_side, max_side), Image.Resampling.LANCZOS)
    w, h = work.size
    search_box = (
        int(round(w * 0.05)),
        int(round(h * 0.05)),
        int(round(w * 0.95)),
        int(round(h * 0.82)),
    )
    search = work.crop(search_box).convert('HSV')
    pix = search.load()
    xs: list[int] = []
    ys: list[int] = []
    sw, sh = search.size
    for y in range(sh):
        for x in range(sw):
            _h, s, v = pix[x, y]
            if v >= 145 and s <= 85:
                xs.append(x)
                ys.append(y)
    if len(xs) < max(250, int(sw * sh * 0.004)):
        return None
    left, top, right, bottom = min(xs), min(ys), max(xs) + 1, max(ys) + 1
    bw = right - left
    bh = bottom - top
    area_ratio = (bw * bh) / max(1.0, sw * sh)
    ratio = max(bw, bh) / max(1.0, min(bw, bh))
    if area_ratio < 0.02 or area_ratio > 0.85 or ratio < 1.1 or ratio > 6.0:
        return None
    # translate back to original coordinates and add generous padding
    scale_x = image.size[0] / max(1.0, w)
    scale_y = image.size[1] / max(1.0, h)
    sx0, sy0, _, _ = search_box
    left = int(round((sx0 + left) * scale_x))
    top = int(round((sy0 + top) * scale_y))
    right = int(round((sx0 + right) * scale_x))
    bottom = int(round((sy0 + bottom) * scale_y))
    pad_x = max(20, int(round((right - left) * 0.08)))
    pad_y = max(14, int(round((bottom - top) * 0.10)))
    left = max(0, left - pad_x)
    top = max(0, top - pad_y)
    right = min(image.size[0], right + pad_x)
    bottom = min(image.size[1], bottom + pad_y)
    if right - left < 180 or bottom - top < 70:
        return None
    crop = image.crop((left, top, right, bottom))
    if crop.height > crop.width:
        crop = crop.rotate(90, expand=True)
    return _pad_label_crop(crop)


def _candidate_label_crops(image: Image.Image) -> list[Image.Image]:
    crops: list[Image.Image] = []
    detected = _detect_label_crop(image)
    if detected is not None:
        crops.append(detected)
    for crop in _fallback_center_label_crops(image):
        if all(crop.size != existing.size for existing in crops):
            crops.append(crop)
    return crops[:3]


def _prepare_variants(image: Image.Image, *, label_mode: bool = False) -> list[tuple[str, Image.Image, str]]:
    rgb = image
    gray = ImageOps.grayscale(image)
    enhanced = ImageOps.autocontrast(gray)
    enhanced = ImageEnhance.Contrast(enhanced).enhance(1.75 if label_mode else 1.55)
    enhanced = ImageEnhance.Sharpness(enhanced).enhance(2.0 if label_mode else 1.6)
    threshold = enhanced.point(lambda px: 255 if px > (148 if label_mode else 156) else 0)
    sparse = ImageEnhance.Contrast(enhanced).enhance(1.9 if label_mode else 1.7)
    medium = ImageEnhance.Contrast(gray).enhance(1.35 if label_mode else 1.25)
    upscaled = enhanced
    longest = max(enhanced.size or (0, 0))
    target = 1800 if label_mode else 1500
    if longest and longest < target:
        factor = min(2.4 if label_mode else 2.0, target / longest)
        upscaled = enhanced.resize((max(1, int(round(enhanced.width * factor))), max(1, int(round(enhanced.height * factor)))), Image.Resampling.LANCZOS)
    base_psm = '6'
    alt_psm = '11'
    line_psm = '6' if label_mode else '7'
    prefix = 'etikett ' if label_mode else ''
    return [
        (prefix + 'original farge', rgb, f'--oem 1 --psm {alt_psm} preserve_interword_spaces=1'),
        (prefix + 'forbedret bilde', enhanced, f'--oem 1 --psm {base_psm} preserve_interword_spaces=1'),
        (prefix + 'oppskalert dokument', upscaled, f'--oem 1 --psm {base_psm} preserve_interword_spaces=1'),
        (prefix + 'høy kontrast', threshold, f'--oem 1 --psm {alt_psm} preserve_interword_spaces=1'),
        (prefix + 'sparsom tekst', sparse, f'--oem 1 --psm {alt_psm} preserve_interword_spaces=1'),
        (prefix + 'enkel linje', medium, f'--oem 1 --psm {line_psm} preserve_interword_spaces=1'),
    ]


def _clean_ocr_text(text: str) -> str:
    raw_lines = re.split(r'[\r\n]+', str(text or ''))
    lines: list[str] = []
    for raw in raw_lines:
        line = ' '.join(str(raw or '').replace('|', ' ').split()).strip(' ,;|-')
        if not line:
            continue
        if len(TEXT_SCORE_RE.findall(line)) < 2:
            continue
        line = re.sub(r'^[^A-Za-zÆØÅæøå0-9]+', '', line)
        line = re.sub(r'[^A-Za-zÆØÅæøå0-9.,:+\- ]+$', '', line)
        line = re.sub(r'\bTLF\s*[:.-]?\s*47\b', 'TLF.', line, flags=re.I)
        if not line:
            continue
        lines.append(line)
    return '\n'.join(lines).strip()


def extract_text_from_image(content: bytes, *, filename: str = '', timeout_seconds: int = 25) -> dict[str, Any]:
    if not content:
        raise ValueError('Bildefilen er tom.')
    try:
        image = _load_image(content)
    except Exception as exc:  # pragma: no cover - depends on image format support in runtime
        raise ValueError(f'Kunne ikke lese bildefilen {filename or ""}.') from exc

    attempts: list[dict[str, Any]] = []
    label_crops = _candidate_label_crops(image)
    try:
        variants: list[tuple[str, Image.Image, str]] = []
        for crop in label_crops:
            variants.extend(_prepare_variants(crop, label_mode=True))
        variants.extend(_prepare_variants(image, label_mode=False))
        # avoid excessive OCR passes
        variants = variants[:14]
        for label, variant, config in variants:
            try:
                text = pytesseract.image_to_string(variant, lang='nor+eng', config=config, timeout=timeout_seconds)
            except TesseractError:
                text = ''
            clean_text = _clean_ocr_text(text)
            attempts.append({
                'strategy': label,
                'text': clean_text,
                'hints': registry.extract_tag_hints(clean_text),
            })
    except TesseractNotFoundError as exc:  # pragma: no cover - runtime specific
        raise RuntimeError('OCR-motor er ikke installert på serveren.') from exc

    best: dict[str, Any] | None = None
    best_score = -1
    for item in attempts:
        text_value = str(item.get('text') or '').strip()
        hints = dict(item.get('hints') or {})
        score = _score_text(text_value) + _hint_quality(hints)
        if str(item.get('strategy') or '').startswith('etikett '):
            score += 80
            if hints.get('vessel_reg'):
                score += 25
            if hints.get('name'):
                score += 20
            if hints.get('phone') or hints.get('post_place'):
                score += 15
        if best is None or score > best_score:
            best = item
            best_score = score

    best = best or {'strategy': 'ingen', 'text': '', 'hints': {}}
    best_text = str(best.get('text') or '').strip()
    best_hints = dict(best.get('hints') or {})
    normalized_text = _compose_text_from_hints(best_hints, fallback_text=best_text)
    if _score_text(normalized_text) < 18:
        raise ValueError('Ingen tydelig tekst ble funnet i bildet.')
    return {
        'text': normalized_text,
        'raw_text': best_text,
        'hints': best_hints,
        'strategy': str(best.get('strategy') or 'forbedret bilde'),
        'attempts': [{
            'strategy': str(item.get('strategy') or ''),
            'score': _score_text(str(item.get('text') or '')) + _hint_quality(dict(item.get('hints') or {})),
        } for item in attempts],
        'label_crop_detected': bool(label_crops),
    }


__all__ = ['extract_text_from_image']
