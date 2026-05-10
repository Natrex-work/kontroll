from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse

try:
    from dotenv import load_dotenv
except Exception:  # pragma: no cover - optional dependency during bootstrap
    load_dotenv = None

BASE_DIR = Path(__file__).resolve().parent.parent
if load_dotenv is not None:
    load_dotenv(BASE_DIR / '.env', override=False)

ALLOWED_SAME_SITE = {'lax', 'strict', 'none'}


def _env_flag(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() not in {'0', 'false', 'no', 'off'}


def _env_int(name: str, default: int, *, minimum: int = 0, maximum: int | None = None) -> int:
    raw = os.getenv(name)
    try:
        value = int(str(raw).strip()) if raw is not None and str(raw).strip() else default
    except Exception:
        value = default
    value = max(minimum, value)
    if maximum is not None:
        value = min(maximum, value)
    return value


def _env_list(name: str) -> tuple[str, ...]:
    raw = os.getenv(name, '')
    values = [item.strip() for item in raw.split(',') if item.strip()]
    return tuple(dict.fromkeys(values))


def _normalize_same_site(value: str | None) -> str:
    normalized = str(value or 'lax').strip().lower() or 'lax'
    if normalized not in ALLOWED_SAME_SITE:
        return 'lax'
    return normalized


def _host_from_value(value: str | None) -> str | None:
    raw = str(value or '').strip()
    if not raw:
        return None
    if raw == '*' or raw.startswith('*.'):
        return raw.lower()
    if '://' not in raw and not raw.startswith('//'):
        if '/' not in raw:
            return raw.split(':', 1)[0].strip().lower() or None
        raw = f"https://{raw.lstrip('/')}"
    parsed = urlparse(raw)
    host = (parsed.hostname or '').strip().lower()
    return host or None


PRODUCTION_MODE = _env_flag('KV_PRODUCTION_MODE', False)
RENDER_EXTERNAL_URL = str(os.getenv('RENDER_EXTERNAL_URL', '')).strip()
RENDER_EXTERNAL_HOSTNAME = str(os.getenv('RENDER_EXTERNAL_HOSTNAME', '')).strip().lower()
SERVER_URL = str(os.getenv('SERVER_URL', '')).strip() or RENDER_EXTERNAL_URL

_allowed_hosts: list[str] = []
for item in _env_list('KV_ALLOWED_HOSTS'):
    normalized = _host_from_value(item)
    if normalized and normalized not in _allowed_hosts:
        _allowed_hosts.append(normalized)

for candidate in (SERVER_URL, RENDER_EXTERNAL_URL, RENDER_EXTERNAL_HOSTNAME):
    normalized = _host_from_value(candidate)
    if normalized and normalized not in _allowed_hosts:
        _allowed_hosts.append(normalized)

if not _allowed_hosts:
    if PRODUCTION_MODE:
        _allowed_hosts = [RENDER_EXTERNAL_HOSTNAME] if RENDER_EXTERNAL_HOSTNAME else []
    else:
        _allowed_hosts = ['*']

_session_same_site = _normalize_same_site(os.getenv('KV_SESSION_SAMESITE', 'lax'))
_session_https_only = _env_flag('KV_SESSION_HTTPS_ONLY', PRODUCTION_MODE)
if _session_same_site == 'none' and not _session_https_only:
    _session_same_site = 'lax'

# Keep upload and request limits aligned for mobile OCR and evidence uploads.
_DEFAULT_MAX_UPLOAD_MB = max(1, _env_int('KV_MAX_UPLOAD_MB', 30, minimum=1, maximum=60))
_DEFAULT_MAX_REQUEST_MB = max(
    _DEFAULT_MAX_UPLOAD_MB,
    _env_int('KV_MAX_REQUEST_MB', _DEFAULT_MAX_UPLOAD_MB, minimum=2, maximum=80),
)


def _render_runtime() -> bool:
    # Render sets RENDER=true at runtime. Use this to keep SQLite, uploads and
    # generated documents outside the app image by default. Environment
    # variables still override these defaults.
    return _env_flag('RENDER', False) or bool(RENDER_EXTERNAL_URL or RENDER_EXTERNAL_HOSTNAME)


def _runtime_storage_root() -> Path:
    explicit = str(os.getenv('KV_STORAGE_ROOT', '')).strip()
    if explicit:
        return Path(explicit)
    if _render_runtime():
        return Path('/var/data/fiskerikontroll')
    return BASE_DIR


def _runtime_path(env_name: str, default_path: Path) -> Path:
    raw = str(os.getenv(env_name, '')).strip()
    return Path(raw) if raw else default_path


_RUNTIME_STORAGE_ROOT = _runtime_storage_root()


@dataclass(frozen=True)
class Settings:
    app_name: str
    brand_org_name: str
    app_version: str
    app_version_label: str
    base_dir: Path
    data_dir: Path
    templates_dir: Path
    static_dir: Path
    upload_dir: Path
    generated_dir: Path
    db_path: Path
    session_secret: str
    session_same_site: str
    session_https_only: bool
    session_max_age_seconds: int
    session_idle_minutes: int
    session_absolute_minutes: int
    log_level: str
    max_upload_size_mb: int
    max_request_size_mb: int
    min_password_length: int
    allowed_hosts: tuple[str, ...]
    production_mode: bool
    server_url: str
    login_rate_limit_attempts: int
    login_rate_limit_window_seconds: int
    otp_enabled: bool
    vision_provider: str
    tableau_lookup_enabled: bool
    otp_length: int
    otp_ttl_seconds: int
    otp_max_attempts: int
    otp_send_rate_limit_attempts: int
    otp_send_rate_limit_window_seconds: int
    otp_dev_log_codes: bool
    sms_provider: str
    twilio_account_sid: str
    twilio_auth_token: str
    twilio_from_number: str
    twilio_messaging_service_sid: str
    bootstrap_admin_email: str
    bootstrap_admin_name: str
    bootstrap_admin_password: str
    bootstrap_admin_case_prefix: str
    smtp_host: str
    smtp_port: int
    smtp_username: str
    smtp_password: str
    smtp_from: str
    smtp_use_tls: bool
    smtp_use_starttls: bool

    def ensure_runtime_dirs(self) -> None:
        self.data_dir.mkdir(parents=True, exist_ok=True)
        (self.data_dir / 'cache').mkdir(parents=True, exist_ok=True)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.upload_dir.mkdir(parents=True, exist_ok=True)
        self.generated_dir.mkdir(parents=True, exist_ok=True)


settings = Settings(
    app_name=os.getenv('KV_APP_NAME', 'Kontroll'),
    brand_org_name=os.getenv('KV_BRAND_ORG_NAME', 'Minfiskerikontroll').strip() or 'Minfiskerikontroll',
    app_version=os.getenv('KV_APP_VERSION', '1.8.42'),
    app_version_label=os.getenv('KV_APP_VERSION_LABEL', '1.8.42'),
    base_dir=BASE_DIR,
    data_dir=_runtime_path('KV_DATA_DIR', _RUNTIME_STORAGE_ROOT / 'data'),
    templates_dir=BASE_DIR / 'app' / 'templates',
    static_dir=BASE_DIR / 'app' / 'static',
    upload_dir=_runtime_path('KV_UPLOAD_DIR', _RUNTIME_STORAGE_ROOT / 'uploads'),
    generated_dir=_runtime_path('KV_GENERATED_DIR', _RUNTIME_STORAGE_ROOT / 'generated'),
    db_path=_runtime_path('KV_DB_PATH', _RUNTIME_STORAGE_ROOT / 'kv_kontroll.db'),
    session_secret=os.getenv('SESSION_SECRET', 'dev-session-secret-change-me'),
    session_same_site=_session_same_site,
    session_https_only=_session_https_only,
    session_max_age_seconds=_env_int('KV_SESSION_MAX_AGE_SECONDS', 12 * 60 * 60, minimum=15 * 60, maximum=14 * 24 * 60 * 60),
    session_idle_minutes=_env_int('KV_SESSION_IDLE_MINUTES', 30 if PRODUCTION_MODE else 120, minimum=5, maximum=24 * 60),
    session_absolute_minutes=_env_int('KV_SESSION_ABSOLUTE_MINUTES', 12 * 60, minimum=30, maximum=7 * 24 * 60),
    log_level=os.getenv('KV_LOG_LEVEL', 'INFO').upper(),
    max_upload_size_mb=_DEFAULT_MAX_UPLOAD_MB,
    max_request_size_mb=_DEFAULT_MAX_REQUEST_MB,
    min_password_length=max(10, _env_int('KV_MIN_PASSWORD_LENGTH', 12, minimum=10, maximum=128)),
    allowed_hosts=tuple(_allowed_hosts),
    production_mode=PRODUCTION_MODE,
    server_url=SERVER_URL,
    login_rate_limit_attempts=_env_int('KV_LOGIN_RATE_LIMIT_ATTEMPTS', 10, minimum=3, maximum=100),
    login_rate_limit_window_seconds=_env_int('KV_LOGIN_RATE_LIMIT_WINDOW_SECONDS', 15 * 60, minimum=60, maximum=24 * 60 * 60),
    otp_enabled=_env_flag('KV_OTP_ENABLED', False),
    vision_provider=str(os.getenv('KV_VISION_PROVIDER', 'local') or 'local').strip().lower(),
    tableau_lookup_enabled=_env_flag('KV_TABLEAU_LOOKUP_ENABLED', True),
    otp_length=_env_int('KV_OTP_LENGTH', 6, minimum=6, maximum=8),
    otp_ttl_seconds=_env_int('KV_OTP_TTL_SECONDS', 5 * 60, minimum=60, maximum=30 * 60),
    otp_max_attempts=_env_int('KV_OTP_MAX_ATTEMPTS', 5, minimum=3, maximum=10),
    otp_send_rate_limit_attempts=_env_int('KV_OTP_SEND_RATE_LIMIT_ATTEMPTS', 3, minimum=1, maximum=20),
    otp_send_rate_limit_window_seconds=_env_int('KV_OTP_SEND_RATE_LIMIT_WINDOW_SECONDS', 10 * 60, minimum=60, maximum=60 * 60),
    otp_dev_log_codes=_env_flag('KV_OTP_DEV_LOG_CODES', (not PRODUCTION_MODE and not _render_runtime())),
    sms_provider=os.getenv('KV_SMS_PROVIDER', 'twilio').strip().lower(),
    twilio_account_sid=os.getenv('TWILIO_ACCOUNT_SID', '').strip() or os.getenv('KV_TWILIO_ACCOUNT_SID', '').strip(),
    twilio_auth_token=os.getenv('TWILIO_AUTH_TOKEN', '') or os.getenv('KV_TWILIO_AUTH_TOKEN', ''),
    twilio_from_number=os.getenv('TWILIO_FROM_NUMBER', '').strip() or os.getenv('KV_TWILIO_FROM_NUMBER', '').strip(),
    twilio_messaging_service_sid=os.getenv('TWILIO_MESSAGING_SERVICE_SID', '').strip() or os.getenv('KV_TWILIO_MESSAGING_SERVICE_SID', '').strip(),
    bootstrap_admin_email=os.getenv('KV_BOOTSTRAP_ADMIN_EMAIL', '').strip().lower(),
    bootstrap_admin_name=os.getenv('KV_BOOTSTRAP_ADMIN_NAME', '').strip(),
    bootstrap_admin_password=os.getenv('KV_BOOTSTRAP_ADMIN_PASSWORD', ''),
    bootstrap_admin_case_prefix=os.getenv('KV_BOOTSTRAP_ADMIN_PREFIX', 'LBHN').strip().upper() or 'LBHN',
    smtp_host=os.getenv('KV_SMTP_HOST', '').strip(),
    smtp_port=_env_int('KV_SMTP_PORT', 587, minimum=1, maximum=65535),
    smtp_username=os.getenv('KV_SMTP_USERNAME', '').strip(),
    smtp_password=os.getenv('KV_SMTP_PASSWORD', ''),
    smtp_from=os.getenv('KV_SMTP_FROM', '').strip(),
    smtp_use_tls=_env_flag('KV_SMTP_USE_TLS', False),
    smtp_use_starttls=_env_flag('KV_SMTP_USE_STARTTLS', True),
)
