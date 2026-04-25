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
CASE_BASIS = ('patruljeobservasjon', 'tips', 'anmeldelse', 'annen_omstendighet')
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
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = dict_factory
    conn.execute('PRAGMA foreign_keys = ON')
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
        _ensure_column(conn, 'cases', 'suspect_post_place', 'suspect_post_place TEXT')
        _ensure_column(conn, 'cases', 'observed_gear_count', 'observed_gear_count INTEGER')
        _ensure_column(conn, 'cases', 'complaint_override', 'complaint_override TEXT')
        _ensure_column(conn, 'cases', 'own_report_override', 'own_report_override TEXT')
        _ensure_column(conn, 'cases', 'interview_report_override', 'interview_report_override TEXT')
        _ensure_column(conn, 'cases', 'seizure_report_override', 'seizure_report_override TEXT')
        _ensure_column(conn, 'cases', 'interview_sessions_json', "interview_sessions_json TEXT NOT NULL DEFAULT '[]'")
        _ensure_column(conn, 'cases', 'interview_not_conducted', 'interview_not_conducted INTEGER NOT NULL DEFAULT 0')
        _ensure_column(conn, 'cases', 'interview_not_conducted_reason', 'interview_not_conducted_reason TEXT')
        _ensure_column(conn, 'cases', 'interview_guidance_text', 'interview_guidance_text TEXT')
        _ensure_column(conn, 'cases', 'complainant_signature', 'complainant_signature TEXT')
        _ensure_column(conn, 'cases', 'witness_signature', 'witness_signature TEXT')
        _ensure_column(conn, 'cases', 'investigator_signature', 'investigator_signature TEXT')
        _ensure_column(conn, 'cases', 'suspect_signature', 'suspect_signature TEXT')
        _ensure_column(conn, 'cases', 'deleted_at', 'deleted_at TEXT')
        _ensure_column(conn, 'cases', 'deleted_by', 'deleted_by INTEGER')

        _ensure_column(conn, 'evidence', 'created_by', 'created_by INTEGER REFERENCES users(id) ON DELETE SET NULL')
        _ensure_column(conn, 'evidence', 'finding_key', 'finding_key TEXT')
        _ensure_column(conn, 'evidence', 'law_text', 'law_text TEXT')
        _ensure_column(conn, 'evidence', 'violation_reason', 'violation_reason TEXT')
        _ensure_column(conn, 'evidence', 'seizure_ref', 'seizure_ref TEXT')

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
        conn.execute("UPDATE cases SET interview_not_conducted = 0 WHERE interview_not_conducted IS NULL")
        conn.execute("UPDATE cases SET case_basis = 'patruljeobservasjon' WHERE case_basis IS NULL OR case_basis = ''")
        conn.execute("UPDATE cases SET status = 'Utkast' WHERE status IS NULL OR status = '' OR lower(status) = 'draft'")
        conn.execute("UPDATE cases SET status = 'Anmeldt' WHERE lower(status) = 'klar for anmeldelse'")
        conn.execute("UPDATE cases SET status = 'Anmeldt og sendt' WHERE lower(status) = 'ferdig eksportert'")


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
    year = datetime.now().strftime('%y')
    cur_user = conn.execute('SELECT case_prefix FROM users WHERE id = ?', (created_by,))
    user_row = cur_user.fetchone() or {}
    prefix = _normalize_case_prefix(user_row.get('case_prefix'))
    like_pattern = f'{prefix} {year} %'
    cur = conn.execute('SELECT case_number FROM cases WHERE case_number LIKE ? ORDER BY id DESC LIMIT 1', (like_pattern,))
    row = cur.fetchone()
    last_num = 0
    if row:
        import re
        match = re.search(r'(\d{3})\s*$', str(row.get('case_number') or ''))
        if match:
            try:
                last_num = int(match.group(1))
            except Exception:
                last_num = 0
    return f'{prefix} {year} {last_num + 1:03d}'



def create_case(created_by: int, investigator_name: str, complainant_name: str | None, witness_name: str | None) -> int:
    now = utcnow_iso()
    local_now = localnow_form()
    with get_conn() as conn:
        case_number = _next_case_number(conn, created_by)
        cur = conn.execute(
            '''
            INSERT INTO cases(
                case_number, created_by, investigator_name, complainant_name, witness_name,
                case_basis, basis_source_name, basis_details, start_time, end_time,
                source_snapshot_json, crew_json, external_actors_json, persons_json, interview_sessions_json, interview_not_conducted, interview_not_conducted_reason, interview_guidance_text, complainant_signature, witness_signature, investigator_signature, suspect_signature, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''',
            (
                case_number,
                created_by,
                investigator_name,
                complainant_name,
                witness_name,
                'patruljeobservasjon',
                'Kystvakten lettbåt',
                'Det ble fra Kystvakten lettbåt gjennomført kontroll med fokus på faststående fiskeredskap. Kontrollgrunnlaget bygger på egen observasjon og planlagt kontrollvirksomhet.',
                local_now,
                None,
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
                investigator_name,
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

def save_case(case_id: int, data: Dict[str, Any]) -> None:
    allowed_keys = [
        'case_number', 'investigator_name', 'complainant_name', 'witness_name', 'case_basis', 'basis_source_name', 'basis_details',
        'control_type', 'fishery_type', 'species', 'gear_type', 'start_time', 'end_time', 'location_name', 'latitude', 'longitude',
        'area_status', 'area_name', 'suspect_name', 'suspect_phone', 'suspect_birthdate', 'suspect_address', 'suspect_post_place', 'lookup_text', 'vessel_name',
        'vessel_reg', 'radio_call_sign', 'notes', 'hearing_text', 'seizure_notes', 'summary', 'findings_json', 'status', 'source_snapshot_json',
        'crew_json', 'external_actors_json', 'persons_json', 'interview_sessions_json', 'interview_not_conducted', 'interview_not_conducted_reason', 'interview_guidance_text', 'hummer_participant_no', 'hummer_last_registered', 'observed_gear_count', 'complaint_override', 'own_report_override', 'interview_report_override', 'seizure_report_override', 'complainant_signature', 'witness_signature', 'investigator_signature', 'suspect_signature', 'last_previewed_at', 'last_generated_pdf'
    ]
    assignments = []
    values: list[Any] = []
    for key in allowed_keys:
        if key in data:
            assignments.append(f'{key} = ?')
            value = data[key]
            if key in {'findings_json', 'source_snapshot_json', 'crew_json', 'external_actors_json', 'persons_json', 'interview_sessions_json'} and not isinstance(value, str):
                value = json.dumps(value, ensure_ascii=False)
            values.append(value)
    assignments.append('updated_at = ?')
    values.append(utcnow_iso())
    values.append(case_id)
    with get_conn() as conn:
        conn.execute(f'UPDATE cases SET {", ".join(assignments)} WHERE id = ?', values)


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


def add_evidence(case_id: int, filename: str, original_filename: str, caption: str | None, mime_type: str | None, created_by: int | None = None, finding_key: str | None = None, law_text: str | None = None, violation_reason: str | None = None, seizure_ref: str | None = None) -> int:
    with get_conn() as conn:
        cur = conn.execute(
            '''
            INSERT INTO evidence(case_id, filename, original_filename, caption, mime_type, finding_key, law_text, violation_reason, seizure_ref, created_at, created_by)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''',
            (case_id, filename, original_filename, caption, mime_type, finding_key, law_text, violation_reason, seizure_ref, utcnow_iso(), created_by),
        )
        return int(cur.lastrowid)


def list_evidence(case_id: int) -> list[Dict[str, Any]]:
    with get_conn() as conn:
        cur = conn.execute('SELECT * FROM evidence WHERE case_id = ? ORDER BY created_at DESC, id DESC', (case_id,))
        return list(cur.fetchall())


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
