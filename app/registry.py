from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Iterable

BASE_DIR = Path(__file__).resolve().parent.parent
PEOPLE_PATH = BASE_DIR / 'data' / 'people_registry.json'
HUMMER_PATH = BASE_DIR / 'data' / 'hummer_participants.json'
HUMMER_CACHE_PATH = BASE_DIR / 'data' / 'cache' / 'hummer_registry_cache.json'
OFFICIAL_HUMMER_URL = 'https://www.fiskeridir.no/statistikk-tall-og-analyse/data-og-statistikk-om-turist--og-fritidsfiske/registrerte-hummarfiskarar'

PHONE_RE = re.compile(r'(?<!\d)(?:\+?47\s*)?(\d{8})(?!\d)')
VESSEL_RE = re.compile(r'\b([A-ZÆØÅ]{1,3}[- ]?\d{1,4}(?:[- ]?[A-ZÆØÅ]{1,2})?)\b', re.IGNORECASE)
FISHERIMERKE_RE = re.compile(r'^([A-ZÆØÅ]{1,3}[- ]?[A-ZÆØÅ]{1,3}[- ]?\d{1,4})$', re.IGNORECASE)
RADIO_RE = re.compile(r'\b([A-ZÆØÅ]{2,5}\d{0,3})\b', re.IGNORECASE)
HUMMER_DIRECT_RE = re.compile(r'\b(?:H[- ]?\d{4}[- ]?\d{3}|20\d{5})\b', re.IGNORECASE)
HUMMER_STRICT_RE = re.compile(r'\b(?:H[- ]?\d{4}[- ]?\d{3}|20\d{5}|[A-ZÆØÅ]{2,5}[- ]?[A-ZÆØÅ]{2,5}[- ]?\d{3,4})\b', re.IGNORECASE)
HUMMER_LABELED_RE = re.compile(r'(?:hummer\s*)?deltak(?:er|ar)(?:nr|nummer)?\s*[:#-]?\s*((?:H[- ]?\d{4}[- ]?\d{3})|(?:20\d{5})|(?:[A-ZÆØÅ]{2,5}[- ]?[A-ZÆØÅ]{2,5}[- ]?\d{3,4}))\b', re.IGNORECASE)
POSTCODE_RE = re.compile(r'\b(\d{4})\s+([A-ZÆØÅa-zæøå][A-Za-zÆØÅæøå\- ]{1,40})\b')
POST_PLACE_ONLY_RE = re.compile(r'^\s*(\d{4}\s+[A-ZÆØÅa-zæøå][A-Za-zÆØÅæøå\- ]{1,40})\s*$')
BIRTHDATE_RE = re.compile(r'\b(\d{2}[.\-/]\d{2}[.\-/]\d{4})\b')
STREET_LINE_RE = re.compile(r'^[A-ZÆØÅa-zæøå][A-Za-zÆØÅæøå\-\. ]+\s+\d{1,4}(?:\s*[A-Za-z])?(?:(?:\s*,\s*|\s+)\d{4}\s+[A-ZÆØÅa-zæøå\- ]+)?$')
COMPACT_STREET_RE = re.compile(r'^([A-ZÆØÅa-zæøå][A-Za-zÆØÅæøå\-\. ]{1,40}?)(\d{1,4}[A-Za-z]?)$')
NAME_LINE_RE = re.compile(r'^[A-ZÆØÅ][A-Za-zÆØÅæøå\-]+(?:\s+[A-ZÆØÅ][A-Za-zÆØÅæøå\-]+){1,3}$')
NON_NAME_WORDS = {
    'kv', 'kystvakten', 'hummer', 'deltakarnummer', 'deltakernummer', 'tlf', 'telefon', 'adresse', 'mobil', 'vak',
    'blåse', 'blase', 'flyt', 'dobbe', 'radiokallesignal', 'fiskerimerke', 'registreringsmerke'
}


def _load(path: Path) -> list[dict[str, Any]]:
    try:
        raw = json.loads(path.read_text(encoding='utf-8'))
    except Exception:
        raw = []
    return raw if isinstance(raw, list) else []


def _norm(text: str | None) -> str:
    return ' '.join(str(text or '').strip().lower().split())


def _normalize_person_name(value: str | None) -> str:
    raw = ' '.join(str(value or '').replace('|', ' ').split()).strip(' ,;')
    if ',' in raw:
        last, _, first = raw.partition(',')
        raw = ' '.join([first.strip(), last.strip()]).strip()
    return _norm(raw)


def _name_variants(value: str | None) -> list[str]:
    raw = ' '.join(str(value or '').replace('|', ' ').split()).strip(' ,;')
    if not raw:
        return []
    variants = {_normalize_person_name(raw), _norm(raw)}
    if ',' in raw:
        last, _, first = raw.partition(',')
        variants.add(_norm(last.strip()))
        variants.add(_norm(first.strip()))
    return [v for v in variants if v]


def _compact(text: str | None) -> str:
    return re.sub(r'\W+', '', str(text or '').upper())


def _first(iterable: Iterable[str]) -> str:
    for item in iterable:
        item = str(item or '').strip()
        if item:
            return item
    return ''


def _normalize_lines(text: str) -> list[str]:
    raw_lines = re.split(r'[\r\n]+', str(text or ''))
    lines: list[str] = []
    for line in raw_lines:
        raw = str(line or '').replace('|', ' ').replace(';', ' ')
        clean = ' '.join(raw.replace('\t', ' ').split())
        if not clean:
            continue
        lines.append(clean.strip(' ,;|'))
    if not lines and text:
        merged = ' '.join(str(text).replace('|', ' ').split())
        if merged:
            lines.append(merged)
    return lines


def _normalize_address_line(line: str) -> str:
    candidate = ' '.join(str(line or '').replace('|', ' ').split()).strip(' ,;|-')
    if not candidate:
        return ''
    upper_compact = candidate.upper().replace(' ', '')
    if VESSEL_RE.fullmatch(upper_compact) or FISHERIMERKE_RE.fullmatch(upper_compact) or HUMMER_STRICT_RE.fullmatch(upper_compact):
        return candidate
    match = COMPACT_STREET_RE.match(candidate)
    if match and not POST_PLACE_ONLY_RE.match(candidate):
        street = ' '.join(match.group(1).split())
        number = match.group(2)
        candidate = f'{street} {number}'
    return candidate


def _split_address_post_place(value: str) -> tuple[str, str]:
    text = _normalize_address_line(value)
    if not text:
        return '', ''
    match = POSTCODE_RE.search(text)
    if not match:
        return text, ''
    post = f"{match.group(1)} {match.group(2).strip()}".strip()
    before = text[:match.start()].strip(' ,')
    return before, post


def _normalize_hummer_no(value: str) -> str:
    raw = str(value or '').strip().upper().replace(' ', '')
    if not raw:
        return ''
    raw = raw.replace('–', '-').replace('—', '-')
    if raw.isdigit():
        if len(raw) == 7 and raw.startswith('20'):
            raw = f'H-{raw[:4]}-{raw[4:]}'
        else:
            return ''
    if raw.startswith('H') and not raw.startswith('H-') and re.fullmatch(r'H\d{4}-?\d{3}', raw):
        raw = raw.replace('H', 'H-', 1)
    raw = raw.replace('--', '-')
    match = re.fullmatch(r'([A-ZÆØÅ]{2,5})-?([A-ZÆØÅ]{2,5})-?(\d{3,4})', raw)
    if match:
        raw = f'{match.group(1)}-{match.group(2)}-{match.group(3)}'
    if not HUMMER_STRICT_RE.fullmatch(raw):
        return ''
    return raw


def _clean_name_candidate(value: str | None) -> str:
    parts = [part for part in ' '.join(str(value or '').replace('|', ' ').split()).strip(' ,;|-').split() if part]
    if not parts:
        return ''
    while len(parts) > 2 and len(parts[0]) == 1:
        parts = parts[1:]
    while len(parts) > 2 and len(parts[-1]) == 1:
        parts = parts[:-1]
    cleaned = ' '.join(parts)
    cleaned = re.sub(r'\b([A-ZÆØÅ])$', '', cleaned).strip(' ,;|-')
    return cleaned


def normalize_person_name(value: str) -> str:
    text = _clean_name_candidate(value)
    if not text:
        return ''
    if ',' in text:
        left, right = [part.strip() for part in text.split(',', 1)]
        if left and right:
            return f'{right} {left}'.strip()
    return text


def _is_probable_name(line: str) -> bool:
    line = _clean_name_candidate(line)
    if not NAME_LINE_RE.match(line):
        return False
    words = {w.lower() for w in line.split()}
    if words & NON_NAME_WORDS:
        return False
    return True


def _line_address(lines: list[str]) -> str:
    for idx, line in enumerate(lines):
        if STREET_LINE_RE.match(line) and POSTCODE_RE.search(line):
            return line
        if STREET_LINE_RE.match(line) and idx + 1 < len(lines) and POSTCODE_RE.match(lines[idx + 1]):
            return f'{line}, {lines[idx + 1]}'
    for idx, line in enumerate(lines):
        if STREET_LINE_RE.match(line):
            return line
        if POSTCODE_RE.match(line) and idx > 0 and STREET_LINE_RE.match(lines[idx - 1]):
            return f'{lines[idx - 1]}, {line}'
    return ''


def _extract_labeled_value(lines: list[str], labels: tuple[str, ...]) -> str:
    patterns = [re.compile(r'^(?:' + label + r')\s*[:#-]?\s*(.+)$', re.IGNORECASE) for label in labels]
    for line in lines:
        for pattern in patterns:
            match = pattern.match(line)
            if match:
                value = ' '.join(match.group(1).split())
                if value:
                    return value
    return ''


def extract_tag_hints(tag_text: str) -> dict[str, str]:
    text = str(tag_text or '').strip()
    out = {
        'phone': '',
        'vessel_reg': '',
        'radio_call_sign': '',
        'hummer_participant_no': '',
        'address': '',
        'post_place': '',
        'birthdate': '',
        'name': '',
    }
    if not text:
        return out

    lines = [_normalize_address_line(line) for line in _normalize_lines(text)]
    joined = ' | '.join(lines)

    def _pick_phone(raw: str) -> str:
        pm = PHONE_RE.search(str(raw or '').replace(' ', '')) or PHONE_RE.search(str(raw or ''))
        return pm.group(1) if pm else ''

    labeled_phone = _extract_labeled_value(lines, ('mobil(?:nummer)?', 'telefon', 'tlf'))
    out['phone'] = _pick_phone(labeled_phone) or _pick_phone(joined)

    labeled_hummer = HUMMER_LABELED_RE.search(joined)
    direct_hummer = HUMMER_DIRECT_RE.search(joined.upper())
    labeled_hummer_text = _extract_labeled_value(lines, (r'hummer\s*deltak(?:er|ar)(?:nr|nummer)?', 'deltak(?:er|ar)(?:nr|nummer)?'))
    if labeled_hummer:
        out['hummer_participant_no'] = _normalize_hummer_no(labeled_hummer.group(1))
    elif labeled_hummer_text:
        out['hummer_participant_no'] = _normalize_hummer_no(labeled_hummer_text)
    elif direct_hummer:
        out['hummer_participant_no'] = _normalize_hummer_no(direct_hummer.group(0))

    labeled_birthdate = _extract_labeled_value(lines, ('fødselsdato', 'fodselsdato', 'f[øo]dt'))
    birthdate_match = BIRTHDATE_RE.search(labeled_birthdate or joined)
    if birthdate_match:
        out['birthdate'] = birthdate_match.group(1).replace('-', '.').replace('/', '.')

    labeled_name = _extract_labeled_value(lines, ('navn', 'eier', 'ansvarlig', 'skipper'))
    if labeled_name:
        labeled_name = normalize_person_name(labeled_name)
        if _is_probable_name(labeled_name):
            out['name'] = labeled_name

    labeled_post = _extract_labeled_value(lines, ('poststed', r'postnr(?:\.| og sted)?', 'postnummer'))
    if labeled_post and POSTCODE_RE.search(labeled_post):
        pm = POSTCODE_RE.search(labeled_post)
        out['post_place'] = f"{pm.group(1)} {pm.group(2).strip()}"

    labeled_address = _extract_labeled_value(lines, ('adresse',))
    if labeled_address:
        addr, post = _split_address_post_place(labeled_address)
        out['address'] = addr
        if post and not out['post_place']:
            out['post_place'] = post

    for idx, raw_line in enumerate(lines):
        line = _normalize_address_line(raw_line)
        if not line:
            continue
        upper_line = line.upper().replace(' ', '')
        vessel_full = FISHERIMERKE_RE.fullmatch(upper_line) or VESSEL_RE.fullmatch(upper_line) or FISHERIMERKE_RE.fullmatch(line.upper()) or VESSEL_RE.fullmatch(line.upper())
        if vessel_full and not out['vessel_reg']:
            candidate = vessel_full.group(1).replace(' ', '').upper()
            if candidate != _compact(out['hummer_participant_no']) and not POST_PLACE_ONLY_RE.match(line):
                out['vessel_reg'] = candidate
                continue
        if not out['post_place'] and POST_PLACE_ONLY_RE.match(line):
            out['post_place'] = line
            continue
        cleaned_name = _clean_name_candidate(line)
        if not out['name'] and _is_probable_name(cleaned_name):
            out['name'] = normalize_person_name(cleaned_name)
            continue
        if not out['address'] and STREET_LINE_RE.match(line) and not (VESSEL_RE.fullmatch(line.upper()) or FISHERIMERKE_RE.fullmatch(line.upper())):
            addr, post = _split_address_post_place(line)
            out['address'] = addr or line
            if post and not out['post_place']:
                out['post_place'] = post
            elif idx + 1 < len(lines) and POST_PLACE_ONLY_RE.match(lines[idx + 1]):
                out['post_place'] = lines[idx + 1]
            continue
        if not out['address'] and COMPACT_STREET_RE.match(line) and not (VESSEL_RE.fullmatch(line.upper()) or FISHERIMERKE_RE.fullmatch(line.upper())):
            addr, post = _split_address_post_place(line)
            out['address'] = addr or _normalize_address_line(line)
            if post and not out['post_place']:
                out['post_place'] = post
            elif idx + 1 < len(lines) and POST_PLACE_ONLY_RE.match(lines[idx + 1]):
                out['post_place'] = lines[idx + 1]
            continue
        if not out['vessel_reg']:
            vessel_match = FISHERIMERKE_RE.fullmatch(line.upper()) or VESSEL_RE.fullmatch(line.upper()) or FISHERIMERKE_RE.search(line.upper()) or VESSEL_RE.search(line.upper())
            if vessel_match:
                candidate = vessel_match.group(1).replace(' ', '').upper()
                if candidate != _compact(out['hummer_participant_no']) and not POST_PLACE_ONLY_RE.match(line):
                    out['vessel_reg'] = candidate
                    continue
        if not out['radio_call_sign'] and any(token in line.upper() for token in ['RADIO', 'CALL', 'KALLESIGNAL']):
            radio_match = RADIO_RE.search(line.upper())
            if radio_match:
                candidate = radio_match.group(1).upper()
                if candidate not in {out['vessel_reg'], _compact(out['hummer_participant_no'])} and not candidate.isdigit():
                    out['radio_call_sign'] = candidate

    if not out['name']:
        fragments = re.findall(r'([A-ZÆØÅ][A-Za-zÆØÅæøå\-]+(?:\s+[A-ZÆØÅ][A-Za-zÆØÅæøå\-]+){1,3})', joined)
        for frag in fragments:
            candidate = _clean_name_candidate(frag)
            if out['address'] and candidate in out['address']:
                continue
            if _is_probable_name(candidate):
                out['name'] = candidate
                break

    if out['address']:
        out['address'] = re.sub(r'\b(?:tlf|telefon|mobil)[:#-]?\s*\+?47?\s*\d[\d\s]{6,}\b', '', out['address'], flags=re.I)
        out['address'] = out['address'].replace(out.get('hummer_participant_no') or '', '').strip(' ,;|')
        if out['name'] and out['address'].lower().startswith(out['name'].lower()):
            out['address'] = out['address'][len(out['name']):].lstrip(' ,;')

    if out['post_place'] and out['name'] and out['post_place'].lower().startswith(out['name'].lower()):
        out['post_place'] = ''

    if out['hummer_participant_no'] and POSTCODE_RE.search(out['hummer_participant_no']):
        out['hummer_participant_no'] = ''

    return out


def infer_last_registered(participant_no: str = '', fallback: str = '') -> str:
    participant_no = str(participant_no or '').strip()
    if fallback:
        return str(fallback)
    match = re.search(r'(20\d{2})', participant_no)
    return match.group(1) if match else ''


def format_last_registered(value: str = '') -> str:
    value = str(value or '').strip()
    if not value:
        return ''
    if value.isdigit() and len(value) == 4:
        return f'{value}-sesongen'
    return value


def _normalize_hummer_row(row: dict[str, Any], *, source: str = '', source_url: str = OFFICIAL_HUMMER_URL) -> dict[str, Any]:
    item = dict(row or {})
    participant_no = _normalize_hummer_no(item.get('participant_no') or item.get('hummer_participant_no') or '')
    if participant_no:
        item['participant_no'] = participant_no
    name = normalize_person_name(item.get('name') or '')
    if name:
        item['name'] = name
    last_registered = infer_last_registered(
        participant_no,
        item.get('last_registered_year') or item.get('last_registered') or item.get('registered_year') or '',
    )
    if last_registered:
        item['last_registered'] = last_registered
        item['last_registered_year'] = last_registered
        item['last_registered_display'] = format_last_registered(last_registered)
        item['registered_date_display'] = item['last_registered_display']
    if source and not item.get('source'):
        item['source'] = source
    if source_url and not item.get('source_url'):
        item['source_url'] = source_url
    return item


def _load_hummer_rows() -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()

    def add_many(raw_rows: Iterable[dict[str, Any]], *, source: str) -> None:
        for raw in raw_rows or []:
            item = _normalize_hummer_row(raw, source=source)
            key = (_compact(item.get('participant_no')), _normalize_person_name(item.get('name')))
            if not any(key):
                continue
            if key in seen:
                continue
            seen.add(key)
            rows.append(item)

    add_many(_load(HUMMER_PATH), source='Lokal hummerliste')
    add_many(_load(HUMMER_CACHE_PATH), source='Fiskeridirektoratet - registrerte hummarfiskarar')
    return rows


def _score_hummer_row(row: dict[str, Any], participant_no: str = '', name: str = '') -> int:
    score = 0
    p = _compact(_normalize_hummer_no(participant_no))
    name_variants = _name_variants(name)
    if p and _compact(row.get('participant_no')) == p:
        score += 120
    row_name = _normalize_person_name(row.get('name'))
    raw_row_name = _norm(row.get('name'))
    if name_variants:
        if row_name in name_variants or raw_row_name in name_variants:
            score += 90
        elif any(variant and (variant in row_name or variant in raw_row_name) for variant in name_variants):
            score += 35
    return score


def search_hummer_participants(participant_no: str = '', name: str = '', *, limit: int = 20) -> list[dict[str, Any]]:
    rows = _load_hummer_rows()
    scored: list[tuple[int, dict[str, Any]]] = []
    for row in rows:
        score = _score_hummer_row(row, participant_no=participant_no, name=name)
        if score:
            scored.append((score, row))
    scored.sort(key=lambda pair: (-pair[0], _normalize_person_name(pair[1].get('name')), _compact(pair[1].get('participant_no'))))
    return [dict(item) for _, item in scored[:max(1, limit)]]


def lookup_hummer_participant(participant_no: str = '', name: str = '') -> dict[str, Any]:
    matches = search_hummer_participants(participant_no=participant_no, name=name, limit=25)
    if not matches:
        return {'found': False, 'message': 'Ingen treff i lokal eller hurtigbufret hummerdeltakerliste.', 'candidates': []}

    normalized_participant = _compact(_normalize_hummer_no(participant_no))
    normalized_name = _normalize_person_name(name)
    normalized_raw_name = _norm(name)

    exact = None
    for row in matches:
        participant_match = bool(normalized_participant and _compact(row.get('participant_no')) == normalized_participant)
        row_name = _normalize_person_name(row.get('name'))
        row_raw_name = _norm(row.get('name'))
        name_match = bool(normalized_name and (row_name == normalized_name or row_raw_name == normalized_raw_name))
        if participant_match or name_match:
            exact = row
            break

    if not exact:
        return {
            'found': False,
            'message': 'Mulige treff i hummerregisteret. Velg kandidat fra listen.',
            'candidates': matches[:10],
        }

    item = _normalize_hummer_row(exact)
    return {
        'found': True,
        'person': item,
        'candidates': matches[:10],
        'message': 'Treff i lokal eller hurtigbufret hummerdeltakerliste.',
    }


def _score_person(row: dict[str, Any], *, phone: str = '', vessel_reg: str = '', radio_call_sign: str = '', name: str = '', tag_text: str = '', hummer_participant_no: str = '') -> int:
    score = 0
    row_name = _norm(row.get('name'))
    aliases = [_norm(alias) for alias in (row.get('aliases') or [])]
    tags = [_norm(tag) for tag in (row.get('tag_samples') or [])]

    if phone and str(row.get('phone') or '').strip() == phone:
        score += 120
    if vessel_reg and _compact(row.get('vessel_reg')) == _compact(vessel_reg):
        score += 110
    if radio_call_sign and _compact(row.get('radio_call_sign')) == _compact(radio_call_sign):
        score += 110
    if hummer_participant_no and _compact(row.get('hummer_participant_no')) == _compact(_normalize_hummer_no(hummer_participant_no)):
        score += 120
    if name:
        if name == row_name:
            score += 90
        elif any(name == alias for alias in aliases):
            score += 75
        elif name in row_name:
            score += 45
        elif any(name in alias for alias in aliases):
            score += 35
    tag_norm = _norm(tag_text)
    if tag_norm:
        if any(tag_norm in sample for sample in tags):
            score += 25
        if tag_norm in row_name:
            score += 20
    return score


def search_people(phone: str = '', vessel_reg: str = '', radio_call_sign: str = '', name: str = '', tag_text: str = '', hummer_participant_no: str = '', limit: int = 6) -> list[dict[str, Any]]:
    rows = _load(PEOPLE_PATH)
    hints = extract_tag_hints(tag_text)
    phone = (phone or hints.get('phone') or '').strip()
    vessel_reg = (vessel_reg or hints.get('vessel_reg') or '').strip()
    radio_call_sign = (radio_call_sign or hints.get('radio_call_sign') or '').strip()
    name = _norm(name or hints.get('name') or '')
    hummer_participant_no = _normalize_hummer_no(hummer_participant_no or hints.get('hummer_participant_no') or '')

    scored: list[tuple[int, dict[str, Any]]] = []
    for row in rows:
        score = _score_person(
            row,
            phone=phone,
            vessel_reg=vessel_reg,
            radio_call_sign=radio_call_sign,
            name=name,
            tag_text=tag_text,
            hummer_participant_no=hummer_participant_no,
        )
        if score > 0:
            item = dict(row)
            item['source'] = 'Lokal person-/fartøyliste'
            item['match_score'] = score
            scored.append((score, item))

    scored.sort(key=lambda pair: (-pair[0], _norm(pair[1].get('name'))))
    return [row for _, row in scored[:limit]]


def lookup_person(phone: str = '', vessel_reg: str = '', radio_call_sign: str = '', name: str = '', tag_text: str = '', hummer_participant_no: str = '') -> dict[str, Any] | None:
    matches = search_people(phone=phone, vessel_reg=vessel_reg, radio_call_sign=radio_call_sign, name=name, tag_text=tag_text, hummer_participant_no=hummer_participant_no, limit=1)
    if not matches:
        return None
    out = dict(matches[0])
    out['match_reason'] = _first([
        'telefon' if phone and str(out.get('phone') or '').strip() == phone else '',
        'registrering' if vessel_reg and _compact(out.get('vessel_reg')) == _compact(vessel_reg) else '',
        'radiokallesignal' if radio_call_sign and _compact(out.get('radio_call_sign')) == _compact(radio_call_sign) else '',
        'hummerdeltakernummer' if hummer_participant_no and _compact(out.get('hummer_participant_no')) == _compact(hummer_participant_no) else '',
        'navn' if name and name in _norm(out.get('name')) else '',
        'OCR-hint' if tag_text else '',
    ]) or 'registertreff'
    return out
