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
    session_secret: str
    session_same_site: str
    session_https_only: bool
    log_level: str
    max_upload_size_mb: int

    def ensure_runtime_dirs(self) -> None:
        self.upload_dir.mkdir(parents=True, exist_ok=True)
        self.generated_dir.mkdir(parents=True, exist_ok=True)


settings = Settings(
    app_name=os.getenv('KV_APP_NAME', 'Kontroll Og Oppsyn v40'),
    app_version=os.getenv('KV_APP_VERSION', '40.0.0'),
    app_version_label=os.getenv('KV_APP_VERSION_LABEL', 'v40'),
    base_dir=BASE_DIR,
    templates_dir=BASE_DIR / 'app' / 'templates',
    static_dir=BASE_DIR / 'app' / 'static',
    upload_dir=Path(os.getenv('KV_UPLOAD_DIR', str(BASE_DIR / 'uploads'))),
    generated_dir=Path(os.getenv('KV_GENERATED_DIR', str(BASE_DIR / 'generated'))),
    db_path=Path(os.getenv('KV_DB_PATH', str(BASE_DIR / 'kv_kontroll_demo.db'))),
    session_secret=os.getenv('SESSION_SECRET', 'dev-session-secret-change-me'),
    session_same_site=os.getenv('KV_SESSION_SAMESITE', 'lax'),
    session_https_only=_env_flag('KV_SESSION_HTTPS_ONLY', False),
    log_level=os.getenv('KV_LOG_LEVEL', 'INFO').upper(),
    max_upload_size_mb=max(1, int(os.getenv('KV_MAX_UPLOAD_MB', '25'))),
)
