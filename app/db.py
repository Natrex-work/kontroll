from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, Optional

from .config import settings

DB_PATH = settings.db_path

USER_ROLES = ('admin', 'investigator')
CASE_STATUSES = ('Utkast', 'Anmeldt', 'Anmeldt og sendt', 'Ingen reaksjon', 'Advarsel')
CASE_BASIS = ('patruljeobservasjon', 'tips')
INVESTIGATOR_PERMISSION_OPTIONS = ('kv_kontroll', 'kart', 'regelverk')
ADMIN_PERMISSION_OPTIONS = ('user_admin', 'control_admin')
USER_PERMISSION_OPTIONS = INVESTIGATOR_PERMISSION_OPTIONS + ADMIN_PERMISSION_OPTIONS
USER_PERMISSION_LABELS = {
    'kv_kontroll': 'Kontroll',
    'kart': 'Kart og områder',
    'regelverk': 'Regelverk',
    'user_admin': 'Brukerstyring',
    'control_admin': 'Slette/gjenopprette kontroller',
}
DEFAULT_INVESTIGATOR_PERMISSIONS = list(INVESTIGATOR_PERMISSION_OPTIONS)
DEFAULT_ADMIN_PERMISSIONS = list(USER_PERMISSION_OPTIONS)


class CaseConflictError(Exception):
    """Raised when a client tries to save an older version of a case."""

    def __init__(self, *, current_version: int, current_updated_at: str):
        super().__init__('Saken er endret et annet sted.')
        self.current_version = int(current_version or 1)
        self.current_updated_at = str(current_updated_at or '')


def utcnow_iso() -> str:
    return datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')


def localnow_form() -> str:
    return datetime.now().strftime('%Y-%m-%dT%H:%M')


def dict_factory(cursor: sqlite3.Cursor, row: tuple[Any, ...]) -> Dict[str, Any]:
    return {col[0]: row[idx] for idx, col in enumerate(cursor.description)}


def _permission_order(permission: str) -> int:
    try:
        return USER_PERMISSION_OPTIONS.index(permission)
    except ValueError:
        return len(USER_PERMISSION_OPTIONS)


def normalize_permissions(role: str, value: Any) -> list[str]:
    role = str(role or 'investigator').strip() or 'investigator'
    if role == 'admin':
        return list(DEFAULT_ADMIN_PERMISSIONS)

    allowed_set = set(INVESTIGATOR_PERMISSION_OPTIONS)
    raw_items: list[str] = []
    if isinstance(value, str):
        raw = value.strip()
        if raw:
            try:
                parsed = json.loads(raw)
                if isinstance(parsed, list):
                    raw_items = [str(item).strip() for item in parsed]
            except Exception:
                raw_items = [part.strip() for part in raw.split(',')]
    elif isinstance(value, (list, tuple, set)):
        raw_items = [str(item).strip() for item in value]

    cleaned: list[str] = []
    seen: set[str] = set()
    for item in raw_items:
        if item in allowed_set and item not in seen:
            cleaned.append(item)
            seen.add(item)

    if not cleaned:
        cleaned = list(DEFAULT_INVESTIGATOR_PERMISSIONS)

    cleaned.sort(key=_permission_order)
    return cleaned


def permissions_to_json(role: str, value: Any) -> str:
    return json.dumps(normalize_permissions(role, value), ensure_ascii=False)


def get_user_permissions(user_row: Optional[Dict[str, Any]]) -> list[str]:
    if not user_row:
        return []
    return normalize_permissions(str(user_row.get('role') or 'investigator'), user_row.get('permissions_json'))


def user_has_permission(user_row: Optional[Dict[str, Any]], permission: str) -> bool:
    return permission in get_user_permissions(user_row)


@contextmanager
def get_conn() -> Iterable[sqlite3.Connection]:
    conn = sqlite3.connect(DB_PATH, timeout=30)
    conn.row_factory = dict_factory
    conn.execute('PRAGMA foreign_keys = ON')
    conn.execute('PRAGMA busy_timeout = 10000')
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def _table_columns(conn: sqlite3.Connection, table_name: str) -> set[str]:
    cur = conn.execute(f'PRAGMA table_info({table_name})')
    return {str(row['name']) for row in cur.fetchall()}


def _ensure_column(conn: sqlite3.Connection, table_name: str, column_name: str, ddl: str) -> None:
    columns = _table_columns(conn, table_name)
    if column_name not in columns:
        conn.execute(f'ALTER TABLE {table_name} ADD COLUMN {ddl}')


def init_db() -> None:
    with get_conn() as conn:
        try:
            conn.execute('PRAGMA journal_mode = WAL')
            conn.execute('PRAGMA synchronous = NORMAL')
        except Exception:
            pass
        conn.executescript(
            '''
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                email TEXT NOT NULL UNIQUE,
                full_name TEXT NOT NULL,
                password_hash TEXT NOT NULL,
                role TEXT NOT NULL CHECK (role IN ('admin', 'investigator')),
                address TEXT,
                phone TEXT,
                vessel_affiliation TEXT,
                permissions_json TEXT NOT NULL DEFAULT '[]',
                last_complainant_name TEXT,
                last_witness_name TEXT,
                case_prefix TEXT,
                active INTEGER NOT NULL DEFAULT 1,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS cases (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                case_number TEXT NOT NULL UNIQUE,
                created_by INTEGER NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
                investigator_name TEXT NOT NULL,
                complainant_name TEXT,
                witness_name TEXT,
                case_basis TEXT NOT NULL DEFAULT 'patruljeobservasjon',
                basis_source_name TEXT,
                basis_details TEXT,
                control_type TEXT,
                fishery_type TEXT,
                species TEXT,
                gear_type TEXT,
                start_time TEXT,
                end_time TEXT,
                location_name TEXT,
                latitude REAL,
                longitude REAL,
                area_status TEXT,
                area_name TEXT,
                suspect_name TEXT,
                suspect_phone TEXT,
                suspect_birthdate TEXT,
                suspect_address TEXT,
                suspect_post_place TEXT,
                lookup_text TEXT,
                vessel_name TEXT,
                vessel_reg TEXT,
                radio_call_sign TEXT,
                gear_marker_id TEXT,
                notes TEXT,
                hearing_text TEXT,
                seizure_notes TEXT,
                summary TEXT,
                findings_json TEXT NOT NULL DEFAULT '[]',
                source_snapshot_json TEXT NOT NULL DEFAULT '[]',
                crew_json TEXT NOT NULL DEFAULT '[]',
                external_actors_json TEXT NOT NULL DEFAULT '[]',
                persons_json TEXT NOT NULL DEFAULT '[]',
                hummer_participant_no TEXT,
                hummer_last_registered TEXT,
                observed_gear_count INTEGER,
                complaint_override TEXT,
                own_report_override TEXT,
                interview_report_override TEXT,
                seizure_report_override TEXT,
                interview_sessions_json TEXT NOT NULL DEFAULT '[]',
                seizure_reports_json TEXT NOT NULL DEFAULT '[]',
                interview_not_conducted INTEGER NOT NULL DEFAULT 0,
                interview_not_conducted_reason TEXT,
                interview_guidance_text TEXT,
                complainant_signature TEXT,
                witness_signature TEXT,
                investigator_signature TEXT,
                suspect_signature TEXT,
                status TEXT NOT NULL DEFAULT 'Utkast',
                last_generated_pdf TEXT,
                last_previewed_at TEXT,
                deleted_at TEXT,
                deleted_by INTEGER REFERENCES users(id) ON DELETE SET NULL,
                version INTEGER NOT NULL DEFAULT 1,
                updated_by INTEGER REFERENCES users(id) ON DELETE SET NULL,
                last_client_mutation_id TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS evidence (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                case_id INTEGER NOT NULL REFERENCES cases(id) ON DELETE CASCADE,
                filename TEXT NOT NULL,
                original_filename TEXT NOT NULL,
                caption TEXT,
                mime_type TEXT,
                finding_key TEXT,
                law_text TEXT,
                violation_reason TEXT,
                seizure_ref TEXT,
                file_size INTEGER,
                sha256 TEXT,
                sync_state TEXT NOT NULL DEFAULT 'synced',
                device_id TEXT,
                local_media_id TEXT,
                server_received_at TEXT,
                display_order INTEGER,
                created_at TEXT NOT NULL,
                created_by INTEGER REFERENCES users(id) ON DELETE SET NULL
            );

            CREATE TABLE IF NOT EXISTS audit_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                actor_user_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
                action TEXT NOT NULL,
                entity_type TEXT NOT NULL,
                entity_id TEXT,
                details_json TEXT,
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS case_counters (
                prefix TEXT NOT NULL,
                year TEXT NOT NULL,
                next_number INTEGER NOT NULL DEFAULT 1,
                updated_at TEXT NOT NULL,
                PRIMARY KEY(prefix, year)
            );

            CREATE INDEX IF NOT EXISTS idx_cases_created_by_deleted_updated ON cases(created_by, deleted_at, updated_at);
            CREATE INDEX IF NOT EXISTS idx_cases_deleted_updated ON cases(deleted_at, updated_at);
            CREATE INDEX IF NOT EXISTS idx_cases_status_updated ON cases(status, updated_at);
            CREATE INDEX IF NOT EXISTS idx_evidence_case_id_created_at ON evidence(case_id, created_at);
            CREATE INDEX IF NOT EXISTS idx_audit_log_created_at ON audit_log(created_at);
            CREATE INDEX IF NOT EXISTS idx_case_counters_prefix_year ON case_counters(prefix, year);
            '''
        )

        _ensure_column(conn, 'users', 'active', 'active INTEGER NOT NULL DEFAULT 1')
        _ensure_column(conn, 'users', 'case_prefix', 'case_prefix TEXT')
        _ensure_column(conn, 'users', 'address', 'address TEXT')
        _ensure_column(conn, 'users', 'phone', 'phone TEXT')
        _ensure_column(conn, 'users', 'vessel_affiliation', 'vessel_affiliation TEXT')
        _ensure_column(conn, 'users', 'permissions_json', "permissions_json TEXT NOT NULL DEFAULT '[]'")
        _ensure_column(conn, 'users', 'updated_at', "updated_at TEXT NOT NULL DEFAULT '1970-01-01T00:00:00Z'")

        _ensure_column(conn, 'cases', 'case_basis', "case_basis TEXT NOT NULL DEFAULT 'patruljeobservasjon'")
        _ensure_column(conn, 'cases', 'basis_source_name', 'basis_source_name TEXT')
        _ensure_column(conn, 'cases', 'basis_details', 'basis_details TEXT')
        _ensure_column(conn, 'cases', 'source_snapshot_json', "source_snapshot_json TEXT NOT NULL DEFAULT '[]'")
        _ensure_column(conn, 'cases', 'last_generated_pdf', 'last_generated_pdf TEXT')
        _ensure_column(conn, 'cases', 'lookup_text', 'lookup_text TEXT')
        _ensure_column(conn, 'cases', 'last_previewed_at', 'last_previewed_at TEXT')
        _ensure_column(conn, 'cases', 'crew_json', "crew_json TEXT NOT NULL DEFAULT '[]'")
        _ensure_column(conn, 'cases', 'external_actors_json', "external_actors_json TEXT NOT NULL DEFAULT '[]'")
        _ensure_column(conn, 'cases', 'persons_json', "persons_json TEXT NOT NULL DEFAULT '[]'")
        _ensure_column(conn, 'cases', 'hummer_participant_no', 'hummer_participant_no TEXT')
        _ensure_column(conn, 'cases', 'hummer_last_registered', 'hummer_last_registered TEXT')
        _ensure_column(conn, 'cases', 'radio_call_sign', 'radio_call_sign TEXT')
        _ensure_column(conn, 'cases', 'gear_marker_id', 'gear_marker_id TEXT')
        _ensure_column(conn, 'cases', 'suspect_post_place', 'suspect_post_place TEXT')
        _ensure_column(conn, 'cases', 'observed_gear_count', 'observed_gear_count INTEGER')
        _ensure_column(conn, 'cases', 'complaint_override', 'complaint_override TEXT')
        _ensure_column(conn, 'cases', 'own_report_override', 'own_report_override TEXT')
        _ensure_column(conn, 'cases', 'interview_report_override', 'interview_report_override TEXT')
        _ensure_column(conn, 'cases', 'seizure_report_override', 'seizure_report_override TEXT')
        _ensure_column(conn, 'cases', 'interview_sessions_json', "interview_sessions_json TEXT NOT NULL DEFAULT '[]'")
        _ensure_column(conn, 'cases', 'seizure_reports_json', "seizure_reports_json TEXT NOT NULL DEFAULT '[]'")
        _ensure_column(conn, 'cases', 'interview_not_conducted', 'interview_not_conducted INTEGER NOT NULL DEFAULT 0')
        _ensure_column(conn, 'cases', 'interview_not_conducted_reason', 'interview_not_conducted_reason TEXT')
        _ensure_column(conn, 'cases', 'interview_guidance_text', 'interview_guidance_text TEXT')
        _ensure_column(conn, 'cases', 'complainant_signature', 'complainant_signature TEXT')
        _ensure_column(conn, 'cases', 'witness_signature', 'witness_signature TEXT')
        _ensure_column(conn, 'cases', 'investigator_signature', 'investigator_signature TEXT')
        _ensure_column(conn, 'cases', 'suspect_signature', 'suspect_signature TEXT')
        _ensure_column(conn, 'cases', 'deleted_at', 'deleted_at TEXT')
        _ensure_column(conn, 'cases', 'deleted_by', 'deleted_by INTEGER')
        _ensure_column(conn, 'cases', 'version', 'version INTEGER NOT NULL DEFAULT 1')
        _ensure_column(conn, 'cases', 'updated_by', 'updated_by INTEGER')
        _ensure_column(conn, 'cases', 'last_client_mutation_id', 'last_client_mutation_id TEXT')

        _ensure_column(conn, 'evidence', 'created_by', 'created_by INTEGER REFERENCES users(id) ON DELETE SET NULL')
        _ensure_column(conn, 'evidence', 'finding_key', 'finding_key TEXT')
        _ensure_column(conn, 'evidence', 'law_text', 'law_text TEXT')
        _ensure_column(conn, 'evidence', 'violation_reason', 'violation_reason TEXT')
        _ensure_column(conn, 'evidence', 'seizure_ref', 'seizure_ref TEXT')
        _ensure_column(conn, 'evidence', 'file_size', 'file_size INTEGER')
        _ensure_column(conn, 'evidence', 'sha256', 'sha256 TEXT')
        _ensure_column(conn, 'evidence', 'sync_state', "sync_state TEXT NOT NULL DEFAULT 'synced'")
        _ensure_column(conn, 'evidence', 'device_id', 'device_id TEXT')
        _ensure_column(conn, 'evidence', 'local_media_id', 'local_media_id TEXT')
        _ensure_column(conn, 'evidence', 'server_received_at', 'server_received_at TEXT')
        _ensure_column(conn, 'evidence', 'display_order', 'display_order INTEGER')
        conn.execute('UPDATE evidence SET display_order = id * 10 WHERE display_order IS NULL')

        conn.execute('CREATE INDEX IF NOT EXISTS idx_evidence_case_sha ON evidence(case_id, sha256)')
        conn.execute('CREATE INDEX IF NOT EXISTS idx_evidence_case_order ON evidence(case_id, display_order, id)')
        conn.execute('CREATE INDEX IF NOT EXISTS idx_evidence_local_media_id ON evidence(local_media_id)')

        now = utcnow_iso()
        conn.execute("UPDATE users SET active = 1 WHERE active IS NULL")
        conn.execute("UPDATE users SET case_prefix = 'LBHN' WHERE case_prefix IS NULL OR trim(case_prefix) = ''")
        conn.execute(
            "UPDATE users SET updated_at = COALESCE(NULLIF(updated_at, ''), created_at, ?) WHERE updated_at IS NULL OR updated_at = '' OR updated_at = '1970-01-01T00:00:00Z'",
            (now,),
        )

        user_rows = conn.execute('SELECT id, role, permissions_json FROM users').fetchall()
        for row in user_rows:
            normalized = permissions_to_json(str(row.get('role') or 'investigator'), row.get('permissions_json'))
            if row.get('permissions_json') != normalized:
                conn.execute('UPDATE users SET permissions_json = ?, updated_at = ? WHERE id = ?', (normalized, now, row['id']))

        conn.execute("UPDATE cases SET source_snapshot_json = '[]' WHERE source_snapshot_json IS NULL OR source_snapshot_json = ''")
        conn.execute("UPDATE cases SET crew_json = '[]' WHERE crew_json IS NULL OR crew_json = ''")
        conn.execute("UPDATE cases SET external_actors_json = '[]' WHERE external_actors_json IS NULL OR external_actors_json = ''")
        conn.execute("UPDATE cases SET persons_json = '[]' WHERE persons_json IS NULL OR persons_json = ''")
        conn.execute("UPDATE cases SET interview_sessions_json = '[]' WHERE interview_sessions_json IS NULL OR interview_sessions_json = ''")
        conn.execute("UPDATE cases SET seizure_reports_json = '[]' WHERE seizure_reports_json IS NULL OR seizure_reports_json = ''")
        conn.execute("UPDATE cases SET interview_not_conducted = 0 WHERE interview_not_conducted IS NULL")
        conn.execute("UPDATE cases SET case_basis = 'patruljeobservasjon' WHERE case_basis IS NULL OR case_basis = ''")
        conn.execute("UPDATE cases SET case_basis = 'patruljeobservasjon' WHERE case_basis NOT IN ('patruljeobservasjon', 'tips')")
        conn.execute("UPDATE cases SET status = 'Utkast' WHERE status IS NULL OR status = '' OR lower(status) = 'draft'")
        conn.execute("UPDATE cases SET status = 'Anmeldt' WHERE lower(status) = 'klar for anmeldelse'")
        conn.execute("UPDATE cases SET status = 'Anmeldt og sendt' WHERE lower(status) = 'ferdig eksportert'")
        conn.execute('UPDATE cases SET version = 1 WHERE version IS NULL OR version < 1')


def record_audit(actor_user_id: int | None, action: str, entity_type: str, entity_id: str | int | None = None, details: Optional[Dict[str, Any]] = None) -> int:
    with get_conn() as conn:
        cur = conn.execute(
            '''
            INSERT INTO audit_log(actor_user_id, action, entity_type, entity_id, details_json, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
            ''',
            (
                actor_user_id,
                action.strip(),
                entity_type.strip(),
                None if entity_id is None else str(entity_id),
                json.dumps(details or {}, ensure_ascii=False),
                utcnow_iso(),
            ),
        )
        return int(cur.lastrowid)


def list_audit_logs(limit: int = 200) -> list[Dict[str, Any]]:
    with get_conn() as conn:
        cur = conn.execute(
            '''
            SELECT a.*, u.full_name AS actor_name, u.email AS actor_email
            FROM audit_log a
            LEFT JOIN users u ON a.actor_user_id = u.id
            ORDER BY a.created_at DESC, a.id DESC
            LIMIT ?
            ''',
            (limit,),
        )
        return list(cur.fetchall())


def create_user(
    email: str,
    full_name: str,
    password_hash: str,
    role: str = 'investigator',
    address: str | None = None,
    phone: str | None = None,
    vessel_affiliation: str | None = None,
    permissions: list[str] | tuple[str, ...] | None = None,
    last_complainant_name: Optional[str] = None,
    last_witness_name: Optional[str] = None,
    case_prefix: Optional[str] = None,
    active: bool = True,
) -> int:
    now = utcnow_iso()
    permissions_json = permissions_to_json(role, permissions)
    with get_conn() as conn:
        cur = conn.execute(
            '''
            INSERT INTO users(email, full_name, password_hash, role, address, phone, vessel_affiliation, permissions_json, active, last_complainant_name, last_witness_name, case_prefix, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''',
            (
                email.strip().lower(),
                full_name.strip(),
                password_hash,
                role,
                (address or '').strip() or None,
                (phone or '').strip() or None,
                (vessel_affiliation or '').strip() or None,
                permissions_json,
                1 if active else 0,
                last_complainant_name,
                last_witness_name,
                (case_prefix or '').strip().upper() or None,
                now,
                now,
            ),
        )
        return int(cur.lastrowid)


def update_user(
    user_id: int,
    *,
    full_name: str,
    role: str,
    active: bool,
    address: str | None,
    phone: str | None,
    vessel_affiliation: str | None,
    permissions: list[str] | tuple[str, ...] | None,
    last_complainant_name: str | None,
    last_witness_name: str | None,
    case_prefix: str | None,
) -> None:
    with get_conn() as conn:
        conn.execute(
            '''
            UPDATE users
            SET full_name = ?, role = ?, active = ?, address = ?, phone = ?, vessel_affiliation = ?, permissions_json = ?, last_complainant_name = ?, last_witness_name = ?, case_prefix = ?, updated_at = ?
            WHERE id = ?
            ''',
            (
                full_name.strip(),
                role,
                1 if active else 0,
                (address or '').strip() or None,
                (phone or '').strip() or None,
                (vessel_affiliation or '').strip() or None,
                permissions_to_json(role, permissions),
                (last_complainant_name or '').strip() or None,
                (last_witness_name or '').strip() or None,
                (case_prefix or '').strip().upper() or None,
                utcnow_iso(),
                user_id,
            ),
        )


def remove_user(user_id: int) -> None:
    with get_conn() as conn:
        conn.execute('UPDATE users SET active = 0, updated_at = ? WHERE id = ?', (utcnow_iso(), user_id))



def set_user_password(user_id: int, password_hash: str) -> None:
    with get_conn() as conn:
        conn.execute(
            'UPDATE users SET password_hash = ?, updated_at = ? WHERE id = ?',
            (password_hash, utcnow_iso(), user_id),
        )


def get_user_by_email(email: str) -> Optional[Dict[str, Any]]:
    with get_conn() as conn:
        cur = conn.execute('SELECT * FROM users WHERE email = ?', (email.strip().lower(),))
        return cur.fetchone()


def get_user_by_id(user_id: int) -> Optional[Dict[str, Any]]:
    with get_conn() as conn:
        cur = conn.execute('SELECT * FROM users WHERE id = ?', (user_id,))
        return cur.fetchone()


def list_users() -> list[Dict[str, Any]]:
    with get_conn() as conn:
        cur = conn.execute("SELECT * FROM users ORDER BY CASE WHEN role = 'admin' THEN 0 ELSE 1 END, active DESC, full_name ASC")
        rows = list(cur.fetchall())
    for row in rows:
        row['permissions'] = get_user_permissions(row)
    return rows


def update_user_last_names(user_id: int, complainant_name: str | None, witness_name: str | None) -> None:
    with get_conn() as conn:
        conn.execute(
            '''
            UPDATE users
            SET last_complainant_name = ?, last_witness_name = ?, updated_at = ?
            WHERE id = ?
            ''',
            (
                (complainant_name or '').strip() or None,
                (witness_name or '').strip() or None,
                utcnow_iso(),
                user_id,
            ),
        )


def _normalize_case_prefix(value: str | None) -> str:
    raw = ''.join(ch for ch in str(value or '').upper() if ch.isalnum())
    return raw[:8] or 'LBHN'


def _next_case_number(conn: sqlite3.Connection, created_by: int) -> str:
    """Reserve next case number for a user in a write transaction.

    Uses case_counters so two users/devices cannot receive the same
    prefix/year/løpenummer under concurrent requests.
    """
    year = datetime.now().strftime('%y')
    cur_user = conn.execute('SELECT case_prefix FROM users WHERE id = ?', (created_by,))
    user_row = cur_user.fetchone() or {}
    prefix = _normalize_case_prefix(user_row.get('case_prefix'))
    now = utcnow_iso()
    row = conn.execute(
        'SELECT next_number FROM case_counters WHERE prefix = ? AND year = ?',
        (prefix, year),
    ).fetchone()

    if row is None:
        like_pattern = f'{prefix} {year} %'
        cur = conn.execute('SELECT case_number FROM cases WHERE case_number LIKE ?', (like_pattern,))
        last_num = 0
        import re
        for existing in cur.fetchall():
            match = re.search(r'(\d{3})\s*$', str(existing.get('case_number') or ''))
            if match:
                try:
                    last_num = max(last_num, int(match.group(1)))
                except Exception:
                    pass
        reserved = last_num + 1
        conn.execute(
            'INSERT INTO case_counters(prefix, year, next_number, updated_at) VALUES (?, ?, ?, ?)',
            (prefix, year, reserved + 1, now),
        )
    else:
        reserved = max(int(row.get('next_number') or 1), 1)
        conn.execute(
            'UPDATE case_counters SET next_number = ?, updated_at = ? WHERE prefix = ? AND year = ?',
            (reserved + 1, now, prefix, year),
        )

    return f'{prefix} {year} {reserved:03d}'



def create_case(created_by: int, investigator_name: str, complainant_name: str | None, witness_name: str | None) -> int:
    now = utcnow_iso()
    local_now = localnow_form()
    with get_conn() as conn:
        conn.execute('BEGIN IMMEDIATE')
        case_number = _next_case_number(conn, created_by)
        cur = conn.execute(
            '''
            INSERT INTO cases(
                case_number, created_by, investigator_name, complainant_name, witness_name,
                case_basis, basis_source_name, basis_details, start_time, end_time,
                source_snapshot_json, crew_json, external_actors_json, persons_json, interview_sessions_json, seizure_reports_json, interview_not_conducted, interview_not_conducted_reason, interview_guidance_text, complainant_signature, witness_signature, investigator_signature, suspect_signature, version, updated_by, last_client_mutation_id, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''',
            (
                case_number,
                created_by,
                investigator_name,
                complainant_name,
                witness_name,
                'patruljeobservasjon',
                None,
                'Kontrollsak er opprettet. Bruk Sett inn standardtekst når nærmeste sted, kontrolltype, art/fiskeri og redskap er valgt.',
                local_now,
                None,
                '[]',
                '[]',
                '[]',
                '[]',
                '[]',
                '[]',
                0,
                None,
                None,
                None,
                None,
                None,
                None,
                1,
                created_by,
                None,
                now,
                now,
            ),
        )
        return int(cur.lastrowid)


def get_case(case_id: int) -> Optional[Dict[str, Any]]:
    with get_conn() as conn:
        cur = conn.execute(
            '''
            SELECT c.*, u.full_name AS created_by_name, u.email AS created_by_email, d.full_name AS deleted_by_name
            FROM cases c
            JOIN users u ON c.created_by = u.id
            LEFT JOIN users d ON c.deleted_by = d.id
            WHERE c.id = ?
            ''',
            (case_id,),
        )
        return cur.fetchone()


def list_cases(user: Dict[str, Any], status_filter: str | None = None, include_deleted: bool = False) -> list[Dict[str, Any]]:
    with get_conn() as conn:
        clauses = []
        params: list[Any] = []
        if user['role'] != 'admin':
            clauses.append('c.created_by = ?')
            params.append(user['id'])
        if not include_deleted:
            clauses.append('c.deleted_at IS NULL')
        if status_filter and status_filter != 'all':
            clauses.append('c.status = ?')
            params.append(status_filter)
        where_sql = f"WHERE {' AND '.join(clauses)}" if clauses else ''
        cur = conn.execute(
            f'''
            SELECT c.*, u.full_name AS created_by_name, d.full_name AS deleted_by_name
            FROM cases c
            JOIN users u ON c.created_by = u.id
            LEFT JOIN users d ON c.deleted_by = d.id
            {where_sql}
            ORDER BY c.updated_at DESC, c.id DESC
            ''',
            params,
        )
        return list(cur.fetchall())


def list_cases_for_admin(deleted_filter: str = 'active', search: str = '') -> list[Dict[str, Any]]:
    deleted_filter = str(deleted_filter or 'active').strip().lower()
    with get_conn() as conn:
        clauses: list[str] = []
        params: list[Any] = []
        if deleted_filter == 'deleted':
            clauses.append('c.deleted_at IS NOT NULL')
        elif deleted_filter == 'all':
            pass
        else:
            clauses.append('c.deleted_at IS NULL')
        search_value = str(search or '').strip()
        if search_value:
            like = f'%{search_value}%'
            clauses.append('(c.case_number LIKE ? OR c.investigator_name LIKE ? OR COALESCE(c.complainant_name, "") LIKE ? OR COALESCE(c.suspect_name, "") LIKE ? OR COALESCE(c.vessel_name, "") LIKE ?)')
            params.extend([like, like, like, like, like])
        where_sql = f"WHERE {' AND '.join(clauses)}" if clauses else ''
        cur = conn.execute(
            f'''
            SELECT c.*, u.full_name AS created_by_name, d.full_name AS deleted_by_name
            FROM cases c
            JOIN users u ON c.created_by = u.id
            LEFT JOIN users d ON c.deleted_by = d.id
            {where_sql}
            ORDER BY CASE WHEN c.deleted_at IS NULL THEN c.updated_at ELSE c.deleted_at END DESC, c.id DESC
            ''',
            params,
        )
        return list(cur.fetchall())


def admin_case_counts() -> Dict[str, int]:
    with get_conn() as conn:
        active = conn.execute('SELECT COUNT(*) AS n FROM cases WHERE deleted_at IS NULL').fetchone()['n']
        deleted = conn.execute('SELECT COUNT(*) AS n FROM cases WHERE deleted_at IS NOT NULL').fetchone()['n']
        total = int(active) + int(deleted)
        return {'total': int(total), 'active': int(active), 'deleted': int(deleted)}


def case_counts(user: Dict[str, Any]) -> Dict[str, int]:
    with get_conn() as conn:
        if user['role'] == 'admin':
            total = conn.execute('SELECT COUNT(*) AS n FROM cases WHERE deleted_at IS NULL').fetchone()['n']
            draft = conn.execute("SELECT COUNT(*) AS n FROM cases WHERE deleted_at IS NULL AND status = 'Utkast'").fetchone()['n']
            ready = conn.execute("SELECT COUNT(*) AS n FROM cases WHERE deleted_at IS NULL AND status = 'Anmeldt'").fetchone()['n']
            exported = conn.execute("SELECT COUNT(*) AS n FROM cases WHERE deleted_at IS NULL AND status = 'Anmeldt og sendt'").fetchone()['n']
        else:
            total = conn.execute('SELECT COUNT(*) AS n FROM cases WHERE created_by = ? AND deleted_at IS NULL', (user['id'],)).fetchone()['n']
            draft = conn.execute("SELECT COUNT(*) AS n FROM cases WHERE created_by = ? AND deleted_at IS NULL AND status = 'Utkast'", (user['id'],)).fetchone()['n']
            ready = conn.execute("SELECT COUNT(*) AS n FROM cases WHERE created_by = ? AND deleted_at IS NULL AND status = 'Anmeldt'", (user['id'],)).fetchone()['n']
            exported = conn.execute("SELECT COUNT(*) AS n FROM cases WHERE created_by = ? AND deleted_at IS NULL AND status = 'Anmeldt og sendt'", (user['id'],)).fetchone()['n']
        return {
            'total': int(total),
            'draft': int(draft),
            'ready': int(ready),
            'exported': int(exported),
        }



def case_number_exists(case_number: str, *, exclude_case_id: int | None = None) -> bool:
    clean = str(case_number or '').strip()
    if not clean:
        return False
    with get_conn() as conn:
        if exclude_case_id is None:
            row = conn.execute('SELECT id FROM cases WHERE case_number = ? LIMIT 1', (clean,)).fetchone()
        else:
            row = conn.execute('SELECT id FROM cases WHERE case_number = ? AND id != ? LIMIT 1', (clean, exclude_case_id)).fetchone()
    return row is not None

def save_case(
    case_id: int,
    data: Dict[str, Any],
    *,
    expected_version: int | str | None = None,
    updated_by: int | None = None,
    client_mutation_id: str | None = None,
) -> Dict[str, Any]:
    allowed_keys = [
        'case_number', 'investigator_name', 'complainant_name', 'witness_name', 'case_basis', 'basis_source_name', 'basis_details',
        'control_type', 'fishery_type', 'species', 'gear_type', 'start_time', 'end_time', 'location_name', 'latitude', 'longitude',
        'area_status', 'area_name', 'suspect_name', 'suspect_phone', 'suspect_birthdate', 'suspect_address', 'suspect_post_place', 'lookup_text', 'vessel_name',
        'vessel_reg', 'radio_call_sign', 'gear_marker_id', 'notes', 'hearing_text', 'seizure_notes', 'summary', 'findings_json', 'status', 'source_snapshot_json',
        'crew_json', 'external_actors_json', 'persons_json', 'interview_sessions_json', 'seizure_reports_json', 'interview_not_conducted', 'interview_not_conducted_reason', 'interview_guidance_text', 'hummer_participant_no', 'hummer_last_registered', 'observed_gear_count', 'complaint_override', 'own_report_override', 'interview_report_override', 'seizure_report_override', 'complainant_signature', 'witness_signature', 'investigator_signature', 'suspect_signature', 'last_previewed_at', 'last_generated_pdf'
    ]

    expected: int | None = None
    if expected_version not in (None, ''):
        try:
            expected = int(expected_version)
        except Exception:
            expected = None

    assignments = []
    values: list[Any] = []
    for key in allowed_keys:
        if key in data:
            assignments.append(f'{key} = ?')
            value = data[key]
            if key in {'findings_json', 'source_snapshot_json', 'crew_json', 'external_actors_json', 'persons_json', 'interview_sessions_json', 'seizure_reports_json'} and not isinstance(value, str):
                value = json.dumps(value, ensure_ascii=False)
            values.append(value)

    now = utcnow_iso()
    mutation_id = str(client_mutation_id or '').strip() or None

    with get_conn() as conn:
        current = conn.execute('SELECT version, updated_at, last_client_mutation_id FROM cases WHERE id = ?', (case_id,)).fetchone()
        if not current:
            return {'ok': False, 'missing': True, 'version': 0, 'updated_at': ''}
        current_version = int(current.get('version') or 1)
        if expected is not None and expected > 0 and expected != current_version:
            current_mutation = str(current.get('last_client_mutation_id') or '').strip()
            if mutation_id and current_mutation and mutation_id == current_mutation:
                return {'ok': True, 'version': current_version, 'updated_at': str(current.get('updated_at') or ''), 'duplicate_mutation': True}
            raise CaseConflictError(current_version=current_version, current_updated_at=str(current.get('updated_at') or ''))

        new_version = current_version + 1
        assignments.append('updated_at = ?')
        values.append(now)
        assignments.append('version = ?')
        values.append(new_version)
        assignments.append('updated_by = ?')
        values.append(updated_by)
        assignments.append('last_client_mutation_id = ?')
        values.append(mutation_id)
        values.append(case_id)
        conn.execute(f'UPDATE cases SET {", ".join(assignments)} WHERE id = ?', values)
        return {'ok': True, 'version': new_version, 'updated_at': now}


def hard_delete_case(case_id: int) -> None:
    with get_conn() as conn:
        conn.execute('DELETE FROM cases WHERE id = ?', (case_id,))


def soft_delete_case(case_id: int, deleted_by: int | None) -> None:
    timestamp = utcnow_iso()
    with get_conn() as conn:
        conn.execute(
            'UPDATE cases SET deleted_at = ?, deleted_by = ?, updated_at = ? WHERE id = ? AND deleted_at IS NULL',
            (timestamp, deleted_by, timestamp, case_id),
        )


def restore_case(case_id: int) -> None:
    with get_conn() as conn:
        conn.execute(
            'UPDATE cases SET deleted_at = NULL, deleted_by = NULL, updated_at = ? WHERE id = ? AND deleted_at IS NOT NULL',
            (utcnow_iso(), case_id),
        )


def add_evidence(
    case_id: int,
    filename: str,
    original_filename: str,
    caption: str | None,
    mime_type: str | None,
    created_by: int | None = None,
    finding_key: str | None = None,
    law_text: str | None = None,
    violation_reason: str | None = None,
    seizure_ref: str | None = None,
    file_size: int | None = None,
    sha256: str | None = None,
    device_id: str | None = None,
    local_media_id: str | None = None,
    display_order: int | None = None,
) -> int:
    now = utcnow_iso()
    with get_conn() as conn:
        if display_order is None:
            cur_order = conn.execute('SELECT COALESCE(MAX(display_order), 0) FROM evidence WHERE case_id = ?', (case_id,))
            display_order = int(cur_order.fetchone()[0] or 0) + 10
        cur = conn.execute(
            '''
            INSERT INTO evidence(case_id, filename, original_filename, caption, mime_type, finding_key, law_text, violation_reason, seizure_ref, file_size, sha256, sync_state, device_id, local_media_id, server_received_at, display_order, created_at, created_by)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''',
            (case_id, filename, original_filename, caption, mime_type, finding_key, law_text, violation_reason, seizure_ref, file_size, sha256, 'synced', device_id, local_media_id, now, int(display_order), now, created_by),
        )
        return int(cur.lastrowid)


def list_evidence(case_id: int) -> list[Dict[str, Any]]:
    with get_conn() as conn:
        cur = conn.execute('''
            SELECT * FROM evidence
            WHERE case_id = ?
            ORDER BY COALESCE(display_order, id * 10) ASC, created_at ASC, id ASC
        ''', (case_id,))
        return list(cur.fetchall())


def reorder_evidence(case_id: int, evidence_ids: list[int]) -> None:
    clean_ids: list[int] = []
    seen: set[int] = set()
    for value in evidence_ids or []:
        try:
            item_id = int(value)
        except Exception:
            continue
        if item_id <= 0 or item_id in seen:
            continue
        seen.add(item_id)
        clean_ids.append(item_id)
    if not clean_ids:
        return
    with get_conn() as conn:
        existing = {int(row['id']) for row in conn.execute('SELECT id FROM evidence WHERE case_id = ?', (case_id,)).fetchall()}
        order_value = 10
        for item_id in clean_ids:
            if item_id not in existing:
                continue
            conn.execute('UPDATE evidence SET display_order = ? WHERE case_id = ? AND id = ?', (order_value, case_id, item_id))
            order_value += 10
        # Keep non-image/audio rows and rows not included after the explicitly ordered image list.
        for row in conn.execute('SELECT id FROM evidence WHERE case_id = ? AND id NOT IN (%s) ORDER BY COALESCE(display_order, id * 10), id' % ','.join('?' for _ in clean_ids), (case_id, *clean_ids)).fetchall():
            conn.execute('UPDATE evidence SET display_order = ? WHERE case_id = ? AND id = ?', (order_value, case_id, int(row['id'])))
            order_value += 10


def get_evidence_by_local_media_id(case_id: int, local_media_id: str | None) -> Optional[Dict[str, Any]]:
    clean = str(local_media_id or '').strip()
    if not clean:
        return None
    with get_conn() as conn:
        cur = conn.execute(
            'SELECT * FROM evidence WHERE case_id = ? AND local_media_id = ? ORDER BY id DESC LIMIT 1',
            (case_id, clean),
        )
        return cur.fetchone()


def get_evidence_by_id(evidence_id: int) -> Optional[Dict[str, Any]]:
    with get_conn() as conn:
        cur = conn.execute('SELECT * FROM evidence WHERE id = ?', (evidence_id,))
        return cur.fetchone()


def delete_evidence(evidence_id: int) -> Optional[Dict[str, Any]]:
    with get_conn() as conn:
        cur = conn.execute('SELECT * FROM evidence WHERE id = ?', (evidence_id,))
        row = cur.fetchone()
        if not row:
            return None
        conn.execute('DELETE FROM evidence WHERE id = ?', (evidence_id,))
        return row


def case_to_findings(case_row: Dict[str, Any]) -> list[Dict[str, Any]]:
    raw = case_row.get('findings_json') or '[]'
    try:
        data = json.loads(raw)
        if isinstance(data, list):
            return data
    except Exception:
        pass
    return []


def case_to_sources(case_row: Dict[str, Any]) -> list[Dict[str, Any]]:
    raw = case_row.get('source_snapshot_json') or '[]'
    try:
        data = json.loads(raw)
        if isinstance(data, list):
            return data
    except Exception:
        pass
    return []


def has_any_cases() -> bool:
    with get_conn() as conn:
        row = conn.execute('SELECT COUNT(*) AS n FROM cases').fetchone()
        return bool(int(row['n']))



def case_to_crew(case_row: Dict[str, Any]) -> list[Dict[str, Any]]:
    raw = case_row.get('crew_json') or '[]'
    try:
        data = json.loads(raw)
        if isinstance(data, list):
            return data
    except Exception:
        pass
    return []





def case_to_persons(case_row: Dict[str, Any]) -> list[Dict[str, Any]]:
    raw = case_row.get('persons_json') or '[]'
    try:
        data = json.loads(raw)
        if isinstance(data, list):
            return [item for item in data if isinstance(item, dict)]
    except Exception:
        pass
    return []

def case_to_interviews(case_row: Dict[str, Any]) -> list[Dict[str, Any]]:
    raw = case_row.get('interview_sessions_json') or '[]'
    try:
        data = json.loads(raw)
        if isinstance(data, list):
            return data
    except Exception:
        pass
    return []


def case_to_seizure_reports(case_row: Dict[str, Any]) -> list[Dict[str, Any]]:
    raw = case_row.get('seizure_reports_json') or '[]'
    try:
        data = json.loads(raw)
        if isinstance(data, list):
            return [item for item in data if isinstance(item, dict)]
    except Exception:
        pass
    return []

def case_to_external_actors(case_row: Dict[str, Any]) -> list[str]:
    raw = case_row.get('external_actors_json') or '[]'
    try:
        data = json.loads(raw)
        if isinstance(data, list):
            return [str(x) for x in data if str(x).strip()]
    except Exception:
        pass
    return []



def list_cases_for_person_lookup(phone: str = '', name: str = '', address: str = '', species: str = '', gear_type: str = '', vessel_reg: str = '', radio_call_sign: str = '', hummer_participant_no: str = '', exclude_case_id: int | None = None) -> list[Dict[str, Any]]:
    phone = str(phone or '').strip()
    name = str(name or '').strip().lower()
    address = str(address or '').strip().lower()
    species = str(species or '').strip().lower()
    gear_type = str(gear_type or '').strip().lower()
    vessel_reg = str(vessel_reg or '').strip().upper().replace(' ', '')
    radio_call_sign = str(radio_call_sign or '').strip().upper().replace(' ', '')
    hummer_participant_no = str(hummer_participant_no or '').strip().upper().replace(' ', '')
    sql = "SELECT id, case_number, suspect_name, suspect_phone, suspect_address, suspect_post_place, vessel_name, vessel_reg, radio_call_sign, hummer_participant_no, species, gear_type, observed_gear_count, start_time, status FROM cases WHERE deleted_at IS NULL"
    values: list[Any] = []
    if exclude_case_id is not None:
        sql += ' AND id != ?'
        values.append(exclude_case_id)
    if species:
        sql += ' AND lower(COALESCE(species, "")) = ?'
        values.append(species)
    if gear_type:
        sql += ' AND lower(COALESCE(gear_type, "")) = ?'
        values.append(gear_type)
    # require at least one identifying match
    id_parts = []
    if phone:
        id_parts.append('replace(COALESCE(suspect_phone, ""), " ", "") = ?')
        values.append(phone.replace(' ', ''))
    if name:
        id_parts.append('lower(COALESCE(suspect_name, "")) = ?')
        values.append(name)
    if address:
        id_parts.append('lower(COALESCE(suspect_address, "")) = ?')
        values.append(address)
    if vessel_reg:
        id_parts.append('replace(upper(COALESCE(vessel_reg, "")), " ", "") = ?')
        values.append(vessel_reg)
    if radio_call_sign:
        id_parts.append('replace(upper(COALESCE(radio_call_sign, "")), " ", "") = ?')
        values.append(radio_call_sign)
    if hummer_participant_no:
        id_parts.append('replace(upper(COALESCE(hummer_participant_no, "")), " ", "") = ?')
        values.append(hummer_participant_no)
    if not id_parts:
        return []
    sql += ' AND (' + ' OR '.join(id_parts) + ')'
    sql += ' ORDER BY start_time DESC, id DESC LIMIT 50'
    with get_conn() as conn:
        cur = conn.execute(sql, values)
        return list(cur.fetchall())




def lookup_people_from_cases(phone: str = '', name: str = '', address: str = '', vessel_reg: str = '', radio_call_sign: str = '', hummer_participant_no: str = '', exclude_case_id: int | None = None, limit: int = 6) -> list[Dict[str, Any]]:
    rows = list_cases_for_person_lookup(phone=phone, name=name, address=address, vessel_reg=vessel_reg, radio_call_sign=radio_call_sign, hummer_participant_no=hummer_participant_no, exclude_case_id=exclude_case_id)
    out: list[Dict[str, Any]] = []
    seen: set[tuple[str, str, str, str]] = set()
    for row in rows:
        key = (str(row.get('suspect_name') or '').strip(), str(row.get('suspect_phone') or '').strip(), str(row.get('vessel_reg') or '').strip(), str(row.get('hummer_participant_no') or '').strip())
        if key in seen:
            continue
        seen.add(key)
        out.append({
            'name': row.get('suspect_name') or '',
            'address': row.get('suspect_address') or '',
            'post_place': row.get('suspect_post_place') or '',
            'phone': row.get('suspect_phone') or '',
            'vessel_name': row.get('vessel_name') or '',
            'vessel_reg': row.get('vessel_reg') or '',
            'radio_call_sign': row.get('radio_call_sign') or '',
            'hummer_participant_no': row.get('hummer_participant_no') or '',
            'participant_no': row.get('hummer_participant_no') or '',
            'source': 'Tidligere saker i appen',
            'source_url': '',
            'match_reason': 'tidligere sak',
        })
        if len(out) >= limit:
            break
    return out

def related_gear_summary(phone: str = '', name: str = '', address: str = '', species: str = '', gear_type: str = '', vessel_reg: str = '', radio_call_sign: str = '', hummer_participant_no: str = '', exclude_case_id: int | None = None) -> Dict[str, Any]:
    rows = list_cases_for_person_lookup(phone=phone, name=name, address=address, species=species, gear_type=gear_type, vessel_reg=vessel_reg, radio_call_sign=radio_call_sign, hummer_participant_no=hummer_participant_no, exclude_case_id=exclude_case_id)
    total = 0
    cases: list[Dict[str, Any]] = []
    for row in rows:
        try:
            count = int(row.get('observed_gear_count') or 0)
        except Exception:
            count = 0
        total += count
        cases.append({
            'case_number': row.get('case_number'),
            'count': count,
            'start_time': row.get('start_time'),
            'status': row.get('status'),
        })
    return {'count_total': total, 'matches': cases}
