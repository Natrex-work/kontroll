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
            assert 'admin@kv.demo' not in login_page.text
            assert 'kontrollor@kv.demo' not in login_page.text
            assert 'Admin123!' not in login_page.text
            assert 'Demo123!' not in login_page.text
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
            map_catalog = client.get('/api/map/catalog')
            assert map_catalog.status_code == 200
            map_catalog_json = map_catalog.json()
            assert len(map_catalog_json.get('layers') or []) >= 20
            layer_names = ' | '.join(item.get('name') or '' for item in map_catalog_json.get('layers') or [])
            assert 'J-melding stengte fiskefelt' in layer_names
            assert 'Hummer - fredningsområder' in layer_names

            regelverk = client.get('/regelverk')
            assert regelverk.status_code == 200

            rules_without_coords = client.get('/api/rules', params={'control_type': 'Fritidsfiske', 'species': 'Hummer', 'gear_type': 'Teine', 'lat': '', 'lng': ''})
            assert rules_without_coords.status_code == 200, rules_without_coords.text
            rules_without_coords_json = rules_without_coords.json()
            rule_keys = {item.get('key') for item in rules_without_coords_json.get('items') or []}
            assert 'hummerdeltakernummer' in rule_keys
            assert 'hummer_periode' in rule_keys

            import app.live_sources as live_sources
            import app.registry as registry_module

            orig_lookup_directory_candidates = live_sources.lookup_directory_candidates
            orig_lookup_hummer_participant_live = live_sources.lookup_hummer_participant_live
            orig_lookup_hummer_participant = registry_module.lookup_hummer_participant
            try:
                live_sources.lookup_directory_candidates = lambda phone='', name='', address='': {
                    'found': True,
                    'person': {
                        'name': name or 'Ola Nordmann',
                        'address': 'Bryggeveien 1, 3480 Tofte',
                        'phone': phone or '90000000',
                        'source': '1881',
                        'source_url': 'https://example.invalid/1881'
                    },
                    'candidates': [{
                        'name': name or 'Ola Nordmann',
                        'address': 'Bryggeveien 1, 3480 Tofte',
                        'phone': phone or '90000000',
                        'source': '1881',
                        'source_url': 'https://example.invalid/1881'
                    }],
                    'message': 'Treff i offentlig katalog.'
                }
                registry_module.lookup_hummer_participant = lambda participant_no='', name='': {
                    'found': bool((name or '').strip().lower() == 'ola nordmann'),
                    'person': {
                        'participant_no': 'H-2026-123',
                        'name': 'Ola Nordmann',
                        'last_registered_display': '2026-sesongen',
                        'fisher_type': 'fritidsfiskar',
                        'source': 'Hummerregister',
                        'source_url': 'https://example.invalid/hummer'
                    } if (name or '').strip().lower() == 'ola nordmann' else {},
                    'candidates': [{
                        'participant_no': 'H-2026-123',
                        'name': 'Ola Nordmann',
                        'last_registered_display': '2026-sesongen',
                        'fisher_type': 'fritidsfiskar',
                        'source': 'Hummerregister',
                        'source_url': 'https://example.invalid/hummer'
                    }] if (name or '').strip().lower() == 'ola nordmann' else [],
                    'message': 'Treff i lokal eller hurtigbufret hummerdeltakerliste.' if (name or '').strip().lower() == 'ola nordmann' else 'Ingen treff'
                }
                live_sources.lookup_hummer_participant_live = lambda participant_no='', name='': registry_module.lookup_hummer_participant(participant_no=participant_no, name=name)
                registry_lookup = client.get('/api/registry/lookup', params={
                    'phone': '90000000',
                    'address': 'Bryggeveien 1',
                    'post_place': '3480 Tofte',
                    'name': 'Ola Nordmann'
                })
                assert registry_lookup.status_code == 200, registry_lookup.text
                registry_json = registry_lookup.json()
                assert registry_json.get('found') is True
                assert (registry_json.get('person') or {}).get('name') == 'Ola Nordmann'
                assert (registry_json.get('person') or {}).get('hummer_participant_no') == 'H-2026-123'
                assert (registry_json.get('person') or {}).get('hummer_last_registered') == '2026-sesongen'
            finally:
                live_sources.lookup_directory_candidates = orig_lookup_directory_candidates
                live_sources.lookup_hummer_participant_live = orig_lookup_hummer_participant_live
                registry_module.lookup_hummer_participant = orig_lookup_hummer_participant

            offline_new = client.get('/cases/offline/new?local_id=local-smoke-1')
            assert offline_new.status_code == 200
            assert 'lokal sakskladd' in offline_new.text.lower()
            offline_csrf = extract_csrf(offline_new.text)
            offline_payload = {
                'csrf_token': offline_csrf,
                'local_case_id': 'local-smoke-1',
                'case_number_suffix': '124',
                'investigator_name': 'Test Admin',
                'status': 'Utkast',
                'case_basis': 'patruljeobservasjon',
                'basis_source_name': 'Kystvakten lettbåt',
                'basis_details': 'Offline opprettet testkontroll.',
                'control_type': 'Fritidsfiske',
                'fishery_type': 'Hummer',
                'species': 'Hummer',
                'gear_type': 'Teine',
                'start_time': '2026-04-18T12:00',
                'location_name': 'Tofte',
                'latitude': '59.535400',
                'longitude': '10.536600',
                'findings_json': '[]',
                'source_snapshot_json': '[]',
                'crew_json': '[]',
                'external_actors_json': '[]',
                'interview_sessions_json': '[]',
            }
            offline_create = client.post('/api/cases/create-from-draft', data=offline_payload)
            assert offline_create.status_code == 200, offline_create.text
            offline_json = offline_create.json()
            assert offline_json.get('ok') is True
            assert str(offline_json.get('case_url') or '').endswith('/edit')

            create_case = client.post('/cases/new', data={'csrf_token': dashboard_csrf}, follow_redirects=False)
            assert create_case.status_code in {302, 303}
            edit_url = create_case.headers['location']
            assert edit_url.endswith('/edit?new_case=1&step=1')

            edit = client.get(edit_url)
            assert edit.status_code == 200
            assert 'data-force-start-step="1"' in edit.text
            assert 'data-start-step="1"' in edit.text
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

            map_features = client.get('/api/map/features', params={'layer_id': 76, 'bbox': '10.0,59.0,11.0,60.0'})
            assert map_features.status_code == 200
            zones = client.get('/api/zones/check', params={'lat': 59.5354, 'lng': 10.5366, 'species': 'Hummer', 'gear_type': 'Teine'})
            assert zones.status_code == 200
            zone_json = zones.json()
            assert zone_json.get('status') in {'fredningsområde', 'ingen treff', 'regulert område', 'stengt område', 'maksimalmål område'}

        return 0
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


if __name__ == '__main__':
    raise SystemExit(main())
