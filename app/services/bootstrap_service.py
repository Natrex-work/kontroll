from __future__ import annotations

from fastapi import HTTPException

from .. import db
from ..auth import hash_password
from ..config import settings
from ..logging_setup import get_logger
from ..validation import validate_password

logger = get_logger(__name__)


def initialize_application_data() -> None:
    settings.ensure_runtime_dirs()
    db.init_db()
    _validate_runtime_security()
    ensure_bootstrap_admin()
    if settings.session_secret == 'dev-session-secret-change-me':
        logger.warning('SESSION_SECRET bruker standard utviklingsverdi. Sett en unik verdi i .env eller miljøet før ordinær bruk.')
    if not db.list_users():
        logger.warning('Ingen brukere finnes. Opprett første administrator med KV_BOOTSTRAP_ADMIN_* eller `python manage.py create-admin`.')


def _validate_runtime_security() -> None:
    if settings.production_mode:
        if settings.session_secret == 'dev-session-secret-change-me':
            raise RuntimeError('SESSION_SECRET må settes til en unik verdi i produksjon.')
        if not settings.session_https_only:
            raise RuntimeError('KV_SESSION_HTTPS_ONLY må være aktivert i produksjon.')
        if not settings.allowed_hosts or '*' in settings.allowed_hosts:
            raise RuntimeError('KV_ALLOWED_HOSTS må settes eksplisitt i produksjon.')


def ensure_bootstrap_admin() -> None:
    email = settings.bootstrap_admin_email
    name = settings.bootstrap_admin_name
    password = settings.bootstrap_admin_password
    if not (email and name and password):
        return
    try:
        validate_password(password)
    except HTTPException as exc:
        raise RuntimeError(f'KV_BOOTSTRAP_ADMIN_PASSWORD er for svakt: {exc.detail}') from exc
    existing = db.get_user_by_email(email)
    if existing is not None:
        return
    user_id = db.create_user(
        email=email,
        full_name=name,
        password_hash=hash_password(password),
        role='admin',
        permissions=list(db.DEFAULT_ADMIN_PERMISSIONS),
        last_complainant_name=name,
        last_witness_name=name,
        case_prefix=settings.bootstrap_admin_case_prefix,
        active=True,
    )
    db.record_audit(user_id, 'bootstrap_admin', 'user', user_id, {'email': email})
    logger.info('Opprettet første administrator fra miljøvariabler.')
