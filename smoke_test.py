from __future__ import annotations

import importlib
import os
import re
import shutil
import tempfile
from pathlib import Path

from fastapi.testclient import TestClient


CSRF_RE = re.compile(r"name=[\"']csrf_token[\"']\\s+value=[\"']([^\"']+)[\"']|<meta name=[\"']csrf-token[\"'] content=[\"']([^\"']+)[\"']", re.IGNORECASE)


def extract_csrf(html: str) -> str:
    match = CSRF_RE.search(html)
    if not match:
        raise AssertionError('Fant ikke CSRF-token i HTML')
    return match.group(1) or match.group(2)


def build_test_app() -> tuple[object, Path]:
    tmpdir = Path(tempfile.mkdtemp(prefix='kvtrial-'))
    os.environ['KV_DB_PATH'] = str(tmpdir / 'kv_kontroll.db')
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

    import app.config
    import app.db
    import app.main

    importlib.reload(app.config)
    importlib.reload(app.db)
    importlib.reload(app.main)
    return app.main.app, tmpdir


def main() -> int:
    app, tmpdir = build_test_app()
    try:
        with TestClient(app, base_url='https://testserver') as client:
            health = client.get('/healthz')
            assert health.status_code == 200
            assert health.json()['status'] == 'ok'

            docs = client.get('/docs')
            assert docs.status_code == 404
            openapi = client.get('/openapi.json')
            assert openapi.status_code == 404
            uploads = client.get('/uploads/test.jpg')
            assert uploads.status_code in {404, 405}

            login_page = client.get('/login')
            assert login_page.status_code == 200
            login_csrf = extract_csrf(login_page.text)

            login = client.post('/login', data={'email': 'admin@example.no', 'password': 'TestPass123!Test', 'csrf_token': login_csrf}, follow_redirects=False)
            assert login.status_code in {302, 303}, login.text
            assert login.headers['location'] == '/dashboard'
            session_cookie = login.cookies.get('kv_session') or client.cookies.get('kv_session')
            assert session_cookie

            dashboard = client.get('/dashboard')
            assert dashboard.status_code == 200
            assert dashboard.headers.get('content-security-policy')
            assert dashboard.headers.get('x-frame-options') == 'DENY'
            dashboard_csrf = extract_csrf(dashboard.text)

            kart = client.get('/kart')
            assert kart.status_code == 200

            regelverk = client.get('/regelverk')
            assert regelverk.status_code == 200

            create_case = client.post('/cases/new', data={'csrf_token': dashboard_csrf}, follow_redirects=False)
            assert create_case.status_code in {302, 303}
            edit_url = create_case.headers['location']
            assert edit_url.endswith('/edit')

            edit = client.get(edit_url)
            assert edit.status_code == 200
            case_id = int(edit_url.split('/')[-2])
            case_csrf = extract_csrf(edit.text)

            payload = {
                'csrf_token': case_csrf,
                'case_number_suffix': '123',
                'investigator_name': 'Test Admin',
                'status': 'Utkast',
                'case_basis': 'patruljeobservasjon',
                'basis_source_name': 'Kystvakten lettbåt',
                'basis_details': 'Planlagt kontroll i testområde.',
                'control_type': 'Fritidsfiske',
                'fishery_type': 'Hummer',
                'species': 'Hummer',
                'gear_type': 'Teine',
                'start_time': '2026-04-18T12:00',
                'end_time': '',
                'location_name': 'Tofte',
                'latitude': '59.535400',
                'longitude': '10.536600',
                'area_status': 'fredningsområde',
                'area_name': 'Hummer - fredningsområde Tofte',
                'suspect_name': 'Test Person',
                'suspect_phone': '90000000',
                'suspect_birthdate': '01.01.1980',
                'suspect_address': 'Bryggeveien 1',
                'suspect_post_place': '3480 Tofte',
                'lookup_text': '',
                'vessel_name': 'MS Test',
                'vessel_reg': 'LB-1-T',
                'radio_call_sign': 'LA1234',
                'notes': 'Testnotat',
                'hearing_text': 'Forklaring',
                'seizure_notes': 'Ingen beslag',
                'summary': 'Kort oppsummering',
                'findings_json': '[]',
                'source_snapshot_json': '[]',
                'crew_json': '[]',
                'external_actors_json': '[]',
                'interview_sessions_json': '[]',
                'hummer_participant_no': '',
                'hummer_last_registered': '',
                'observed_gear_count': '0',
                'complaint_override': '',
                'own_report_override': '',
                'interview_report_override': '',
                'seizure_report_override': '',
                'complainant_signature': 'Test Admin',
                'witness_signature': 'Test Admin',
                'investigator_signature': 'Test Admin',
                'suspect_signature': 'Test Person',
            }
            save = client.post(f'/cases/{case_id}/save', data=payload, follow_redirects=False)
            assert save.status_code in {302, 303}, save.text
            assert 'case_number_saved=1' in save.headers['location']

            preview = client.get(f'/cases/{case_id}/preview')
            assert preview.status_code == 200
            assert 'Tilbake til sak' in preview.text
            assert 'LBHN 26 123' in preview.text
            preview_csrf = extract_csrf(preview.text)

            export_pdf = client.post(f'/cases/{case_id}/pdf', data={'csrf_token': preview_csrf})
            assert export_pdf.status_code == 200
            assert export_pdf.headers['content-type'].startswith('application/pdf')

            zones = client.get('/api/zones/check', params={'lat': 59.5354, 'lng': 10.5366, 'species': 'Hummer', 'gear_type': 'Teine'})
            assert zones.status_code == 200
            zone_json = zones.json()
            assert zone_json.get('status') in {'fredningsområde', 'ingen treff', 'regulert område'}

        return 0
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


if __name__ == '__main__':
    raise SystemExit(main())
