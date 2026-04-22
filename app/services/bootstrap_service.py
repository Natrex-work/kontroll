from __future__ import annotations

from fastapi import HTTPException

from .. import db
from ..auth import hash_password
from ..config import BASE_DIR, settings
from ..logging_setup import get_logger
from ..validation import validate_password

logger = get_logger(__name__)


def _format_allowed_hosts() -> str:
    return ', '.join(settings.allowed_hosts) if settings.allowed_hosts else '(ingen)'


def _log_runtime_summary() -> None:
    logger.info(
        'Oppstart: production=%s render=%s server_url=%s render_host=%s allowed_hosts=%s db_path=%s upload_dir=%s generated_dir=%s',
        settings.production_mode,
        settings.render_runtime,
        settings.server_url or '-',
        settings.render_external_hostname or '-',
        _format_allowed_hosts(),
        settings.db_path,
        settings.upload_dir,
        settings.generated_dir,
    )


def initialize_application_data() -> None:
    settings.ensure_runtime_dirs()
    db.init_db()
    _log_runtime_summary()
    _validate_runtime_security()
    disable_legacy_demo_users()
    ensure_bootstrap_admin()
    if settings.session_secret == 'dev-session-secret-change-me':
        logger.warning('SESSION_SECRET bruker standard utviklingsverdi. Sett en unik verdi i .env eller miljøet før ordinær bruk.')
    if settings.production_mode and str(settings.db_path).startswith(str(BASE_DIR)):
        logger.warning('KV_DB_PATH peker til lokal appmappe. Uten Render-disk kan brukere og saker forsvinne ved restart. Sett KV_DB_PATH/KV_UPLOAD_DIR/KV_GENERATED_DIR til /var/data/...')
    if not db.list_users():
        logger.warning('Ingen brukere finnes. Opprett første administrator med KV_BOOTSTRAP_ADMIN_* eller `python manage.py create-admin`.')


def _validate_runtime_security() -> None:
    if settings.production_mode:
        if settings.session_secret == 'dev-session-secret-change-me':
            raise RuntimeError('SESSION_SECRET må settes til en unik verdi i produksjon. På Render kan du legge den inn manuelt eller la render.yaml generere en verdi automatisk.')
        if not settings.session_https_only:
            raise RuntimeError('KV_SESSION_HTTPS_ONLY må være aktivert i produksjon.')
        if not settings.allowed_hosts or '*' in settings.allowed_hosts:
            raise RuntimeError('KV_ALLOWED_HOSTS må settes eksplisitt i produksjon. Legg inn alle egne domener, og behold gjerne onrender-domenet også.')


def disable_legacy_demo_users() -> None:
    demo_emails = ['admin@kv.demo', 'kontrollor@kv.demo', 'demo@kv.demo']
    for email in demo_emails:
        existing = db.get_user_by_email(email)
        if not existing:
            continue
        if not int(existing.get('active', 1)):
            continue
        db.remove_user(int(existing['id']))
        db.record_audit(existing['id'], 'disable_legacy_demo_user', 'user', existing['id'], {'email': email})
        logger.warning('Deaktiverte eldre demobruker %s under oppstart.', email)


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
