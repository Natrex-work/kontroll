from __future__ import annotations

from io import BytesIO
import os
import re
import time
from typing import Any

from PIL import Image, ImageEnhance, ImageOps

from .. import registry

pytesseract = None
TesseractError = RuntimeError
TesseractNotFoundError = RuntimeError
_TESSERACT_IMPORT_ATTEMPTED = False


def _tesseract_libs():
    global pytesseract, TesseractError, TesseractNotFoundError, _TESSERACT_IMPORT_ATTEMPTED
    if not _TESSERACT_IMPORT_ATTEMPTED:
        _TESSERACT_IMPORT_ATTEMPTED = True
        try:
            import pytesseract as _pytesseract
            from pytesseract import TesseractError as _TesseractError, TesseractNotFoundError as _TesseractNotFoundError
            pytesseract = _pytesseract
            TesseractError = _TesseractError
            TesseractNotFoundError = _TesseractNotFoundError
        except Exception:
            pytesseract = None
    if pytesseract is None:
        raise RuntimeError('OCR-motor er ikke tilgjengelig på serveren.')
    return pytesseract, TesseractError, TesseractNotFoundError


try:  # pragma: no cover - optional runtime enhancement for HEIC/HEIF support
    from pillow_heif import register_heif_opener
except Exception:  # pragma: no cover
    register_heif_opener = None

if register_heif_opener is not None:  # pragma: no cover - depends on optional package
    try:
        register_heif_opener()
    except Exception:
        pass

# OpenCV/numpy are useful for cropping and deskewing, but importing cv2 at
# application startup is expensive in small containers and has previously made
# smoke tests/deploy health checks hang. Load these libraries only when an OCR
# request actually needs them.
cv2 = None
np = None
_VISION_IMPORT_ATTEMPTED = False


def _vision_libs():
    global cv2, np, _VISION_IMPORT_ATTEMPTED
    if not _VISION_IMPORT_ATTEMPTED:
        _VISION_IMPORT_ATTEMPTED = True
        try:  # pragma: no cover - optional runtime enhancement for deskewing OCR images
            import cv2 as _cv2
            import numpy as _np
            cv2 = _cv2
            np = _np
        except Exception:  # pragma: no cover
            cv2 = None
            np = None
    return cv2, np

TEXT_SCORE_RE = re.compile(r'[A-Za-zÆØÅæøå0-9]')
PHONE_HINT_RE = re.compile(r'(?:\+?47\s*)?\d[\d\s]{6,}')
POST_HINT_RE = re.compile(r'\b\d{4}\s+[A-ZÆØÅa-zæøå][A-Za-zÆØÅæøå\- ]{2,30}\b')
VESSEL_HINT_RE = re.compile(r'\b[A-ZÆØÅ]{1,4}[- ]?[A-ZÆØÅ]{1,4}[- ]?\d{2,4}\b')
NAME_HINT_RE = re.compile(r'\b[A-ZÆØÅ][A-Za-zÆØÅæøå\-]+(?:\s+[A-ZÆØÅ][A-Za-zÆØÅæøå\-]+){1,3}\b')
FIELD_BONUS = {
    'name': 42,
    'address': 34,
    'post_place': 30,
    'phone': 36,
    'birthdate': 24,
    'vessel_reg': 34,
    'radio_call_sign': 30,
    'hummer_participant_no': 46,
}


def _env_int(name: str, default: int, *, minimum: int, maximum: int) -> int:
    try:
        value = int(os.getenv(name, str(default)) or default)
    except Exception:
        value = default
    return max(minimum, min(maximum, value))


OCR_MAX_SIDE = _env_int('KV_OCR_MAX_SIDE', 2800, minimum=1100, maximum=3600)
OCR_MIN_SIDE = _env_int('KV_OCR_MIN_SIDE', 1600, minimum=700, maximum=2600)
OCR_VARIANT_LIMIT = _env_int('KV_OCR_VARIANT_LIMIT', 20, minimum=3, maximum=28)
OCR_ATTEMPT_TIMEOUT_MAX = _env_int('KV_OCR_ATTEMPT_TIMEOUT', 12, minimum=3, maximum=18)
OCR_ENABLE_DESKEW = os.getenv('KV_OCR_ENABLE_DESKEW', '1').lower() in {'1', 'true', 'yes', 'on'}


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
    if hints.get('gear_marker_id'):
        score += 50
    if hints.get('radio_call_sign'):
        score += 35
    if hints.get('vessel_name'):
        score += 35
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
    if hints.get('hummer_participant_no'):
        lines.append(str(hints['hummer_participant_no']).strip())
    if hints.get('gear_marker_id'):
        lines.append('Merke-ID: ' + str(hints['gear_marker_id']).strip())
    elif hints.get('vessel_reg'):
        lines.append(str(hints['vessel_reg']).strip())
    if hints.get('vessel_name'):
        lines.append('Fartøysnavn: ' + str(hints['vessel_name']).strip())
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
    max_side = OCR_MAX_SIDE
    min_side = OCR_MIN_SIDE
    width, height = image.size
    longest = max(width, height)
    if longest > max_side:
        image.thumbnail((max_side, max_side), Image.Resampling.LANCZOS)
    elif longest < min_side:
        scale = min(min_side / max(longest, 1), 2.0)
        image = image.resize((max(1, int(round(width * scale))), max(1, int(round(height * scale)))), Image.Resampling.LANCZOS)
    return image


def _crop_to_dark_content(image: Image.Image, *, threshold: int = 220, margin: int = 40) -> Image.Image:
    local_cv2, local_np = _vision_libs()
    if local_cv2 is None or local_np is None:
        return image
    try:
        arr = local_np.array(image.convert('RGB'))
        gray = local_cv2.cvtColor(arr, local_cv2.COLOR_RGB2GRAY)
        mask = gray < threshold
        if not bool(mask.any()):
            return image
        ys, xs = local_np.where(mask)
        left = max(0, int(xs.min()) - margin)
        top = max(0, int(ys.min()) - margin)
        right = min(arr.shape[1], int(xs.max()) + margin + 1)
        bottom = min(arr.shape[0], int(ys.max()) + margin + 1)
        if right - left < 140 or bottom - top < 50:
            return image
        return image.crop((left, top, right, bottom))
    except Exception:
        return image


def _estimate_text_angle(image: Image.Image) -> float | None:
    local_cv2, local_np = _vision_libs()
    if local_cv2 is None or local_np is None:
        return None
    try:
        work = image.convert('RGB').copy()
        max_side = OCR_MAX_SIDE
        if max(work.size) > max_side:
            work.thumbnail((max_side, max_side), Image.Resampling.LANCZOS)
        arr = local_np.array(work)
        gray = local_cv2.cvtColor(arr, local_cv2.COLOR_RGB2GRAY)
        gray = local_cv2.GaussianBlur(gray, (3, 3), 0)
        _, thresh = local_cv2.threshold(gray, 0, 255, local_cv2.THRESH_BINARY_INV + local_cv2.THRESH_OTSU)
        if local_cv2.countNonZero(thresh) < 180:
            thresh = ((gray < 220).astype('uint8')) * 255
        kernel = local_np.ones((3, 3), dtype='uint8')
        thresh = local_cv2.morphologyEx(thresh, local_cv2.MORPH_OPEN, kernel, iterations=1)
        coords = local_np.column_stack(local_np.where(thresh > 0))
        if coords.size < 180:
            return None
        rect = local_cv2.minAreaRect(coords.astype('float32'))
        angle = float(rect[-1])
        width, height = rect[1]
        if width < height:
            angle = 90.0 + angle
        if angle > 45.0:
            angle -= 90.0
        if angle < -45.0:
            angle += 90.0
        if abs(angle) < 1.2 or abs(angle) > 35.0:
            return None
        return angle
    except Exception:
        return None


def _deskew_full_image_variants(image: Image.Image) -> list[tuple[str, Image.Image, str]]:
    if not OCR_ENABLE_DESKEW:
        return []
    angle = _estimate_text_angle(image)
    if angle is None:
        return []
    variants: list[tuple[str, Image.Image, str]] = []
    seen_angles: set[float] = set()
    for candidate in [angle, angle + 1.2, angle - 1.2]:
        rounded = round(candidate, 1)
        if rounded in seen_angles or abs(candidate) < 1.0 or abs(candidate) > 35.0:
            continue
        seen_angles.add(rounded)
        try:
            rotated = image.rotate(-candidate, expand=True, fillcolor='#ffffff')
            margin = max(28, int(round(max(rotated.size) * 0.018)))
            cropped = _crop_to_dark_content(rotated, threshold=220, margin=margin)
            if cropped.height > cropped.width * 1.7:
                cropped = cropped.rotate(90, expand=True, fillcolor='#ffffff')
            padded = _pad_label_crop(cropped, pct=0.02)
            variants.extend(_prepare_variants(padded, label_mode=True)[:4])
        except Exception:
            continue
    deduped: list[tuple[str, Image.Image, str]] = []
    seen: set[tuple[str, tuple[int, int], str]] = set()
    for label, variant, config in variants:
        key = (label, variant.size, config)
        if key in seen:
            continue
        seen.add(key)
        deduped.append((label, variant, config))
    return deduped[:8]


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
        (0.02, 0.02, 0.98, 0.98),
        (0.05, 0.00, 0.95, 0.38),
        (0.05, 0.55, 0.95, 0.98),
        (0.15, 0.10, 0.85, 0.52),
        (0.10, 0.15, 0.90, 0.58),
        (0.18, 0.18, 0.82, 0.62),
        (0.06, 0.08, 0.94, 0.70),
        (0.00, 0.12, 0.52, 0.82),
        (0.48, 0.12, 1.00, 0.82),
        (0.22, 0.00, 0.78, 0.92),
    ]
    seen_boxes: set[tuple[int, int, int, int]] = set()
    for left_r, top_r, right_r, bottom_r in windows:
        left = int(round(w * left_r))
        top = int(round(h * top_r))
        right = int(round(w * right_r))
        bottom = int(round(h * bottom_r))
        box = (left, top, right, bottom)
        if box in seen_boxes:
            continue
        seen_boxes.add(box)
        if right - left < 180 or bottom - top < 70:
            continue
        crops.append(_pad_label_crop(image.crop(box)))
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
    return crops[:6]


def _adaptive_ocr_variants(image: Image.Image, *, label_mode: bool = False) -> list[tuple[str, Image.Image, str]]:
    local_cv2, local_np = _vision_libs()
    if local_cv2 is None or local_np is None:
        return []
    try:
        arr = local_np.array(image.convert('RGB'))
        gray = local_cv2.cvtColor(arr, local_cv2.COLOR_RGB2GRAY)
        gray = local_cv2.fastNlMeansDenoising(gray, None, 8 if label_mode else 6, 7, 21)
        clahe = local_cv2.createCLAHE(clipLimit=2.6 if label_mode else 2.2, tileGridSize=(8, 8)).apply(gray)
        block = 31 if label_mode else 35
        if block % 2 == 0:
            block += 1
        adaptive = local_cv2.adaptiveThreshold(clahe, 255, local_cv2.ADAPTIVE_THRESH_GAUSSIAN_C, local_cv2.THRESH_BINARY, block, 9 if label_mode else 11)
        otsu = local_cv2.threshold(clahe, 0, 255, local_cv2.THRESH_BINARY + local_cv2.THRESH_OTSU)[1]
        kernel = local_np.ones((2, 2), dtype='uint8')
        closed = local_cv2.morphologyEx(adaptive, local_cv2.MORPH_CLOSE, kernel, iterations=1)
        prefix = 'etikett ' if label_mode else ''
        return [
            (prefix + 'adaptiv kontrast', Image.fromarray(clahe), '--oem 1 --psm 6 preserve_interword_spaces=1'),
            (prefix + 'adaptiv terskel', Image.fromarray(adaptive), '--oem 1 --psm 6 preserve_interword_spaces=1'),
            (prefix + 'otsu terskel', Image.fromarray(otsu), '--oem 1 --psm 11 preserve_interword_spaces=1'),
            (prefix + 'lukket terskel', Image.fromarray(closed), '--oem 1 --psm 6 preserve_interword_spaces=1'),
        ]
    except Exception:
        return []


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
    rotated_left = upscaled.rotate(90, expand=True)
    rotated_right = upscaled.rotate(-90, expand=True)
    rotated_180 = upscaled.rotate(180, expand=True)
    base_psm = '6'
    alt_psm = '11'
    line_psm = '6' if label_mode else '7'
    prefix = 'etikett ' if label_mode else ''
    variants = [
        (prefix + 'original farge', rgb, f'--oem 1 --psm {alt_psm} preserve_interword_spaces=1'),
        (prefix + 'forbedret bilde', enhanced, f'--oem 1 --psm {base_psm} preserve_interword_spaces=1'),
        (prefix + 'oppskalert dokument', upscaled, f'--oem 1 --psm {base_psm} preserve_interword_spaces=1'),
    ]
    variants.extend(_adaptive_ocr_variants(image, label_mode=label_mode))
    variants.extend([
        (prefix + 'rotert venstre', rotated_left, f'--oem 1 --psm {base_psm} preserve_interword_spaces=1'),
        (prefix + 'rotert høyre', rotated_right, f'--oem 1 --psm {base_psm} preserve_interword_spaces=1'),
        (prefix + 'rotert 180', rotated_180, f'--oem 1 --psm {base_psm} preserve_interword_spaces=1'),
        (prefix + 'høy kontrast', threshold, f'--oem 1 --psm {alt_psm} preserve_interword_spaces=1'),
        (prefix + 'sparsom tekst', sparse, f'--oem 1 --psm {alt_psm} preserve_interword_spaces=1'),
        (prefix + 'enkel linje', medium, f'--oem 1 --psm {line_psm} preserve_interword_spaces=1'),
    ])
    return variants


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


def _preferred_variants(image: Image.Image, label_crops: list[Image.Image]) -> list[tuple[str, Image.Image, str]]:
    variants: list[tuple[str, Image.Image, str]] = []
    deskewed = _deskew_full_image_variants(image)
    variants.extend(deskewed[:6])
    full_variants = _prepare_variants(image, label_mode=False)
    variants.extend(full_variants[:5 if not deskewed else 4])
    for crop in label_crops[:3]:
        variants.extend(_prepare_variants(crop, label_mode=True)[:5])
    variants.extend(full_variants[5:8])
    if len(label_crops) > 3:
        variants.extend(_prepare_variants(label_crops[3], label_mode=True)[:3])
    deduped: list[tuple[str, Image.Image, str]] = []
    seen: set[tuple[str, tuple[int, int], str]] = set()
    for label, variant, config in variants:
        key = (label, variant.size, config)
        if key in seen:
            continue
        seen.add(key)
        deduped.append((label, variant, config))
    return deduped[:22]


def _field_value_score(field: str, value: str) -> int:
    text = str(value or '').strip()
    if not text:
        return -1
    score = len(text) + FIELD_BONUS.get(field, 0)
    if field == 'phone' and re.fullmatch(r'(?:\+?47)?\d{8}', text.replace(' ', '')):
        score += 18
    if field == 'post_place' and POST_HINT_RE.search(text):
        score += 18
    if field == 'name' and len(NAME_HINT_RE.findall(text)) >= 1:
        score += 16
    if field == 'address' and re.search(r'\d', text):
        score += 10
    if field == 'hummer_participant_no' and registry._normalize_hummer_no(text):
        score += 25
    if field == 'gear_marker_id' and getattr(registry, '_normalize_gear_marker_id', lambda value: '')(text):
        score += 22
    if field == 'vessel_name' and len(text) >= 2:
        score += 12
    if field == 'radio_call_sign' and re.fullmatch(r'[A-ZÆØÅ]{2,5}\d{0,3}', text.upper().replace(' ', '')):
        score += 12
    if field == 'vessel_reg' and VESSEL_HINT_RE.search(text):
        score += 18
    return score


def _merge_best_hints(attempts: list[dict[str, Any]]) -> dict[str, str]:
    merged = {
        'phone': '',
        'vessel_reg': '',
        'radio_call_sign': '',
        'hummer_participant_no': '',
        'gear_marker_id': '',
        'address': '',
        'post_place': '',
        'birthdate': '',
        'name': '',
        'vessel_name': '',
    }
    best_scores = {key: -1 for key in merged}
    texts: list[str] = []
    for item in attempts:
        text_value = str(item.get('text') or '').strip()
        if text_value and text_value not in texts:
            texts.append(text_value)
        hints = dict(item.get('hints') or {})
        attempt_score = int(item.get('_score') or 0)
        for field in merged:
            value = str(hints.get(field) or '').strip()
            if not value:
                continue
            score = attempt_score + _field_value_score(field, value)
            if score > best_scores[field]:
                best_scores[field] = score
                merged[field] = value
    if texts:
        combined_text = '\n'.join(texts[:4])
        combined_hints = registry.extract_tag_hints(combined_text)
        for field in merged:
            value = str(combined_hints.get(field) or '').strip()
            if not value:
                continue
            score = _score_text(combined_text) + _field_value_score(field, value)
            if score > best_scores[field]:
                best_scores[field] = score
                merged[field] = value
    return merged


def extract_text_from_image(content: bytes, *, filename: str = '', timeout_seconds: int = 25) -> dict[str, Any]:
    if not content:
        raise ValueError('Bildefilen er tom.')
    started = time.monotonic()
    max_wall_seconds = max(10.0, min(float(timeout_seconds or 25), 50.0))
    deadline = started + max_wall_seconds
    try:
        image = _load_image(content)
    except Exception as exc:  # pragma: no cover - depends on image format support in runtime
        raise ValueError(f'Kunne ikke lese bildefilen {filename or ""}.') from exc

    attempts: list[dict[str, Any]] = []
    try:
        tesseract, tesseract_error_cls, tesseract_missing_cls = _tesseract_libs()
    except RuntimeError as exc:  # pragma: no cover - runtime specific
        raise RuntimeError('OCR-motor er ikke installert pa serveren.') from exc
    label_crops = _candidate_label_crops(image)
    timed_out = False
    try:
        variant_limit = OCR_VARIANT_LIMIT if max_wall_seconds <= 32 else min(28, OCR_VARIANT_LIMIT + 6)
        variants = _preferred_variants(image, label_crops)[:variant_limit]
        for label, variant, config in variants:
            remaining = deadline - time.monotonic()
            if remaining < 3.0:
                timed_out = True
                break
            attempt_timeout = max(3, min(OCR_ATTEMPT_TIMEOUT_MAX, int(remaining)))
            try:
                text = tesseract.image_to_string(variant, lang='nor+eng', config=config, timeout=attempt_timeout)
            except tesseract_missing_cls:
                raise
            except (tesseract_error_cls, RuntimeError):
                text = ''
            clean_text = _clean_ocr_text(text)
            hints = registry.extract_tag_hints(clean_text)
            score = _score_text(clean_text) + _hint_quality(hints)
            if str(label or '').startswith('etikett '):
                score += 40
                if hints.get('vessel_reg'):
                    score += 25
                if hints.get('name'):
                    score += 20
                if hints.get('phone') or hints.get('post_place'):
                    score += 15
            attempts.append({
                'strategy': label,
                'text': clean_text,
                'hints': hints,
                '_score': score,
            })
            if hints.get('name') and (hints.get('address') or hints.get('post_place')) and (hints.get('phone') or hints.get('hummer_participant_no') or hints.get('vessel_reg')) and score >= 200:
                break
            if score >= 230 and sum(1 for value in hints.values() if str(value or '').strip()) >= 4:
                break
    except tesseract_missing_cls as exc:  # pragma: no cover - runtime specific
        raise RuntimeError('OCR-motor er ikke installert pa serveren.') from exc

    best: dict[str, Any] | None = None
    best_score = -1
    for item in attempts:
        score = int(item.get('_score') or 0)
        if best is None or score > best_score:
            best = item
            best_score = score

    best = best or {'strategy': 'ingen', 'text': '', 'hints': {}, '_score': 0}
    best_text = str(best.get('text') or '').strip()
    merged_hints = _merge_best_hints(attempts)
    best_hints = merged_hints if any(str(value or '').strip() for value in merged_hints.values()) else dict(best.get('hints') or {})
    normalized_text = _compose_text_from_hints(best_hints, fallback_text=best_text)
    if _score_text(normalized_text) < 18 and _score_text(best_text) >= 18:
        normalized_text = best_text
    if _score_text(normalized_text) < 18:
        if timed_out:
            raise ValueError('OCR brukte for lang tid uten a finne tydelig tekst. Prov et skarpere og tettere bilde.')
        raise ValueError('Ingen tydelig tekst ble funnet i bildet.')
    return {
        'text': normalized_text,
        'raw_text': best_text,
        'hints': best_hints,
        'strategy': str(best.get('strategy') or 'forbedret bilde'),
        'attempts': [{
            'strategy': str(item.get('strategy') or ''),
            'score': int(item.get('_score') or 0),
        } for item in attempts],
        'label_crop_detected': bool(label_crops),
        'timed_out': timed_out,
        'elapsed_ms': int((time.monotonic() - started) * 1000),
    }

__all__ = ['extract_text_from_image']
