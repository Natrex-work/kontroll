"""Hummerfisker-register: oppslag mot Fiskeridirektoratets påmelde-liste.

Strategi: Forsøker å hente offentlig CSV-eksport fra Tableau-visningen
`Pmeldehummarfiskarar`. Resultatet caches i SQLite. Oppslag fra OCR-flyten
slår direkte mot lokal cache, så det går lynraskt og fungerer offline.

Hvis Tableau-eksport ikke er tilgjengelig (auth, format-endring, eller
CORS), kan admin laste opp en CSV manuelt via /admin/hummerfiskere.
"""
from __future__ import annotations

import csv
import io
import os
import threading
import time
from typing import Any, Iterator

import httpx

from .. import db
from ..logging_setup import get_logger

logger = get_logger(__name__)

# ---------------------------------------------------------------------------
# Konstanter
# ---------------------------------------------------------------------------

TABLEAU_BASE = 'https://tableau.fiskeridir.no'
WORKBOOK = 'Pmeldehummarfiskarargjeldander'
VIEW = 'Pmeldehummarfiskarar'

# Mulige eksport-URL-er som forsøkes i rekkefølge.
# Tableau Server støtter typisk .csv-suffix på views når visningen er
# offentlig. Vi forsøker også med /t/Internet/-prefiks som original URL har.
EXPORT_URLS = [
    f'{TABLEAU_BASE}/t/Internet/views/{WORKBOOK}/{VIEW}.csv?:embed=y&:showVizHome=no&:format=csv',
    f'{TABLEAU_BASE}/views/{WORKBOOK}/{VIEW}.csv?:embed=y&:showVizHome=no',
    f'{TABLEAU_BASE}/t/Internet/views/{WORKBOOK}/{VIEW}/data?:embed=y',
]

FETCH_TIMEOUT_SECONDS = 30
MIN_REFETCH_INTERVAL_SECONDS = 12 * 3600  # 12 timer
USER_AGENT = 'MinFiskerikontroll/1.8.37 (kontroll-bruker; +https://minfiskerikontroll.no)'

# ---------------------------------------------------------------------------
# Internal: column normalisation
# ---------------------------------------------------------------------------

# Tableau-eksporter kan ha varierende kolonnenavn. Vi prøver å matche
# det første som ser ut som riktig felt.
DELTAKERNR_KEYS = ['deltakernummer', 'deltakernr', 'deltaker_nr', 'deltager nr', 'deltaker', 'medlemsnr', 'nummer']
NAVN_KEYS = ['navn', 'fisker', 'eier', 'name']
ADRESSE_KEYS = ['adresse', 'gateadresse', 'street']
POSTNUMMER_KEYS = ['postnr', 'postnummer', 'zip']
POSTSTED_KEYS = ['poststed', 'sted', 'by']
MOBIL_KEYS = ['mobil', 'tlf', 'telefon', 'phone']
FARTOY_KEYS = ['fartøy', 'fartoy', 'båt', 'bat']
FARTOY_REG_KEYS = ['regnr', 'merke', 'kjenne', 'fartøymerke', 'fartoymerke']


def _norm_key(s: str) -> str:
    return ''.join(ch for ch in str(s or '').lower().strip() if ch.isalnum() or ch == ' ').strip()


def _match_field(row: dict[str, str], candidates: list[str]) -> str:
    """Find the first matching column whose normalised key contains any candidate."""
    norm_row = {_norm_key(k): v for k, v in row.items() if k}
    for cand in candidates:
        c = _norm_key(cand)
        for k, v in norm_row.items():
            if c in k:
                value = str(v or '').strip()
                if value and value.lower() not in {'null', 'none', 'na', '%null%'}:
                    return value
    return ''


def _parse_csv_rows(text: str) -> list[dict[str, str]]:
    """Parse CSV text robustly. Tableau exports may use ';' or ',' as separator."""
    if not text or not text.strip():
        return []
    # Sniff dialect
    sample = text[:2048]
    try:
        dialect = csv.Sniffer().sniff(sample, delimiters=',;\t')
    except csv.Error:
        # Default to comma
        class _D:
            delimiter = ','
            quotechar = '"'
            doublequote = True
            skipinitialspace = True
            lineterminator = '\n'
            quoting = csv.QUOTE_MINIMAL
        dialect = _D()  # type: ignore[assignment]
    reader = csv.DictReader(io.StringIO(text), dialect=dialect)
    rows: list[dict[str, str]] = []
    for raw in reader:
        rows.append({(k or '').strip(): (v or '').strip() for k, v in raw.items()})
    return rows


def _row_to_record(row: dict[str, str]) -> dict[str, str] | None:
    """Convert a CSV row to a normalised hummerfisker record. Returns None if no deltakernummer."""
    deltakernr = ''.join(ch for ch in _match_field(row, DELTAKERNR_KEYS) if ch.isdigit())
    if not deltakernr:
        return None
    return {
        'deltakernummer': deltakernr,
        'navn': _match_field(row, NAVN_KEYS),
        'adresse': _match_field(row, ADRESSE_KEYS),
        'postnummer': _match_field(row, POSTNUMMER_KEYS),
        'poststed': _match_field(row, POSTSTED_KEYS),
        'mobil': _match_field(row, MOBIL_KEYS),
        'fartoy_navn': _match_field(row, FARTOY_KEYS),
        'fartoy_reg': _match_field(row, FARTOY_REG_KEYS),
    }


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

_fetch_lock = threading.Lock()
_last_fetch_attempt = 0.0


def fetch_register_from_tableau() -> tuple[bool, int, str]:
    """Try to download and parse the public Tableau export.
    Returns (success, row_count, error_message).
    """
    headers = {
        'User-Agent': USER_AGENT,
        'Accept': 'text/csv,application/csv,text/plain;q=0.9,*/*;q=0.5',
        'Accept-Language': 'nb-NO,nb;q=0.9,no;q=0.8,en;q=0.5',
    }
    last_error = ''
    for url in EXPORT_URLS:
        try:
            logger.info('Hummerfisker-register: prøver %s', url)
            with httpx.Client(timeout=FETCH_TIMEOUT_SECONDS, follow_redirects=True) as client:
                resp = client.get(url, headers=headers)
            if resp.status_code != 200:
                last_error = f'HTTP {resp.status_code} fra {url}'
                continue
            content_type = (resp.headers.get('content-type') or '').lower()
            text = resp.text
            # Avvis HTML-svar (Tableau gir login-side hvis ikke offentlig)
            if 'text/html' in content_type or text.lstrip().lower().startswith('<!doctype') or '<html' in text[:1024].lower():
                last_error = 'Tableau svarte med HTML (ikke CSV) — visningen krever sannsynligvis innlogging eller annen autorisasjon.'
                continue
            rows = _parse_csv_rows(text)
            if not rows:
                last_error = 'CSV-eksporten var tom eller hadde ukjent format.'
                continue
            inserted = 0
            for row in rows:
                rec = _row_to_record(row)
                if not rec:
                    continue
                if db.upsert_hummerfisker(rec, source='fiskeridir'):
                    inserted += 1
            row_count = db.count_hummerfiskere()
            db.set_hummerfiskere_meta(success=True, row_count=row_count)
            logger.info('Hummerfisker-register oppdatert. Totalt %d rader (%d nye/endrede).', row_count, inserted)
            return True, row_count, ''
        except httpx.HTTPError as exc:
            last_error = f'Nettverksfeil mot {url}: {exc}'
            continue
        except Exception as exc:
            last_error = f'Uventet feil ved henting fra {url}: {exc}'
            logger.exception('Uventet feil ved hummerfisker-fetch')
            continue
    db.set_hummerfiskere_meta(success=False, error=last_error or 'Ingen URL ga gyldig CSV.', row_count=db.count_hummerfiskere())
    return False, db.count_hummerfiskere(), last_error or 'Ingen URL ga gyldig CSV.'


def maybe_refresh_async() -> None:
    """Trigger a background fetch if cache is stale and not already in flight.

    Caller does not block — this returns immediately. Used by the lookup
    endpoint so first user of the day triggers a refresh.
    """
    global _last_fetch_attempt
    with _fetch_lock:
        now = time.time()
        if now - _last_fetch_attempt < MIN_REFETCH_INTERVAL_SECONDS:
            return
        meta = db.get_hummerfiskere_meta()
        last_success = meta.get('last_fetch_success_at') or ''
        # If we have data and it's fresh, skip
        if meta.get('row_count') and last_success:
            try:
                from datetime import datetime, timezone
                ts = datetime.strptime(str(last_success), '%Y-%m-%dT%H:%M:%SZ').replace(tzinfo=timezone.utc)
                age = (datetime.now(timezone.utc) - ts).total_seconds()
                if age < MIN_REFETCH_INTERVAL_SECONDS:
                    return
            except Exception:
                pass
        _last_fetch_attempt = now

    def _run():
        try:
            fetch_register_from_tableau()
        except Exception as exc:
            logger.warning('Hummerfisker bakgrunns-fetch feilet: %s', exc)

    thread = threading.Thread(target=_run, name='hummerfisker-fetch', daemon=True)
    thread.start()


def lookup(deltakernummer: str) -> dict[str, Any] | None:
    """Slå opp et deltakernummer i lokal cache. Returnerer dict eller None."""
    return db.lookup_hummerfisker(deltakernummer)


def import_csv_text(text: str, *, source: str = 'manual_upload') -> tuple[int, int]:
    """Parse and import a CSV text. Returns (rows_imported, rows_changed)."""
    rows = _parse_csv_rows(text)
    if not rows:
        return 0, 0
    imported = 0
    changed = 0
    for row in rows:
        rec = _row_to_record(row)
        if not rec:
            continue
        imported += 1
        if db.upsert_hummerfisker(rec, source=source):
            changed += 1
    db.set_hummerfiskere_meta(success=True, row_count=db.count_hummerfiskere())
    return imported, changed
