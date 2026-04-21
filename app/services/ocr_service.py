from __future__ import annotations

from io import BytesIO
import re
from typing import Any

import cv2
import numpy as np
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


def _pil_to_bgr(image: Image.Image) -> np.ndarray:
    rgb = np.asarray(image.convert('RGB'))
    return cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR)


def _bgr_to_pil(image: np.ndarray) -> Image.Image:
    rgb = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
    return Image.fromarray(rgb)


def _order_box_points(points: np.ndarray) -> np.ndarray:
    pts = np.asarray(points, dtype='float32')
    ordered = np.zeros((4, 2), dtype='float32')
    s = pts.sum(axis=1)
    ordered[0] = pts[np.argmin(s)]
    ordered[2] = pts[np.argmax(s)]
    diff = np.diff(pts, axis=1)
    ordered[1] = pts[np.argmin(diff)]
    ordered[3] = pts[np.argmax(diff)]
    return ordered


def _pad_label_crop(image: np.ndarray, *, pct: float = 0.03) -> np.ndarray:
    h, w = image.shape[:2]
    pad_y = max(8, int(round(h * pct)))
    pad_x = max(8, int(round(w * pct)))
    return cv2.copyMakeBorder(image, pad_y, pad_y, pad_x, pad_x, cv2.BORDER_CONSTANT, value=(255, 255, 255))


def _detect_label_crop(image: Image.Image) -> Image.Image | None:
    bgr = _pil_to_bgr(image)
    h, w = bgr.shape[:2]
    img_area = float(h * w)
    hsv = cv2.cvtColor(bgr, cv2.COLOR_BGR2HSV)
    best: tuple[float, np.ndarray] | None = None
    for value_min in (125, 145, 165):
        mask = cv2.inRange(hsv, (0, 0, value_min), (180, 95, 255))
        mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, cv2.getStructuringElement(cv2.MORPH_RECT, (9, 9)))
        mask = cv2.dilate(mask, cv2.getStructuringElement(cv2.MORPH_RECT, (5, 5)), iterations=1)
        contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        for contour in contours:
            area = float(cv2.contourArea(contour))
            if area < img_area * 0.04 or area > img_area * 0.82:
                continue
            rect = cv2.minAreaRect(contour)
            (cx, cy), (rw, rh), _ = rect
            if rw <= 0 or rh <= 0:
                continue
            ratio = max(rw, rh) / max(1.0, min(rw, rh))
            if ratio < 1.2 or ratio > 4.5:
                continue
            fill_ratio = area / max(1.0, rw * rh)
            if fill_ratio < 0.45:
                continue
            box = cv2.boxPoints(rect).astype('float32')
            distance_penalty = (abs(cx - w / 2) / w + abs(cy - h / 2) / h) * 5000.0
            score = area * fill_ratio - distance_penalty
            if best is None or score > best[0]:
                best = (score, box)
    if not best:
        return None
    box = _order_box_points(best[1])
    tl, tr, br, bl = box
    width = int(round(max(np.linalg.norm(br - bl), np.linalg.norm(tr - tl))))
    height = int(round(max(np.linalg.norm(tr - br), np.linalg.norm(tl - bl))))
    if width < 200 or height < 80:
        return None
    dst = np.array([[0, 0], [width - 1, 0], [width - 1, height - 1], [0, height - 1]], dtype='float32')
    matrix = cv2.getPerspectiveTransform(box, dst)
    warped = cv2.warpPerspective(bgr, matrix, (width, height), flags=cv2.INTER_CUBIC, borderMode=cv2.BORDER_REPLICATE)
    if warped.shape[0] > warped.shape[1]:
        warped = cv2.rotate(warped, cv2.ROTATE_90_CLOCKWISE)
    warped = _pad_label_crop(warped)
    return _bgr_to_pil(warped)


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
    label_crop = _detect_label_crop(image)
    try:
        variants: list[tuple[str, Image.Image, str]] = []
        if label_crop is not None:
            variants.extend(_prepare_variants(label_crop, label_mode=True))
        variants.extend(_prepare_variants(image, label_mode=False))
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
        'label_crop_detected': bool(label_crop is not None),
    }


__all__ = ['extract_text_from_image']
