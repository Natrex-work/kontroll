from __future__ import annotations

from typing import Any, Dict, Iterable, Optional

from fastapi import HTTPException, Request

from . import db
from .security import touch_authenticated_session

UserRow = Dict[str, Any]
CaseRow = Dict[str, Any]


def current_user(request: Request) -> Optional[UserRow]:
    user_id = request.session.get('user_id')
    if not user_id:
        return None
    try:
        user_id = int(user_id)
    except Exception:
        request.session.clear()
        return None
    if not touch_authenticated_session(request):
        return None
    user = db.get_user_by_id(user_id)
    if not user or not int(user.get('active', 1)):
        request.session.clear()
        return None
    return user


def require_user(request: Request) -> UserRow:
    user = current_user(request)
    if not user:
        raise HTTPException(status_code=401, detail='Du må logge inn.')
    return user


def user_permissions(user: UserRow | None) -> list[str]:
    return db.get_user_permissions(user)


def has_permission(user: UserRow | None, permission: str) -> bool:
    return db.user_has_permission(user, permission)


def require_permission(request: Request, permission: str, detail: str | None = None) -> UserRow:
    user = require_user(request)
    if not has_permission(user, permission):
        raise HTTPException(status_code=403, detail=detail or 'Brukeren har ikke tilgang til denne modulen.')
    return user


def require_any_permission(request: Request, permissions: Iterable[str], detail: str | None = None) -> UserRow:
    user = require_user(request)
    if not any(has_permission(user, perm) for perm in permissions):
        raise HTTPException(status_code=403, detail=detail or 'Brukeren har ikke tilgang til denne modulen.')
    return user


def require_user_admin(request: Request) -> UserRow:
    user = require_permission(request, 'user_admin', detail='Kun admin med brukerstyring har tilgang.')
    if user.get('role') != 'admin':
        raise HTTPException(status_code=403, detail='Kun admin med brukerstyring har tilgang.')
    return user


def require_control_admin(request: Request) -> UserRow:
    user = require_permission(request, 'control_admin', detail='Kun admin med kontrollstyring har tilgang.')
    if user.get('role') != 'admin':
        raise HTTPException(status_code=403, detail='Kun admin med kontrollstyring har tilgang.')
    return user


def first_allowed_path(user: UserRow | None) -> str | None:
    if not user:
        return None
    ordered = [
        ('kv_kontroll', '/dashboard'),
        ('kart', '/kart'),
        ('regelverk', '/regelverk'),
        ('user_admin', '/admin/users'),
        ('control_admin', '/admin/controls'),
    ]
    for permission, path in ordered:
        if has_permission(user, permission):
            return path
    return None


def can_access_case(user: UserRow, case_row: CaseRow) -> bool:
    if not has_permission(user, 'kv_kontroll'):
        return False
    return user.get('role') == 'admin' or case_row['created_by'] == user['id']


def get_case_for_user(user: UserRow, case_id: int) -> CaseRow:
    case_row = db.get_case(case_id)
    if not case_row:
        raise HTTPException(status_code=404, detail='Fant ikke saken.')
    if case_row.get('deleted_at'):
        raise HTTPException(status_code=404, detail='Saken er slettet og kan bare gjenopprettes av admin.')
    if not can_access_case(user, case_row):
        raise HTTPException(status_code=403, detail='Ingen tilgang til saken.')
    return case_row
