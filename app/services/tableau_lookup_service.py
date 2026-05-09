"""Oppslag mot Fiskeridirektoratet sin hummerfiskar-liste på Tableau Server.

Dataset: https://tableau.fiskeridir.no/t/Internet/views/Pmeldehummarfiskarargjeldander/Pmeldehummarfiskarar

Strategi:
- Dataen lastes ned daglig (CSV-eksport via Tableau sin standard endepunkt)
  og caches på disk (sqlite-light) slik at hver innsendt kontroll kan
  berikes uten å bombe Tableau med trafikk.
- Oppslag skjer via flere veier (deltakernummer eksakt, navn fuzzy,
  postnummer+poststed, mobil) for å få deltakernummer auto-fyllt fra OCR
  selv når bildet ikke viser nummeret tydelig.
- Hvis Tableau ikke er nåbart, fortsetter alt — bare uten berikelse.
  Servicen kaster ALDRI feil videre opp i request-flyten.
"""
from __future__ import annotations

import csv
import io
import json
import re
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

import httpx

from ..config import settings
from ..logging_setup import get_logger

logger = get_logger(__name__)

# ---------------------------------------------------------------------------
# Konfigurasjon
# ---------------------------------------------------------------------------

TABLEAU_HOST = 'https://tableau.fiskeridir.no'
TABLEAU_VIEW_PATH = '/t/Internet/views/Pmeldehummarfiskarargjeldander/Pmeldehummarfiskarar'
# Tableau CSV-eksport-endepunkt: vanligvis tilgjengelig som .csv-suffix på view-URL
TABLEAU_CSV_URLS = (
    f'{TABLEAU_HOST}{TABLEAU_VIEW_PATH}.csv',
    f'{TABLEAU_HOST}/views/Pmeldehummarfiskarargjeldander/Pmeldehummarfiskarar.csv',
)
TABLEAU_TIMEOUT_SECONDS = 25
TABLEAU_USER_AGENT = 'MinFiskerikontroll/1.8.37 (+https://minfiskerikontroll.no)'

# Cache-fil
CACHE_FILE = Path(getattr(settings, 'data_dir', '.')) / 'tableau_hummer_cache.json'
CACHE_TTL_SECONDS = 24 * 3600  # daglig refresh

# Trådsikker hovedstore i RAM (lastes fra disk ved første bruk)
_lock = threading.Lock()
_cache: dict[str, Any] | None = None


# ---------------------------------------------------------------------------
# Datastruktur
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class HummerParticipant:
    deltakernummer: str
    navn: str
    adresse: str = ''
    postnummer: str = ''
    poststed: str = ''
    mobil: str = ''
    fartoy: str = ''

    def to_dict(self) -> dict[str, str]:
        return {
            'deltakernummer': self.deltakernummer,
            'navn': self.navn,
            'adresse': self.adresse,
            'postnummer': self.postnummer,
            'poststed': self.poststed,
            'mobil': self.mobil,
            'fartoy': self.fartoy,
        }


# ---------------------------------------------------------------------------
# Hjelpere
# ---------------------------------------------------------------------------

_NORM_NAME_RE = re.compile(r'[^a-zæøå0-9]')


def _norm_name(s: str) -> str:
    return _NORM_NAME_RE.sub('', str(s or '').lower().strip())


def _norm_phone(s: str) -> str:
    digits = re.sub(r'\D', '', str(s or ''))
    if digits.startswith('0047') and len(digits) >= 12:
        digits = digits[4:]
    elif digits.startswith('47') and len(digits) == 10:
        digits = digits[2:]
    return digits[-8:] if len(digits) >= 8 else ''


def _norm_postnr(s: str) -> str:
    m = re.search(r'\b(\d{4})\b', str(s or ''))
    return m.group(1) if m else ''


# ---------------------------------------------------------------------------
# Cache-håndtering
# ---------------------------------------------------------------------------

def _load_cache_from_disk() -> dict[str, Any]:
    try:
        if not CACHE_FILE.exists():
            return {'fetched_at': 0, 'rows': []}
        with CACHE_FILE.open('r', encoding='utf-8') as f:
            data = json.load(f)
        if not isinstance(data, dict):
            return {'fetched_at': 0, 'rows': []}
        return {
            'fetched_at': float(data.get('fetched_at') or 0),
            'rows': list(data.get('rows') or []),
        }
    except Exception as exc:
        logger.warning('Kunne ikke lese tableau-cache (%s): %s', CACHE_FILE, exc)
        return {'fetched_at': 0, 'rows': []}


def _save_cache_to_disk(cache: dict[str, Any]) -> None:
    try:
        CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
        with CACHE_FILE.open('w', encoding='utf-8') as f:
            json.dump(cache, f, ensure_ascii=False)
    except Exception as exc:
        logger.warning('Kunne ikke skrive tableau-cache (%s): %s', CACHE_FILE, exc)


def _ensure_cache_loaded() -> dict[str, Any]:
    global _cache
    with _lock:
        if _cache is None:
            _cache = _load_cache_from_disk()
        return _cache


# ---------------------------------------------------------------------------
# Tableau-uthenting
# ---------------------------------------------------------------------------

# Mulige kolonnenavn fra ulike eksport-versjoner
_COL_DELTAKER = ['deltakernummer', 'deltakernr', 'pmelding-id', 'pmeldingsnr', 'fisker-id', 'fisker_id', 'fisker id']
_COL_NAVN = ['navn', 'fiskar', 'fisker', 'name', 'navn fiskar', 'navn fisker']
_COL_ADRESSE = ['adresse', 'adr', 'address', 'gateadresse']
_COL_POSTNR = ['postnummer', 'postnr', 'postnumber', 'postal']
_COL_POSTSTED = ['poststed', 'sted', 'kommune', 'tettsted']
_COL_MOBIL = ['mobil', 'telefon', 'mobiltelefon', 'tlf', 'phone']
_COL_FARTOY = ['fartoy', 'fartøy', 'fartøysnamn', 'båt']


def _find_col(header: list[str], candidates: list[str]) -> int:
    norm = [str(h or '').strip().lower() for h in header]
    for cand in candidates:
        if cand in norm:
            return norm.index(cand)
    # Try fuzzy matching: candidate is contained in header
    for cand in candidates:
        for idx, h in enumerate(norm):
            if cand in h or h in cand:
                return idx
    return -1


def _parse_csv(csv_text: str) -> list[dict[str, str]]:
    """Parse Tableau-CSV til en liste over hummerdeltakere."""
    text = str(csv_text or '').lstrip('\ufeff').strip()
    if not text:
        return []
    # Tableau CSV bruker normalt komma, men kan være semikolon. Sniff.
    try:
        dialect = csv.Sniffer().sniff(text[:4096], delimiters=',;\t')
    except csv.Error:
        dialect = csv.excel
    reader = csv.reader(io.StringIO(text), dialect=dialect)
    try:
        header = next(reader)
    except StopIteration:
        return []
    if not header:
        return []
    idx_deltaker = _find_col(header, _COL_DELTAKER)
    idx_navn = _find_col(header, _COL_NAVN)
    idx_adresse = _find_col(header, _COL_ADRESSE)
    idx_postnr = _find_col(header, _COL_POSTNR)
    idx_poststed = _find_col(header, _COL_POSTSTED)
    idx_mobil = _find_col(header, _COL_MOBIL)
    idx_fartoy = _find_col(header, _COL_FARTOY)

    rows: list[dict[str, str]] = []
    for row in reader:
        if not any((str(c or '').strip() for c in row)):
            continue
        def _g(i: int) -> str:
            return str(row[i]).strip() if 0 <= i < len(row) else ''
        deltaker = _g(idx_deltaker)
        navn = _g(idx_navn)
        if not deltaker and not navn:
            continue
        rows.append({
            'deltakernummer': deltaker,
            'navn': navn,
            'adresse': _g(idx_adresse),
            'postnummer': _norm_postnr(_g(idx_postnr)) or _g(idx_postnr),
            'poststed': _g(idx_poststed),
            'mobil': _g(idx_mobil),
            'fartoy': _g(idx_fartoy),
        })
    return rows


def _fetch_tableau() -> list[dict[str, str]] | None:
    """Forsøker å hente CSV fra Tableau. Returnerer None ved feil."""
    headers = {
        'User-Agent': TABLEAU_USER_AGENT,
        'Accept': 'text/csv, */*;q=0.1',
        'Accept-Language': 'nb-NO,nb;q=0.9,en;q=0.5',
    }
    last_error: Exception | None = None
    for url in TABLEAU_CSV_URLS:
        try:
            with httpx.Client(timeout=TABLEAU_TIMEOUT_SECONDS, follow_redirects=True) as client:
                resp = client.get(url, headers=headers)
                if resp.status_code != 200:
                    logger.info('Tableau %s ga status %s', url, resp.status_code)
                    continue
                if 'text/csv' not in (resp.headers.get('content-type') or '').lower() and not resp.text.strip().startswith(('"', '\xef\xbb\xbf')):
                    # Tableau kan returnere HTML hvis CSV-endpoint ikke er aktivt
                    logger.info('Tableau %s returnerte ikke CSV (content-type=%s)', url, resp.headers.get('content-type'))
                    continue
                rows = _parse_csv(resp.text)
                if rows:
                    logger.info('Tableau-data hentet (%d rader) fra %s', len(rows), url)
                    return rows
        except httpx.HTTPError as exc:
            last_error = exc
            logger.info('Tableau-henting feilet for %s: %s', url, exc)
            continue
    if last_error:
        logger.warning('Kunne ikke hente Tableau-data fra noen URL. Siste feil: %s', last_error)
    return None


def _refresh_if_stale(force: bool = False) -> None:
    cache = _ensure_cache_loaded()
    age = time.time() - float(cache.get('fetched_at') or 0)
    if not force and age < CACHE_TTL_SECONDS and cache.get('rows'):
        return  # fortsatt fersk
    rows = _fetch_tableau()
    if rows is None:
        # Behold gammel cache hvis henting feiler
        return
    with _lock:
        global _cache
        _cache = {'fetched_at': time.time(), 'rows': rows}
        _save_cache_to_disk(_cache)


# ---------------------------------------------------------------------------
# Offentlig API
# ---------------------------------------------------------------------------

def get_all_participants() -> list[dict[str, str]]:
    """Returnerer hele listen (forsøker å oppdatere hvis stale)."""
    try:
        _refresh_if_stale()
    except Exception as exc:
        logger.warning('Tableau-refresh feilet: %s', exc)
    return list((_ensure_cache_loaded().get('rows') or []))


def lookup_by_deltaker(deltakernummer: str) -> dict[str, str] | None:
    """Eksakt oppslag på deltakernummer. None hvis ikke funnet eller cache tom."""
    needle = re.sub(r'[^A-Z0-9-]', '', str(deltakernummer or '').upper())
    if not needle:
        return None
    for row in get_all_participants():
        cand = re.sub(r'[^A-Z0-9-]', '', str(row.get('deltakernummer') or '').upper())
        if cand and cand == needle:
            return dict(row)
    return None


def lookup_best_match(*, navn: str = '', adresse: str = '', postnummer: str = '',
                       poststed: str = '', mobil: str = '') -> dict[str, Any] | None:
    """Finn beste match basert på OCR-funn. Returnerer kandidat + score, eller None.

    Krever minst ett tydelig matchekriterium (mobil eller navn+postnummer).
    """
    rows = get_all_participants()
    if not rows:
        return None

    norm_navn = _norm_name(navn)
    norm_phone = _norm_phone(mobil)
    norm_postnr = _norm_postnr(postnummer)
    norm_poststed = _norm_name(poststed)

    best: dict[str, Any] | None = None
    best_score = 0
    for row in rows:
        score = 0
        reasons = []
        cand_phone = _norm_phone(row.get('mobil') or '')
        cand_navn = _norm_name(row.get('navn') or '')
        cand_postnr = _norm_postnr(row.get('postnummer') or '')
        cand_poststed = _norm_name(row.get('poststed') or '')

        # Mobil match (sterkest signal)
        if norm_phone and cand_phone and norm_phone == cand_phone:
            score += 60
            reasons.append('mobilnummer')

        # Navnematch — eksakt, eller siste-fornavn-overlapp
        if norm_navn and cand_navn:
            if norm_navn == cand_navn:
                score += 50
                reasons.append('navn (eksakt)')
            elif norm_navn in cand_navn or cand_navn in norm_navn:
                score += 30
                reasons.append('navn (delvis)')
            else:
                # Token-overlapp på minst to tokens
                a = set(re.findall(r'[a-zæøå]{3,}', norm_navn))
                b = set(re.findall(r'[a-zæøå]{3,}', cand_navn))
                shared = a & b
                if len(shared) >= 2:
                    score += 25
                    reasons.append(f'navn ({len(shared)} ord overlapp)')

        # Postnummer match (4 siffer er ganske unikt geografisk)
        if norm_postnr and cand_postnr and norm_postnr == cand_postnr:
            score += 18
            reasons.append('postnummer')

        # Poststed match
        if norm_poststed and cand_poststed and (norm_poststed == cand_poststed or norm_poststed in cand_poststed or cand_poststed in norm_poststed):
            score += 10
            reasons.append('poststed')

        if score > best_score:
            best_score = score
            best = {
                'row': dict(row),
                'score': score,
                'reasons': reasons,
            }

    # Krev minimum konfidens — vi vil heller ikke berike enn å sette feil deltakernummer
    if not best or best_score < 40:
        return None
    return best


def force_refresh() -> dict[str, Any]:
    """Manuell trigger — brukes av admin-knapp eller scheduler."""
    _refresh_if_stale(force=True)
    cache = _ensure_cache_loaded()
    return {
        'rows': len(cache.get('rows') or []),
        'fetched_at': cache.get('fetched_at') or 0,
    }
