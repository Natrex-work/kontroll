from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

try:
    from dotenv import load_dotenv
except Exception:  # pragma: no cover - optional dependency during bootstrap
    load_dotenv = None

BASE_DIR = Path(__file__).resolve().parent.parent
if load_dotenv is not None:
    load_dotenv(BASE_DIR / '.env', override=False)


def _env_flag(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() not in {'0', 'false', 'no', 'off'}


def _env_list(name: str, default: list[str]) -> list[str]:
    raw = os.getenv(name)
    if raw is None:
        return list(default)
    items = [item.strip() for item in raw.split(',') if item.strip()]
    return items or list(default)


@dataclass(frozen=True)
class Settings:
    app_name: str
    app_version: str
    app_version_label: str
    base_dir: Path
    templates_dir: Path
    static_dir: Path
    upload_dir: Path
    generated_dir: Path
    db_path: Path
    production_mode: bool
    session_secret: str
    data_encryption_key: str
    session_same_site: str
    session_https_only: bool
    session_cookie_name: str
    session_max_age_seconds: int
    allowed_hosts: list[str]
    log_level: str
    max_upload_size_mb: int
    bootstrap_demo_users: bool
    bootstrap_demo_cases: bool
    bootstrap_admin_email: str
    bootstrap_admin_name: str
    bootstrap_admin_password: str
    csrf_enabled: bool

    def ensure_runtime_dirs(self) -> None:
        self.upload_dir.mkdir(parents=True, exist_ok=True)
        self.generated_dir.mkdir(parents=True, exist_ok=True)


PRODUCTION_DEFAULT = _env_flag('KV_PRODUCTION_MODE', False)
SESSION_HTTPS_DEFAULT = True if PRODUCTION_DEFAULT else False
SESSION_SAMESITE_DEFAULT = 'strict' if PRODUCTION_DEFAULT else 'lax'
ALLOWED_HOSTS_DEFAULT = ['*'] if not PRODUCTION_DEFAULT else ['localhost', '127.0.0.1']

settings = Settings(
    app_name=os.getenv('KV_APP_NAME', 'Fiskerikontroll'),
    app_version=os.getenv('KV_APP_VERSION', '1.4.0'),
    app_version_label=os.getenv('KV_APP_VERSION_LABEL', '1.4'),
    base_dir=BASE_DIR,
    templates_dir=BASE_DIR / 'app' / 'templates',
    static_dir=BASE_DIR / 'app' / 'static',
    upload_dir=Path(os.getenv('KV_UPLOAD_DIR', str(BASE_DIR / 'uploads'))),
    generated_dir=Path(os.getenv('KV_GENERATED_DIR', str(BASE_DIR / 'generated'))),
    db_path=Path(os.getenv('KV_DB_PATH', str(BASE_DIR / 'kv_kontroll.db'))),
    production_mode=PRODUCTION_DEFAULT,
    session_secret=os.getenv('SESSION_SECRET', 'dev-session-secret-change-me'),
    data_encryption_key=os.getenv('KV_DATA_ENCRYPTION_KEY', ''),
    session_same_site=os.getenv('KV_SESSION_SAMESITE', SESSION_SAMESITE_DEFAULT),
    session_https_only=_env_flag('KV_SESSION_HTTPS_ONLY', SESSION_HTTPS_DEFAULT),
    session_cookie_name=os.getenv('KV_SESSION_COOKIE_NAME', 'kv_session'),
    session_max_age_seconds=max(900, int(os.getenv('KV_SESSION_MAX_AGE_SECONDS', '43200'))),
    allowed_hosts=_env_list('KV_ALLOWED_HOSTS', ALLOWED_HOSTS_DEFAULT),
    log_level=os.getenv('KV_LOG_LEVEL', 'INFO').upper(),
    max_upload_size_mb=max(1, int(os.getenv('KV_MAX_UPLOAD_MB', '25'))),
    bootstrap_demo_users=_env_flag('KV_BOOTSTRAP_DEMO_USERS', False),
    bootstrap_demo_cases=_env_flag('KV_BOOTSTRAP_DEMO_CASES', False),
    bootstrap_admin_email=os.getenv('KV_BOOTSTRAP_ADMIN_EMAIL', '').strip().lower(),
    bootstrap_admin_name=os.getenv('KV_BOOTSTRAP_ADMIN_NAME', '').strip(),
    bootstrap_admin_password=os.getenv('KV_BOOTSTRAP_ADMIN_PASSWORD', ''),
    csrf_enabled=not _env_flag('KV_DISABLE_CSRF', False),
)
