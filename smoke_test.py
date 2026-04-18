from __future__ import annotations

import io
import json
import os
import sqlite3
import tempfile
import zipfile
from pathlib import Path

os.environ['KV_DISABLE_CSRF'] = '1'
os.environ['KV_PRODUCTION_MODE'] = '0'
os.environ['KV_BOOTSTRAP_DEMO_USERS'] = '0'
os.environ['KV_BOOTSTRAP_DEMO_CASES'] = '0'
_tmpdir = tempfile.mkdtemp(prefix='kv_smoke_')
os.environ['KV_DB_PATH'] = str(Path(_tmpdir) / 'smoke.db')
os.environ['KV_UPLOAD_DIR'] = str(Path(_tmpdir) / 'uploads')
os.environ['KV_GENERATED_DIR'] = str(Path(_tmpdir) / 'generated')
os.environ['SESSION_SECRET'] = 'SmoketestSessionSecret123!'
os.environ['KV_DATA_ENCRYPTION_KEY'] = 'SmoketestEncryptionKey123!'

from fastapi.testclient import TestClient

from app import db
from app.auth import hash_password
from app.main import app
from app.services.bootstrap_service import initialize_application_data


def main() -> None:
    initialize_application_data()
    if not db.get_user_by_email('admin@test.no'):
        db.create_user(
            email='admin@test.no',
            full_name='Admin Test',
            password_hash=hash_password('AdminTest123!'),
            role='admin',
            case_prefix='LBHN',
        )
    if not db.get_user_by_email('bruker@test.no'):
        db.create_user(
            email='bruker@test.no',
            full_name='Bruker Test',
            password_hash=hash_password('BrukerTest123!'),
            role='investigator',
            permissions=['kv_kontroll', 'kart', 'regelverk'],
            case_prefix='LBHN',
        )

    with TestClient(app) as client:
        assert client.get('/login').status_code == 200
        login = client.post('/login', data={'email': 'bruker@test.no', 'password': 'BrukerTest123!'}, follow_redirects=False)
        assert login.status_code in {302, 303}

        case_redirect = client.get('/cases/new', follow_redirects=False)
        assert case_redirect.status_code in {302, 303}
        case_id = int(case_redirect.headers['location'].split('/')[2])

        save_payload = {
            'case_basis': 'patruljeobservasjon',
            'basis_details': 'Det ble fra Kystvakten lettbåt gjennomført kontroll av fritidsfiske i testområde.',
            'control_type': 'Fritidsfiske',
            'fishery_type': 'Hummer',
            'species': 'Hummer',
            'gear_type': 'Teine',
            'start_time': '2026-04-15T10:00',
            'location_name': 'Testhavn',
            'latitude': '58.2',
            'longitude': '8.4',
            'area_status': 'stengt område',
            'area_name': 'Testområde',
            'suspect_name': 'Ola Test',
            'suspect_phone': '90000000',
            'suspect_address': 'Kaiveien 1',
            'suspect_post_place': '0001 Oslo',
            'notes': 'Kontrollen avdekket ett forhold.',
            'summary': '',
            'findings_json': json.dumps([
                {
                    'key': 'hummer_lengdekrav',
                    'label': 'Lengdekrav hummer',
                    'status': 'avvik',
                    'notes': 'En hummer ble målt til 22,3 cm.',
                    'measurements': [{'reference': 'LBHN 26 001-01', 'length_cm': '22.3', 'violation_text': 'Målt 22,3 cm.'}],
                }
            ]),
            'source_snapshot_json': '[]',
            'crew_json': '[]',
            'external_actors_json': '[]',
            'interview_sessions_json': '[]',
        }
        save_resp = client.post(f'/cases/{case_id}/save', data=save_payload, follow_redirects=False)
        assert save_resp.status_code in {302, 303}

        upload = client.post(
            f'/api/cases/{case_id}/evidence',
            data={'caption': 'Testbilde'},
            files={'file': ('test.png', b'\x89PNG\r\n\x1a\n', 'image/png')},
        )
        assert upload.status_code == 200
        payload = upload.json()['evidence']
        assert payload['url'].startswith('/evidence/')
        assert client.get(payload['url']).status_code == 200

        preview = client.get(f'/cases/{case_id}/preview')
        assert preview.status_code == 200
        assert '/cases/' in preview.text

        pdf_resp = client.get(f'/cases/{case_id}/pdf')
        assert pdf_resp.status_code == 200
        assert pdf_resp.headers.get('content-type', '').startswith('application/pdf')

        zip_resp = client.get(f'/cases/{case_id}/bundle')
        assert zip_resp.status_code == 200
        archive = zipfile.ZipFile(io.BytesIO(zip_resp.content))
        names = archive.namelist()
        assert any(name.startswith('pdf/') for name in names)
        assert 'metadata/case.json' in names

    raw_db = sqlite3.connect(os.environ['KV_DB_PATH'])
    raw = raw_db.execute('SELECT suspect_name, suspect_phone, summary FROM cases LIMIT 1').fetchone()
    assert raw is not None
    assert all((value is None or str(value).startswith('enc::') or value == '') for value in raw)
    print('Smoke test bestått.')


if __name__ == '__main__':
    main()
