from __future__ import annotations

import importlib
import os
import shutil
import sys
import tempfile
from pathlib import Path

from fastapi.testclient import TestClient


ENV_KEYS = [
    'KV_DB_PATH',
    'KV_UPLOAD_DIR',
    'KV_GENERATED_DIR',
    'KV_LIVE_SOURCES',
    'KV_PRODUCTION_MODE',
    'KV_ALLOWED_HOSTS',
    'KV_SESSION_HTTPS_ONLY',
    'SESSION_SECRET',
    'KV_DATA_ENCRYPTION_KEY',
    'KV_BOOTSTRAP_ADMIN_EMAIL',
    'KV_BOOTSTRAP_ADMIN_NAME',
    'KV_BOOTSTRAP_ADMIN_PASSWORD',
    'KV_BOOTSTRAP_ADMIN_PREFIX',
    'SERVER_URL',
    'RENDER',
    'RENDER_EXTERNAL_HOSTNAME',
    'RENDER_EXTERNAL_URL',
]


def reset_app_modules() -> None:
    for name in list(sys.modules):
        if name.startswith('app'):
            sys.modules.pop(name, None)


def clear_env() -> None:
    for key in ENV_KEYS:
        os.environ.pop(key, None)


def test_render_external_hostname_allows_healthcheck() -> None:
    tmpdir = Path(tempfile.mkdtemp(prefix='kvtrial-render-host-'))
    try:
        clear_env()
        os.environ['KV_DB_PATH'] = str(tmpdir / 'kv_kontroll.db')
        os.environ['KV_UPLOAD_DIR'] = str(tmpdir / 'uploads')
        os.environ['KV_GENERATED_DIR'] = str(tmpdir / 'generated')
        os.environ['KV_LIVE_SOURCES'] = '0'
        os.environ['KV_PRODUCTION_MODE'] = '1'
        os.environ['KV_SESSION_HTTPS_ONLY'] = '1'
        os.environ['SESSION_SECRET'] = 'test-session-secret-1234567890-very-secure'
        os.environ['KV_DATA_ENCRYPTION_KEY'] = 'test-encryption-key-1234567890-very-secure'
        os.environ['RENDER'] = 'true'
        os.environ['RENDER_EXTERNAL_HOSTNAME'] = 'kv-hotfix.onrender.com'
        os.environ['RENDER_EXTERNAL_URL'] = 'https://kv-hotfix.onrender.com'

        reset_app_modules()
        import app.main

        importlib.reload(app.main)
        with TestClient(app.main.app, base_url='https://kv-hotfix.onrender.com') as client:
            response = client.get('/healthz')
            assert response.status_code == 200, response.text
            assert response.json()['status'] == 'ok'
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)
        clear_env()



def test_db_parent_directory_is_created_automatically() -> None:
    tmpdir = Path(tempfile.mkdtemp(prefix='kvtrial-render-db-'))
    try:
        nested_db = tmpdir / 'var' / 'data' / 'fiskerikontroll' / 'kv_kontroll.db'
        clear_env()
        os.environ['KV_DB_PATH'] = str(nested_db)
        os.environ['KV_UPLOAD_DIR'] = str(tmpdir / 'uploads')
        os.environ['KV_GENERATED_DIR'] = str(tmpdir / 'generated')
        os.environ['KV_LIVE_SOURCES'] = '0'
        os.environ['KV_PRODUCTION_MODE'] = '1'
        os.environ['KV_ALLOWED_HOSTS'] = 'testserver'
        os.environ['KV_SESSION_HTTPS_ONLY'] = '1'
        os.environ['SESSION_SECRET'] = 'test-session-secret-1234567890-very-secure'
        os.environ['KV_DATA_ENCRYPTION_KEY'] = 'test-encryption-key-1234567890-very-secure'
        os.environ['KV_BOOTSTRAP_ADMIN_EMAIL'] = 'admin@example.no'
        os.environ['KV_BOOTSTRAP_ADMIN_NAME'] = 'Test Admin'
        os.environ['KV_BOOTSTRAP_ADMIN_PASSWORD'] = 'TestPass123!Test'
        os.environ['KV_BOOTSTRAP_ADMIN_PREFIX'] = 'LBHN'

        reset_app_modules()
        import app.main

        importlib.reload(app.main)
        with TestClient(app.main.app, base_url='https://testserver') as client:
            response = client.get('/healthz')
            assert response.status_code == 200, response.text
        assert nested_db.parent.exists(), f'Mappen ble ikke opprettet: {nested_db.parent}'
        assert nested_db.exists(), f'DB-filen ble ikke opprettet: {nested_db}'
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)
        clear_env()



def main() -> int:
    test_render_external_hostname_allows_healthcheck()
    test_db_parent_directory_is_created_automatically()
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
