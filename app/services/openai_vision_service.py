from __future__ import annotations

from base64 import b64encode
from io import BytesIO
import json
import os
import re
from typing import Any

import httpx
from PIL import Image, ImageOps, ImageEnhance, ImageFilter

try:
    from .ocr_service import extract_text_from_image as _local_extract_text_from_image
except Exception:  # pragma: no cover - optional fallback
    _local_extract_text_from_image = None

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

PERSON_MARKING_PROMPT = """Du er en presis bilde- og tekstleser for Kystvaktens kontroll av fiskeredskap.

Oppgaven er å lese tekst som faktisk er synlig på bilder av vak, blåse, flyt/dobbe, merke, teine, ruse, garnlenke eller tilsvarende fiskeredskap. Bildene kan vise håndskrift, slitte merker, buede overflater, skitt, dårlig lys eller delvis skjult tekst.

Returner KUN gyldig JSON med feltene:
navn, adresse, postnummer, poststed, mobil, deltakernummer, annen_merking og usikkerhet.

Slik skal du lese:
- Les først bildet som om du skulle transkribere all synlig tekst. Se etter navn, initialer, adresse, postnummer, poststed, mobilnummer og merking.
- Kombiner informasjon fra flere bilder; bruk oversiktsbilde for sammenheng og nærbilde for bokstaver/tall.
- Norske navn, adresser, postnummer/poststed og mobilnummer er vanlig. Eksempler på typisk struktur er: navn på én linje, adresse på neste, og fire siffer + poststed på samme eller neste linje.
- Telefonnummer kan være skrevet med mellomrom, punktum, bindestrek eller uten skilletegn. Behold bare synlige sifre og eventuelt +47.
- Deltakernummer/merking kan ligne JAN-JOH-128, OLA-NOR-123, FLE-FRE-134, AG-3-FS, registreringsmerke eller annen redskapsmerking. Slike koder skal normalt i deltakernummer eller annen_merking, ikke i mobilfeltet.
- Adresse kan stå på flere linjer. Postnummer er normalt fire siffer, med poststed etterpå. Dersom du ser fire siffer etterfulgt av stedsnavn, splitt disse til postnummer og poststed.
- Dersom et navn er synlig sammen med et nummer og kode, fyll navn selv om adresse eller poststed mangler.
- Hvis et felt ikke kan leses med rimelig sikkerhet, sett feltet til tom streng "".
- Ikke fyll inn navn, adresse, poststed eller telefonnummer fra antakelser eller eksterne kilder.
- Ikke gjett manglende bokstaver. Dersom deler av et ord/nummer er usikkert, la feltet stå tomt eller fyll bare sikker del i annen_merking og forklar usikkerheten.
- Forklar kort i "usikkerhet" hva som er uklart, for eksempel "mobilnummer delvis skjult" eller "poststed ikke lesbart".

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


VISION_MAX_SIDE = _env_int('KV_OPENAI_VISION_MAX_SIDE', 4200, minimum=1600, maximum=5200)
VISION_MIN_LONG_SIDE = _env_int('KV_OPENAI_VISION_MIN_LONG_SIDE', 2600, minimum=1200, maximum=4200)
VISION_JPEG_QUALITY = _env_int('KV_OPENAI_VISION_JPEG_QUALITY', 96, minimum=82, maximum=98)
VISION_TIMEOUT_SECONDS = _env_float('KV_OPENAI_VISION_TIMEOUT_SECONDS', 55.0, minimum=10.0, maximum=120.0)
VISION_MODEL_DEFAULT = 'gpt-4.1'


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


def _first_configured_api_key() -> tuple[str, str]:
    for name in ('OPENAI_API_KEY', 'KV_OPENAI_API_KEY', 'OPENAI_KEY'):
        value = str(os.getenv(name) or '').strip()
        if value:
            return value, name
    for name in ('OPENAI_API_KEY_FILE', 'KV_OPENAI_API_KEY_FILE'):
        path = str(os.getenv(name) or '').strip()
        if not path:
            continue
        try:
            value = open(path, 'r', encoding='utf-8').read().strip()
        except Exception:
            value = ''
        if value:
            return value, name
    return '', ''




def _split_post_place_text(value: Any) -> tuple[str, str]:
    text = _clean_string(value, max_len=120)
    if not text:
        return '', ''
    match = re.search(r'\b(\d{4})\s+([A-ZÆØÅa-zæøå][A-Za-zÆØÅæøå\- ]{1,60})', text)
    if match:
        return match.group(1), _clean_string(match.group(2), max_len=80)
    return _normalize_postnummer(text), ''


def _merge_unique(parts: list[str], *, max_len: int = 220) -> str:
    seen: set[str] = set()
    out: list[str] = []
    for part in parts:
        text = _clean_string(part, max_len=max_len)
        key = text.lower()
        if text and key not in seen:
            seen.add(key)
            out.append(text)
    return '; '.join(out)[:max_len]


def _local_ocr_person_marking_fallback(images: list[dict[str, Any]], *, reason: str = '') -> dict[str, Any]:
    """Best-effort fallback when OpenAI vision is not configured.

    The fallback uses the app's existing local OCR/hint extraction. It is less
    accurate than OpenAI vision on handwriting and dirty/bent markers, so every
    returned result is marked for manual review through the usikkerhet field.
    """
    if not images:
        raise ValueError('Legg ved minst ett bilde.')
    if _local_extract_text_from_image is None:
        return _sanitize_result({
            'navn': '',
            'adresse': '',
            'postnummer': '',
            'poststed': '',
            'mobil': '',
            'deltakernummer': '',
            'annen_merking': '',
            'usikkerhet': [
                reason or 'OpenAI API-nøkkel er ikke satt på serveren.',
                'Lokal OCR-reserve er ikke tilgjengelig i dette servermiljøet. Kontroller bildet manuelt og fyll ut feltene selv.',
            ],
        })
    max_images = _env_int('KV_OPENAI_VISION_MAX_IMAGES', 4, minimum=1, maximum=8)
    result: dict[str, Any] = {
        'navn': '',
        'adresse': '',
        'postnummer': '',
        'poststed': '',
        'mobil': '',
        'deltakernummer': '',
        'annen_merking': '',
        'usikkerhet': [],
    }
    other_markings: list[str] = []
    uncertainties: list[str] = []
    if reason:
        uncertainties.append(reason)
    for idx, image in enumerate(images[:max_images], start=1):
        filename = str(image.get('filename') or f'bilde-{idx}.jpg')
        content = bytes(image.get('content') or b'')
        try:
            parsed = _local_extract_text_from_image(content, filename=filename, timeout_seconds=45)
        except Exception as exc:
            uncertainties.append(f'Bilde {idx}: lokal OCR kunne ikke lese bildet ({exc}).')
            continue
        hints = dict((parsed or {}).get('hints') or {})
        if not result['navn'] and hints.get('name'):
            result['navn'] = hints.get('name')
        if not result['adresse'] and hints.get('address'):
            result['adresse'] = hints.get('address')
        if hints.get('post_place') and (not result['postnummer'] or not result['poststed']):
            post_no, post_place = _split_post_place_text(hints.get('post_place'))
            if post_no and not result['postnummer']:
                result['postnummer'] = post_no
            if post_place and not result['poststed']:
                result['poststed'] = post_place
        if not result['mobil'] and hints.get('phone'):
            result['mobil'] = hints.get('phone')
        if not result['deltakernummer'] and hints.get('hummer_participant_no'):
            result['deltakernummer'] = hints.get('hummer_participant_no')
        if hints.get('gear_marker_id'):
            other_markings.append('Merke-ID: ' + str(hints.get('gear_marker_id')).strip())
        if hints.get('vessel_reg'):
            other_markings.append('Fiskerimerke: ' + str(hints.get('vessel_reg')).strip())
        if hints.get('radio_call_sign'):
            other_markings.append('Kallesignal: ' + str(hints.get('radio_call_sign')).strip())
        if hints.get('vessel_name'):
            other_markings.append('Fartøysnavn: ' + str(hints.get('vessel_name')).strip())
        raw_text = _clean_string((parsed or {}).get('text') or (parsed or {}).get('raw_text'), max_len=220)
        if raw_text and not hints:
            other_markings.append(raw_text)
        uncertain = (parsed or {}).get('uncertain_fields') or []
        if isinstance(uncertain, list):
            for field in uncertain:
                name = _clean_string(field, max_len=80)
                if name:
                    uncertainties.append(f'Bilde {idx}: usikkert felt {name}.')
        if (parsed or {}).get('needs_manual_review'):
            uncertainties.append(f'Bilde {idx}: kontroller OCR-resultatet manuelt.')
    result['annen_merking'] = _merge_unique(other_markings)
    if not any(_clean_string(result.get(field)) for field in PERSON_MARKING_FIELDS if field != 'usikkerhet'):
        uncertainties.append('Ingen sikre tekstfelt ble lest fra bildet. Ta et tydelig nærbilde i bedre lys eller fyll ut manuelt.')
    elif not reason:
        uncertainties.append('Lokal OCR er brukt. Kontroller feltene manuelt før lagring.')
    result['usikkerhet'] = _merge_unique(uncertainties, max_len=1000).split('; ') if uncertainties else []
    return _sanitize_result(result)

def analyze_person_marking_images(images: list[dict[str, Any]]) -> dict[str, Any]:
    """Analyze one or more gear/marker photos with OpenAI vision.

    images: list of {'content': bytes, 'filename': str}
    Returns exactly the fields expected by the Person/Fartøy frontend.
    """
    api_key, api_key_source = _first_configured_api_key()
    if not api_key:
        return _local_ocr_person_marking_fallback(
            images,
            reason='OpenAI API-nøkkel er ikke satt på serveren. Lokal OCR er brukt som reserve; kontroller alle felt manuelt.'
        )
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
        'max_output_tokens': _env_int('KV_OPENAI_VISION_MAX_OUTPUT_TOKENS', 1200, minimum=300, maximum=4000),
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
