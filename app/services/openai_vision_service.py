from __future__ import annotations

from base64 import b64encode
from io import BytesIO
import json
import os
import re
from typing import Any

import httpx
from PIL import Image, ImageOps, ImageEnhance, ImageFilter

try:  # pragma: no cover - optional HEIC/HEIF support at runtime
    from pillow_heif import register_heif_opener
except Exception:  # pragma: no cover
    register_heif_opener = None

if register_heif_opener is not None:  # pragma: no cover
    try:
        register_heif_opener()
    except Exception:
        pass

PERSON_MARKING_FIELDS = [
    'navn',
    'adresse',
    'postnummer',
    'poststed',
    'mobil',
    'deltakernummer',
    'annen_merking',
    'usikkerhet',
]

PERSON_MARKING_PROMPT = """Les teksten på bildet av fiskeredskap, vak, blåse eller merke.
Returner KUN gyldig JSON med feltene:
navn, adresse, postnummer, poststed, mobil, deltakernummer, annen_merking og usikkerhet.

Viktig:
- Ikke gjett.
- Hvis noe er uklart, sett feltet til tom streng "".
- Forklar hva som er uklart i "usikkerhet".
- Norske navn, adresser og postnummer/poststed er vanlig.
- Telefonnummer kan være skrevet med mellomrom.
- Kombiner informasjon fra alle bildene dersom flere bilder er sendt inn.
- Bruk nærbildet for detaljer og oversiktsbildet for sammenheng.
- Håndter håndskrift, skitne/slitte merker, buede overflater, delvis skjult tekst og dårlige vinkler/lys.
- Ikke bruk eksterne kilder. Les bare det som faktisk er synlig i bildet/bildene.

JSON-format:
{
  "navn": "",
  "adresse": "",
  "postnummer": "",
  "poststed": "",
  "mobil": "",
  "deltakernummer": "",
  "annen_merking": "",
  "usikkerhet": []
}
""".strip()

PERSON_MARKING_SCHEMA: dict[str, Any] = {
    'type': 'object',
    'additionalProperties': False,
    'properties': {
        'navn': {'type': 'string'},
        'adresse': {'type': 'string'},
        'postnummer': {'type': 'string'},
        'poststed': {'type': 'string'},
        'mobil': {'type': 'string'},
        'deltakernummer': {'type': 'string'},
        'annen_merking': {'type': 'string'},
        'usikkerhet': {'type': 'array', 'items': {'type': 'string'}},
    },
    'required': PERSON_MARKING_FIELDS,
}


class VisionConfigError(RuntimeError):
    """Raised when server-side vision analysis is not configured."""


def _env_int(name: str, default: int, *, minimum: int, maximum: int) -> int:
    try:
        value = int(os.getenv(name, str(default)) or default)
    except Exception:
        value = default
    return max(minimum, min(maximum, value))


def _env_float(name: str, default: float, *, minimum: float, maximum: float) -> float:
    try:
        value = float(os.getenv(name, str(default)) or default)
    except Exception:
        value = default
    return max(minimum, min(maximum, value))


VISION_MAX_SIDE = _env_int('KV_OPENAI_VISION_MAX_SIDE', 2600, minimum=1400, maximum=4200)
VISION_MIN_LONG_SIDE = _env_int('KV_OPENAI_VISION_MIN_LONG_SIDE', 1700, minimum=900, maximum=3200)
VISION_JPEG_QUALITY = _env_int('KV_OPENAI_VISION_JPEG_QUALITY', 92, minimum=75, maximum=96)
VISION_TIMEOUT_SECONDS = _env_float('KV_OPENAI_VISION_TIMEOUT_SECONDS', 55.0, minimum=10.0, maximum=120.0)
VISION_MODEL_DEFAULT = 'gpt-4.1-mini'


def _image_to_jpeg_bytes(content: bytes, *, filename: str = '') -> bytes:
    if not content:
        raise ValueError('Tom bildefil.')
    try:
        image = Image.open(BytesIO(content))
        image = ImageOps.exif_transpose(image)
    except Exception as exc:
        raise ValueError('Kunne ikke lese bildefilen. Prøv JPG/PNG/HEIC fra kameraet.') from exc

    if image.mode not in {'RGB', 'L'}:
        image = image.convert('RGB')
    elif image.mode == 'L':
        image = image.convert('RGB')

    width, height = image.size
    if width < 1 or height < 1:
        raise ValueError('Bildefilen har ugyldig størrelse.')

    longest = max(width, height)
    scale = 1.0
    if longest > VISION_MAX_SIDE:
        scale = VISION_MAX_SIDE / float(longest)
    elif longest < VISION_MIN_LONG_SIDE:
        # Svært små bilder får forsiktig oppskalering. Det kan hjelpe håndskrift,
        # men vi begrenser dette for å unngå kunstige detaljer.
        scale = min(1.35, VISION_MIN_LONG_SIDE / float(longest))
    if abs(scale - 1.0) > 0.01:
        new_size = (max(1, round(width * scale)), max(1, round(height * scale)))
        image = image.resize(new_size, Image.Resampling.LANCZOS)

    # Svak kontrast/skarphet hjelper slitte/bløte merker uten å terskle bort håndskrift.
    try:
        image = ImageEnhance.Contrast(image).enhance(1.08)
        image = ImageEnhance.Sharpness(image).enhance(1.05)
        image = image.filter(ImageFilter.UnsharpMask(radius=1.1, percent=70, threshold=3))
    except Exception:
        pass

    out = BytesIO()
    image.save(out, format='JPEG', quality=VISION_JPEG_QUALITY, optimize=True, progressive=True)
    return out.getvalue()


def _data_url_for_image(content: bytes, *, filename: str = '') -> str:
    prepared = _image_to_jpeg_bytes(content, filename=filename)
    return 'data:image/jpeg;base64,' + b64encode(prepared).decode('ascii')


def _extract_output_text(response_payload: dict[str, Any]) -> str:
    direct = response_payload.get('output_text')
    if isinstance(direct, str) and direct.strip():
        return direct.strip()
    chunks: list[str] = []
    for item in response_payload.get('output') or []:
        if not isinstance(item, dict):
            continue
        for content_item in item.get('content') or []:
            if not isinstance(content_item, dict):
                continue
            text = content_item.get('text') or content_item.get('output_text')
            if isinstance(text, str) and text.strip():
                chunks.append(text.strip())
    return '\n'.join(chunks).strip()


def _json_from_text(text: str) -> dict[str, Any]:
    raw = str(text or '').strip()
    if not raw:
        raise ValueError('Modellen returnerte ikke tekst.')
    raw = re.sub(r'^```(?:json)?\s*', '', raw, flags=re.IGNORECASE).strip()
    raw = re.sub(r'\s*```$', '', raw).strip()
    try:
        parsed = json.loads(raw)
    except Exception:
        match = re.search(r'\{.*\}', raw, flags=re.DOTALL)
        if not match:
            raise ValueError('Modellen returnerte ikke gyldig JSON.')
        parsed = json.loads(match.group(0))
    if not isinstance(parsed, dict):
        raise ValueError('Modellen returnerte ikke et JSON-objekt.')
    return parsed


def _clean_string(value: Any, *, max_len: int = 220) -> str:
    text = re.sub(r'\s+', ' ', str(value or '')).strip()
    if text.lower() in {'null', 'none', 'ukjent', 'ikke synlig', 'ikke lesbar'}:
        return ''
    return text[:max_len]


def _normalize_mobile(value: Any) -> str:
    text = _clean_string(value, max_len=40)
    if not text:
        return ''
    text = re.sub(r'[^0-9+ ]+', '', text)
    text = re.sub(r'\s+', ' ', text).strip()
    digit_count = len(re.findall(r'\d', text))
    if digit_count < 5:
        return ''
    return text


def _normalize_postnummer(value: Any) -> str:
    text = _clean_string(value, max_len=16)
    match = re.search(r'\b\d{4}\b', text)
    return match.group(0) if match else ''


def _sanitize_result(parsed: dict[str, Any]) -> dict[str, Any]:
    usikkerhet_raw = parsed.get('usikkerhet')
    if isinstance(usikkerhet_raw, list):
        usikkerhet = [_clean_string(item, max_len=220) for item in usikkerhet_raw if _clean_string(item, max_len=220)]
    elif usikkerhet_raw:
        usikkerhet = [_clean_string(usikkerhet_raw, max_len=220)]
    else:
        usikkerhet = []

    result = {
        'navn': _clean_string(parsed.get('navn'), max_len=120),
        'adresse': _clean_string(parsed.get('adresse'), max_len=160),
        'postnummer': _normalize_postnummer(parsed.get('postnummer')),
        'poststed': _clean_string(parsed.get('poststed'), max_len=80),
        'mobil': _normalize_mobile(parsed.get('mobil')),
        'deltakernummer': _clean_string(parsed.get('deltakernummer'), max_len=60),
        'annen_merking': _clean_string(parsed.get('annen_merking'), max_len=220),
        'usikkerhet': usikkerhet,
    }
    return result


def analyze_person_marking_images(images: list[dict[str, Any]]) -> dict[str, Any]:
    """Analyze one or more gear/marker photos with OpenAI vision.

    images: list of {'content': bytes, 'filename': str}
    Returns exactly the fields expected by the Person/Fartøy frontend.
    """
    api_key = str(os.getenv('OPENAI_API_KEY') or os.getenv('KV_OPENAI_API_KEY') or '').strip()
    if not api_key:
        raise VisionConfigError('Bildeanalyse er ikke aktivert på serveren. Sett OPENAI_API_KEY eller KV_OPENAI_API_KEY.')
    if not images:
        raise ValueError('Legg ved minst ett bilde.')
    max_images = _env_int('KV_OPENAI_VISION_MAX_IMAGES', 4, minimum=1, maximum=8)
    selected = images[:max_images]
    content_items: list[dict[str, Any]] = [{'type': 'input_text', 'text': PERSON_MARKING_PROMPT}]
    for idx, image in enumerate(selected, start=1):
        filename = str(image.get('filename') or f'bilde-{idx}.jpg')
        data_url = _data_url_for_image(bytes(image.get('content') or b''), filename=filename)
        content_items.append({'type': 'input_text', 'text': f'Bilde {idx}: {filename}'})
        content_items.append({'type': 'input_image', 'image_url': data_url, 'detail': 'high'})

    model = str(os.getenv('KV_OPENAI_VISION_MODEL') or os.getenv('OPENAI_VISION_MODEL') or VISION_MODEL_DEFAULT).strip() or VISION_MODEL_DEFAULT
    payload = {
        'model': model,
        'input': [{'role': 'user', 'content': content_items}],
        'text': {
            'format': {
                'type': 'json_schema',
                'name': 'person_fartoy_merking',
                'schema': PERSON_MARKING_SCHEMA,
                'strict': True,
            }
        },
        'temperature': 0,
        'store': False,
    }
    headers = {'Authorization': f'Bearer {api_key}', 'Content-Type': 'application/json'}
    try:
        with httpx.Client(timeout=VISION_TIMEOUT_SECONDS) as client:
            response = client.post('https://api.openai.com/v1/responses', headers=headers, json=payload)
    except httpx.TimeoutException as exc:
        raise RuntimeError('Bildeanalyse tok for lang tid. Prøv ett tydeligere nærbilde eller bedre lys.') from exc
    except httpx.HTTPError as exc:
        raise RuntimeError('Kunne ikke kontakte bildeanalyse-tjenesten.') from exc

    if response.status_code >= 400:
        detail = ''
        try:
            detail = str((response.json().get('error') or {}).get('message') or '')
        except Exception:
            detail = response.text[:240]
        if 'temperature' in detail.lower():
            payload.pop('temperature', None)
            with httpx.Client(timeout=VISION_TIMEOUT_SECONDS) as client:
                response = client.post('https://api.openai.com/v1/responses', headers=headers, json=payload)
        if response.status_code >= 400:
            raise RuntimeError('Bildeanalyse feilet hos OpenAI' + (f': {detail}' if detail else '.'))

    response_payload = response.json()
    output_text = _extract_output_text(response_payload)
    parsed = _json_from_text(output_text)
    return _sanitize_result(parsed)
