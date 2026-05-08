"""Local image analyzer for Person/Fartøy.

Replaces the OpenAI Vision dependency with a 100% local pipeline:
  1. Tesseract OCR via the existing ocr_service.extract_text_from_image
  2. Smart field-routing using extract_tag_hints + supplementary patterns
  3. Authoritative lookup against the cached Hummer registry from
     tableau.fiskeridir.no when a deltakernummer is found.

Returns the same JSON shape as the OpenAI vision service so the front-end
needs no changes.
"""
from __future__ import annotations

import re
from typing import Any

from .. import registry
from ..logging_setup import get_logger

logger = get_logger(__name__)

# Re-use the helpers and constants already defined in openai_vision_service so
# the output shape stays identical.
from .openai_vision_service import (  # type: ignore
    PERSON_MARKING_FIELDS,
    _clean_string,
    _merge_unique,
    _normalize_mobile,
    _normalize_postnummer,
    _sanitize_result,
    _split_post_place_text,
)

# Local OCR (already tesseract-based)
try:
    from .ocr_service import extract_text_from_image as _local_extract_text_from_image
except Exception:
    _local_extract_text_from_image = None  # type: ignore[assignment]


# ---------------------------------------------------------------------------
# Patterns for fishery marker cards (broader than registry.extract_tag_hints)
# ---------------------------------------------------------------------------

# Hummer participant number — accepts a wide range of formats seen on cards:
#   H-2024-001, H 2024 001, 20240001, 2024 0001, etc.
_HUMMER_PATTERNS = [
    re.compile(r'\b[Hh]\s*[-–\s]*(\d{4})\s*[-–\s]*(\d{2,4})\b'),  # H-2024-001
    re.compile(r'\b(20\d{2})\s*[-–\s]*(\d{3,4})\b'),               # 2024-001
    re.compile(r'\b([A-ZÆØÅ]{2,4})\s*[-–\s]*([A-ZÆØÅ]{2,4})\s*[-–\s]*(\d{2,4})\b'),  # ABC-DEF-123
]

# Norwegian postal code: 4 digits not preceded by a letter
_POSTNR_RE = re.compile(r'(?<![A-ZÆØÅa-zæøå0-9])(\d{4})(?![\d])')

# Norwegian mobile: 8 digits, starts with 4 or 9, optionally with country code
_MOBILE_RE = re.compile(r'(?:\+?47[\s\-]?)?([49]\d{2})[\s\-]?(\d{2})[\s\-]?(\d{3})')

# Address heuristic: line ending with a number, often containing typical road suffixes
_ADDRESS_HINTS_RE = re.compile(r'(?:vei|veg|gate|gata|gt\.?|veien|vegen|allé|alle|plass|brygga|bakken|haug|stien|svingen|toppen|tunet)', re.IGNORECASE)
_ADDRESS_NUMBER_RE = re.compile(r'\b\d+\s*[A-Za-z]?\b\s*$')


def _clean_lines(text: str) -> list[str]:
    """Normalize and filter lines from OCR text."""
    if not text:
        return []
    raw_lines = [ln.strip() for ln in str(text).splitlines() if ln and ln.strip()]
    out: list[str] = []
    for ln in raw_lines:
        # Collapse repeated whitespace
        ln = re.sub(r'\s+', ' ', ln).strip()
        # Drop rows that are clearly noise (only punctuation, single chars, etc.)
        if len(ln) < 2:
            continue
        if not re.search(r'[A-Za-zÆØÅæøå0-9]', ln):
            continue
        out.append(ln)
    return out


def _looks_like_address(line: str) -> bool:
    """True if the line matches a typical Norwegian street address pattern."""
    if not line:
        return False
    # Phone numbers must never be classified as address
    if _MOBILE_RE.search(line):
        return False
    # Lines that are mostly digits (8+) are likely phone or registration numbers
    digits_only = re.sub(r'\D', '', line)
    if len(digits_only) >= 8 and len(digits_only) >= len(line) * 0.5:
        return False
    if _ADDRESS_HINTS_RE.search(line):
        return True
    if _ADDRESS_NUMBER_RE.search(line):
        return True
    return False


def _extract_postnr_and_place(line: str) -> tuple[str, str]:
    """Given a line that contains postnr + sted (e.g. '4019 STAVANGER'),
    return (postnr, sted)."""
    match = _POSTNR_RE.search(line)
    if not match:
        return '', ''
    postnr = match.group(1)
    # Norwegian convention: postnummer FIRST, then sted (e.g. "4019 STAVANGER")
    after = line[match.end():].strip(' \t,-')
    before = line[:match.start()].strip(' \t,-')

    # Pick the side that looks more like a place name: only letters, no digits
    def _looks_like_place(s: str) -> bool:
        if not s:
            return False
        # Must have letters and be at least 2 chars
        letters = sum(1 for c in s if c.isalpha())
        if letters < 2:
            return False
        # Don't accept lines that contain another 4-digit number (likely a phone)
        if re.search(r'\d{4,}', s):
            return False
        return True

    if _looks_like_place(after):
        place = after
    elif _looks_like_place(before):
        place = before
    else:
        place = ''

    # Normalize: capitalize first letter of each word
    place = re.sub(r'\s+', ' ', place).strip()
    if place:
        # Title-case if all-caps, else preserve
        if place.isupper():
            place = ' '.join(w.capitalize() for w in place.split())
        # Remove leading/trailing punctuation
        place = place.strip(' ,.-')
    return postnr, place


def _extract_hummer_no(text: str) -> str:
    """Try several patterns to find a hummer participant number in raw text.

    Strict checks: must NOT be a plain 8-digit Norwegian phone number.
    """
    for pattern in _HUMMER_PATTERNS:
        match = pattern.search(text)
        if match:
            candidate = match.group(0).strip()
            # If candidate is just 8 digits starting with 4 or 9, it's a phone, not deltakernr
            digits_only = re.sub(r'\D', '', candidate)
            if len(digits_only) == 8 and digits_only[0] in '49':
                continue
            normalized = registry._normalize_hummer_no(candidate)
            if normalized:
                return normalized
    return ''


def _extract_mobile(text: str) -> str:
    """Find a Norwegian mobile number in text.

    Strict checks: must be a clean 8-digit number, must not be embedded in a
    longer year-prefixed string like '20240001' (those are deltakernumre).
    """
    for match in _MOBILE_RE.finditer(text):
        digits = match.group(1) + match.group(2) + match.group(3)
        if len(digits) != 8 or digits[0] not in '49':
            continue
        # Check the surrounding context to make sure this is not actually a
        # 12-digit hummer participant number like 20240001234
        start = match.start()
        if start >= 2 and text[start - 2: start].isdigit():
            # Looks like part of a longer number — skip
            continue
        return digits
    return ''


def _looks_like_name(line: str) -> bool:
    """Heuristic for Norwegian person names: 2+ capitalized words, no digits.

    Strict checks:
    - Must NOT contain any digits
    - Must NOT match address keywords (vei/gate/etc.)
    - Must have 2-5 words
    - Each word must be ≥ 2 chars
    - At least 2 words must start with uppercase or be all-caps
    - Must NOT be a label fragment like 'Navn:' or 'Mob nr'
    """
    if not line:
        return False
    if any(c.isdigit() for c in line):
        return False
    # Reject lines that are address/postal/contact keywords
    if _ADDRESS_HINTS_RE.search(line):
        return False
    if re.search(r'(?i)\b(navn|adresse|postnr|postnummer|poststed|sted|mobil|telefon|tlf|deltaker|hummer|fylke|kommune|epost|e-post)\b', line):
        return False
    words = [w for w in re.split(r'\s+', line.strip()) if w]
    if len(words) < 2 or len(words) > 5:
        return False
    cap_words = sum(1 for w in words if w[:1].isupper() or w.isupper())
    if cap_words < 2:
        return False
    if not all(len(w) >= 2 for w in words):
        return False
    # Reject if any word is suspiciously short and lowercase only (like "av", "og")
    if any(w.lower() in {'av', 'og', 'i', 'på', 'til', 'fra', 'med'} for w in words):
        return False
    return True


def _is_label_only(line: str) -> bool:
    """True if the line is just a label like 'Navn:' or 'Adresse:'."""
    line = line.strip()
    return bool(re.match(r'^(navn|adresse|postnr|postnummer|poststed|mobil|telefon|tlf|deltaker|hummer)[\s:.\-]*$', line, re.IGNORECASE))


# ---------------------------------------------------------------------------
# Main pipeline — vote-based aggregator for higher precision
# ---------------------------------------------------------------------------

# Strong validators per field type. These run AFTER the loose hint extraction
# to make sure a value really belongs in that field.

_NORWEGIAN_MOBILE_RE_STRICT = re.compile(r'^[49]\d{7}$')
_POSTNUMMER_STRICT_RE = re.compile(r'^\d{4}$')
_POSTSTED_STRICT_RE = re.compile(r'^[A-ZÆØÅa-zæøå][A-Za-zÆØÅæøå\- ]{1,40}$')
_PARTICIPANT_STRICT_RE = re.compile(r'^[A-Z0-9\-]{4,20}$', re.IGNORECASE)


def _validate_field(field: str, value: str) -> bool:
    """Strict validator. Returns True only when value plausibly belongs to field."""
    v = str(value or '').strip()
    if not v:
        return False
    if field == 'mobil':
        digits = ''.join(ch for ch in v if ch.isdigit())
        # Strip leading 47 country code
        if digits.startswith('47') and len(digits) == 10:
            digits = digits[2:]
        return bool(_NORWEGIAN_MOBILE_RE_STRICT.match(digits))
    if field == 'postnummer':
        return bool(_POSTNUMMER_STRICT_RE.match(v))
    if field == 'poststed':
        return bool(_POSTSTED_STRICT_RE.match(v))
    if field == 'deltakernummer':
        # Allow common formats: H-YYYY-NNN, 20YYNNN, ABC-DEF-NNN
        return bool(_PARTICIPANT_STRICT_RE.match(v.replace(' ', '')))
    if field == 'navn':
        if any(c.isdigit() for c in v):
            return False
        words = [w for w in re.split(r'\s+', v.strip()) if w]
        return 2 <= len(words) <= 5 and all(len(w) >= 2 for w in words)
    if field == 'adresse':
        # Has at least one letter + at least one digit (street + number)
        return any(c.isalpha() for c in v) and any(c.isdigit() for c in v)
    return True


def _vote_pick(candidates: list[str], field: str) -> str:
    """Pick the best candidate by frequency, breaking ties by length and order.

    Validates each candidate against the strict per-field rules first.
    """
    valid = [c for c in candidates if _validate_field(field, c)]
    if not valid:
        return ''
    counts: dict[str, int] = {}
    first_seen: dict[str, int] = {}
    for idx, value in enumerate(valid):
        normalized = value.strip()
        counts[normalized] = counts.get(normalized, 0) + 1
        if normalized not in first_seen:
            first_seen[normalized] = idx
    # Sort: highest count first, then earliest seen, then longer (more info)
    ranked = sorted(
        counts.items(),
        key=lambda pair: (-pair[1], first_seen[pair[0]], -len(pair[0]))
    )
    return ranked[0][0] if ranked else ''


def _gather_from_local_ocr(images: list[dict[str, Any]]) -> dict[str, Any]:
    """Run local OCR on every image and merge candidates by vote.

    Returns a dict in the OpenAI vision shape.
    """
    if _local_extract_text_from_image is None:
        return {
            'navn': '', 'adresse': '', 'postnummer': '', 'poststed': '',
            'mobil': '', 'deltakernummer': '', 'annen_merking': '',
            'usikkerhet': ['Lokal OCR (Tesseract) er ikke tilgjengelig på serveren.'],
        }

    if not images:
        raise ValueError('Legg ved minst ett bilde.')

    # Per-field candidate lists from each image
    candidates: dict[str, list[str]] = {
        'navn': [], 'adresse': [], 'postnummer': [], 'poststed': [],
        'mobil': [], 'deltakernummer': [],
    }
    other_markings: list[str] = []
    uncertainties: list[str] = []
    raw_text_blob = ''
    successful_images = 0

    max_images = 6
    for idx, image in enumerate(images[:max_images], start=1):
        filename = str(image.get('filename') or f'bilde-{idx}.jpg')
        content = bytes(image.get('content') or b'')
        try:
            parsed = _local_extract_text_from_image(content, filename=filename, timeout_seconds=45)
        except Exception as exc:
            uncertainties.append(f'Bilde {idx}: kunne ikke leses ({exc}).')
            continue
        successful_images += 1

        text = str((parsed or {}).get('text') or (parsed or {}).get('raw_text') or '')
        raw_text_blob += '\n' + text
        hints = dict((parsed or {}).get('hints') or {})

        # Collect every candidate from this image
        if hints.get('name'):
            candidates['navn'].append(registry.normalize_person_name(hints['name']))
        if hints.get('address'):
            candidates['adresse'].append(str(hints['address']).strip())
        if hints.get('post_place'):
            post_no, post_place = _split_post_place_text(hints['post_place'])
            if post_no:
                candidates['postnummer'].append(post_no)
            if post_place:
                candidates['poststed'].append(post_place)
        if hints.get('phone'):
            candidates['mobil'].append(str(hints['phone']).strip())
        if hints.get('hummer_participant_no'):
            candidates['deltakernummer'].append(str(hints['hummer_participant_no']).strip())

        # Other markings always accumulated
        if hints.get('gear_marker_id'):
            other_markings.append('Merke-ID: ' + str(hints['gear_marker_id']).strip())
        if hints.get('vessel_reg'):
            other_markings.append('Fiskerimerke: ' + str(hints['vessel_reg']).strip())
        if hints.get('radio_call_sign'):
            other_markings.append('Kallesignal: ' + str(hints['radio_call_sign']).strip())
        if hints.get('vessel_name'):
            other_markings.append('Fartøysnavn: ' + str(hints['vessel_name']).strip())

    if not successful_images:
        return {
            'navn': '', 'adresse': '', 'postnummer': '', 'poststed': '',
            'mobil': '', 'deltakernummer': '', 'annen_merking': '',
            'usikkerhet': uncertainties or ['Kunne ikke lese tekst fra noen av bildene.'],
        }

    # Pick best candidate per field with strict validation
    aggregated = {field: _vote_pick(values, field) for field, values in candidates.items()}

    # Supplementary parsing of combined raw text — only for fields still empty
    lines = _clean_lines(raw_text_blob)

    if not aggregated['deltakernummer']:
        candidate = _extract_hummer_no(raw_text_blob)
        if candidate and _validate_field('deltakernummer', candidate):
            aggregated['deltakernummer'] = candidate

    if not aggregated['mobil']:
        m = _extract_mobile(raw_text_blob)
        if m and _validate_field('mobil', m):
            aggregated['mobil'] = m

    if not aggregated['postnummer'] or not aggregated['poststed']:
        for line in lines:
            postnr, sted = _extract_postnr_and_place(line)
            if postnr and _validate_field('postnummer', postnr):
                if not aggregated['postnummer']:
                    aggregated['postnummer'] = postnr
                if sted and _validate_field('poststed', sted) and not aggregated['poststed']:
                    aggregated['poststed'] = sted
                break

    if not aggregated['adresse']:
        for line in lines:
            if _is_label_only(line):
                continue
            if _looks_like_address(line) and not _POSTNR_RE.search(line) and _validate_field('adresse', line.strip()):
                aggregated['adresse'] = line.strip()
                break

    if not aggregated['navn']:
        for line in lines:
            if _is_label_only(line):
                continue
            normalized = registry.normalize_person_name(line)
            if _validate_field('navn', normalized):
                aggregated['navn'] = normalized
                break

    # Sanity-cross-check: a value that "won" in one field shouldn't also be in another
    # (e.g. a phone number accidentally classified as deltakernummer)
    if aggregated['deltakernummer'] and aggregated['mobil']:
        d_digits = ''.join(ch for ch in aggregated['deltakernummer'] if ch.isdigit())
        m_digits = ''.join(ch for ch in aggregated['mobil'] if ch.isdigit())
        if d_digits == m_digits:
            # Same number in both — keep mobile, clear participant
            aggregated['deltakernummer'] = ''
            uncertainties.append('Samme tall ble tolket som både telefon og deltakernummer — beholdt som telefon.')

    # Track confidence: how many images contributed to each field
    confidence_notes = []
    for field, values in candidates.items():
        if values and aggregated[field]:
            valid = [v for v in values if _validate_field(field, v)]
            if len(valid) < successful_images and successful_images > 1:
                # Field detected in only some images — flag for review
                pct = round(100 * len(valid) / successful_images)
                if pct < 60:
                    confidence_notes.append(f'{field}: lest fra {len(valid)} av {successful_images} bilder ({pct} %)')
    if confidence_notes:
        uncertainties.append('Lav konsensus mellom bildene: ' + ', '.join(confidence_notes) + '. Bekreft manuelt.')

    return {
        **aggregated,
        'annen_merking': _merge_unique(other_markings),
        'usikkerhet': uncertainties,
        '_raw_text': raw_text_blob,
        '_line_count': len(lines),
    }


def _enrich_with_registry(result: dict[str, Any]) -> dict[str, Any]:
    """If a deltakernummer was found, look it up in the cached Hummer registry
    (sourced from tableau.fiskeridir.no). Use the registry data as the
    authoritative source for any field we couldn't read from the image.

    Tries the *live* lookup first (which keeps the local cache fresh by
    fetching from tableau.fiskeridir.no). Falls back to the offline-only
    lookup if the live source is unreachable.
    """
    deltakernr = str(result.get('deltakernummer') or '').strip()
    name_hint = str(result.get('navn') or '').strip()

    if not deltakernr and not name_hint:
        return result

    lookup: dict[str, Any] | None = None

    # 1) Try live lookup (refreshes cache from tableau.fiskeridir.no)
    try:
        from .. import live_sources
        lookup = live_sources.lookup_hummer_participant_live(
            participant_no=deltakernr, name=name_hint
        )
    except Exception as exc:
        logger.info('Live hummer-lookup feilet (faller tilbake til lokal): %s', exc)

    # 2) Fallback to offline-only lookup
    if not lookup:
        try:
            lookup = registry.lookup_hummer_participant(participant_no=deltakernr, name=name_hint)
        except Exception as exc:
            logger.warning('Offline registeroppslag feilet: %s', exc)
            return result

    if not lookup or not lookup.get('found'):
        # No exact match — keep what we have but mention the candidates
        candidates = lookup.get('candidates') if isinstance(lookup, dict) else None
        if candidates:
            usikkerhet = list(result.get('usikkerhet') or [])
            usikkerhet.append(
                f'Mulige treff i Fiskeridirektoratets hummerregister ({len(candidates)}). Velg riktig kandidat manuelt.'
            )
            result['usikkerhet'] = usikkerhet
        return result

    person = dict(lookup.get('person') or {})

    # Use registry data for any missing field, AND override fields where
    # we only had a low-confidence OCR read.
    if person.get('name'):
        if not result.get('navn'):
            result['navn'] = registry.normalize_person_name(person['name'])
        # If OCR name and registry name differ but represent the same person, prefer registry casing
    if person.get('hummer_participant_no'):
        result['deltakernummer'] = registry._normalize_hummer_no(person['hummer_participant_no']) or result.get('deltakernummer')
    if person.get('address') and not result.get('adresse'):
        result['adresse'] = person['address']
    if person.get('post_place') and (not result.get('postnummer') or not result.get('poststed')):
        post_no, post_place = _split_post_place_text(person['post_place'])
        if post_no and not result.get('postnummer'):
            result['postnummer'] = post_no
        if post_place and not result.get('poststed'):
            result['poststed'] = post_place
    if person.get('phone') and not result.get('mobil'):
        result['mobil'] = person['phone']

    # Mark this as registry-confirmed
    result['registry_match'] = True
    result['registry_source'] = 'Fiskeridirektoratet — registrerte hummerfiskere'
    if person.get('source_url'):
        result['registry_source_url'] = person['source_url']

    usikkerhet = list(result.get('usikkerhet') or [])
    if person.get('last_registered_year') or person.get('last_registered_display'):
        last = str(person.get('last_registered_display') or person.get('last_registered_year') or '').strip()
        usikkerhet.append(f'Bekreftet i hummerregisteret (sist registrert: {last}).')
    else:
        usikkerhet.append('Bekreftet i Fiskeridirektoratets hummerregister.')
    result['usikkerhet'] = usikkerhet

    return result


def analyze_person_marking_images_local(images: list[dict[str, Any]]) -> dict[str, Any]:
    """Public entry point: local OCR + registry lookup.

    Returns the same JSON shape as the OpenAI vision service plus optional
    'registry_match', 'registry_source', 'registry_source_url' keys.
    """
    if not images:
        raise ValueError('Legg ved minst ett bilde.')

    result = _gather_from_local_ocr(images)
    # Strip diagnostic-only fields before registry lookup
    raw_text = result.pop('_raw_text', '')
    result.pop('_line_count', None)

    result = _enrich_with_registry(result)

    # Final pass: if nothing at all was extracted, give a friendly hint
    has_any_value = any(_clean_string(result.get(field)) for field in ('navn', 'adresse', 'postnummer', 'poststed', 'mobil', 'deltakernummer'))
    if not has_any_value:
        usikkerhet = list(result.get('usikkerhet') or [])
        usikkerhet.insert(
            0,
            'Ingen sikre tekstfelt ble lest fra bildet. Ta et tydelig nærbilde i bedre lys eller fyll ut manuelt.'
        )
        result['usikkerhet'] = usikkerhet
    elif not result.get('registry_match'):
        # Friendly note instead of "Lokal OCR er brukt; kontroller manuelt"
        usikkerhet = list(result.get('usikkerhet') or [])
        if not any('register' in str(u).lower() or 'hummer' in str(u).lower() for u in usikkerhet):
            usikkerhet.append('Felter er lest fra bildet — kontroller dem mot kortet før lagring.')
        result['usikkerhet'] = usikkerhet

    sanitized = _sanitize_result(result)
    # Preserve our extension fields not handled by _sanitize_result
    for key in ('registry_match', 'registry_source', 'registry_source_url'):
        if key in result:
            sanitized[key] = result[key]
    return sanitized


__all__ = ['analyze_person_marking_images_local']
