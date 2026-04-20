from __future__ import annotations

from io import BytesIO
import re
from typing import Any

from PIL import Image, ImageEnhance, ImageOps
import pytesseract
from pytesseract import TesseractError, TesseractNotFoundError

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


def _score_text(text: str) -> int:
    cleaned = str(text or '').strip()
    if not cleaned:
        return 0
    alpha_num = len(TEXT_SCORE_RE.findall(cleaned))
    line_count = len([line for line in cleaned.splitlines() if line.strip()])
    return alpha_num * 4 + min(len(cleaned), 500) + min(line_count, 10) * 6


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
    max_side = 1800
    min_side = 1200
    width, height = image.size
    longest = max(width, height)
    if longest > max_side:
        image.thumbnail((max_side, max_side), Image.Resampling.LANCZOS)
    elif longest < min_side:
        scale = min(min_side / max(longest, 1), 1.8)
        image = image.resize((max(1, int(round(width * scale))), max(1, int(round(height * scale)))), Image.Resampling.LANCZOS)
    return image


def _prepare_variants(image: Image.Image) -> list[tuple[str, Image.Image, str]]:
    rgb = image
    gray = ImageOps.grayscale(image)
    enhanced = ImageOps.autocontrast(gray)
    enhanced = ImageEnhance.Contrast(enhanced).enhance(1.55)
    enhanced = ImageEnhance.Sharpness(enhanced).enhance(1.6)
    threshold = enhanced.point(lambda px: 255 if px > 156 else 0)
    sparse = ImageEnhance.Contrast(enhanced).enhance(1.7)
    medium = ImageEnhance.Contrast(gray).enhance(1.25)
    upscaled = enhanced
    longest = max(enhanced.size or (0, 0))
    if longest and longest < 1500:
        factor = min(2.0, 1500 / longest)
        upscaled = enhanced.resize((max(1, int(round(enhanced.width * factor))), max(1, int(round(enhanced.height * factor)))), Image.Resampling.LANCZOS)
    return [
        ('original farge', rgb, '--oem 1 --psm 11 preserve_interword_spaces=1'),
        ('forbedret bilde', enhanced, '--oem 1 --psm 6 preserve_interword_spaces=1'),
        ('oppskalert dokument', upscaled, '--oem 1 --psm 6 preserve_interword_spaces=1'),
        ('høy kontrast', threshold, '--oem 1 --psm 11 preserve_interword_spaces=1'),
        ('sparsom tekst', sparse, '--oem 1 --psm 12 preserve_interword_spaces=1'),
        ('enkel linje', medium, '--oem 1 --psm 7 preserve_interword_spaces=1'),
    ]


def extract_text_from_image(content: bytes, *, filename: str = '', timeout_seconds: int = 25) -> dict[str, Any]:
    if not content:
        raise ValueError('Bildefilen er tom.')
    try:
        image = _load_image(content)
    except Exception as exc:  # pragma: no cover - depends on image format support in runtime
        raise ValueError(f'Kunne ikke lese bildefilen {filename or ""}.') from exc

    attempts: list[dict[str, Any]] = []
    try:
        for label, variant, config in _prepare_variants(image):
            try:
                text = pytesseract.image_to_string(variant, lang='nor+eng', config=config, timeout=timeout_seconds)
            except TesseractError:
                text = ''
            attempts.append({'strategy': label, 'text': str(text or '').strip()})
    except TesseractNotFoundError as exc:  # pragma: no cover - runtime specific
        raise RuntimeError('OCR-motor er ikke installert på serveren.') from exc

    best = max(attempts, key=lambda item: _score_text(item.get('text', '')), default={'strategy': 'ingen', 'text': ''})
    best_text = str(best.get('text') or '').strip()
    if _score_text(best_text) < 18:
        raise ValueError('Ingen tydelig tekst ble funnet i bildet.')
    return {
        'text': best_text,
        'strategy': str(best.get('strategy') or 'forbedret bilde'),
        'attempts': [{
            'strategy': str(item.get('strategy') or ''),
            'score': _score_text(str(item.get('text') or '')),
        } for item in attempts],
    }


__all__ = ['extract_text_from_image']
