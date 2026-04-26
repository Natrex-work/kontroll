from __future__ import annotations

import importlib
import os
import re
import shutil
import tempfile
from io import BytesIO
from pathlib import Path

from fastapi.testclient import TestClient
from PIL import Image, ImageDraw, ImageFont


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




def build_synthetic_ocr_image_bytes() -> bytes:
    width, height = 4032, 3024
    image = Image.new('RGB', (width, height), '#7ba6d5')
    draw = ImageDraw.Draw(image)
    label_box = (1500, 1200, 2400, 1650)
    draw.rounded_rectangle(label_box, radius=30, fill='white', outline='black', width=3)
    try:
        font = ImageFont.truetype('/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf', 28)
    except Exception:
        font = ImageFont.load_default()
    text = 'Navn\nOla Nordmann\nAdresse\nSjøveien 12\n8123 HAVN\nMobil\n90123456\nDeltakernummer\nH-2026-123\nMerke-ID\nLOB-HUM-1323'
    draw.multiline_text((1560, 1240), text, fill='black', font=font, spacing=6)
    buffer = BytesIO()
    image.save(buffer, format='JPEG', quality=92)
    return buffer.getvalue()


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

            create_case = client.post('/cases/new', data={'csrf_token': dashboard_csrf}, follow_redirects=False)
            assert create_case.status_code in {302, 303}, create_case.text
            edit = client.get(create_case.headers['location'])
            assert edit.status_code == 200, edit.text
            assert 'case-map-layer-panel-host' in edit.text
            assert 'toggle-zone-hit-overlay' in edit.text

            kart = client.get('/kart')
            assert kart.status_code == 200
            map_catalog = client.get('/api/map/catalog')
            assert map_catalog.status_code == 200
            map_catalog_json = map_catalog.json()
            assert len(map_catalog_json.get('layers') or []) >= 20
            layer_names = ' | '.join(item.get('name') or '' for item in map_catalog_json.get('layers') or [])
            assert 'J-melding stengte fiskefelt' in layer_names
            assert 'Hummer - fredningsområder' in layer_names

            zone_hit = client.get('/api/zones/check', params={
                'lat': 59.53525,
                'lng': 10.5355,
                'species': 'Hummer',
                'gear_type': 'Teine',
                'control_type': 'Fritidsfiske',
            })
            assert zone_hit.status_code == 200, zone_hit.text
            zone_hit_json = zone_hit.json()
            assert zone_hit_json.get('match') is True
            assert any((item.get('layer_ids') or [item.get('layer_id')]) for item in zone_hit_json.get('hits') or [])
            assert any((item.get('feature') or {}).get('geometry') for item in zone_hit_json.get('hits') or [])

            legacy_bundle = client.get('/api/map/bundle', params={
                'bbox': '10.3355,59.33525,10.7355,59.73525',
                'layer_ids': '1'
            })
            assert legacy_bundle.status_code == 200, legacy_bundle.text
            legacy_bundle_json = legacy_bundle.json()
            assert len(legacy_bundle_json.get('features') or []) >= 1
            assert any('Hummer - fredningsområder' == str(item.get('name') or '') for item in legacy_bundle_json.get('layers') or [])

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

            assert registry_module._normalize_hummer_no('H-2026-123') == 'H-2026-123'
            assert registry_module._normalize_hummer_no('LBHN 26 123') == ''
            parsed_hints = registry_module.extract_tag_hints('''Navn
Bernt Hernes
Adresse
Storgata 5
4512 Mandal
Mobil
41234567
Deltakernummer
H-2026-123
Merke-ID
LOB-HUM-1323''')
            assert parsed_hints.get('name') == 'Bernt Hernes'
            assert parsed_hints.get('address') == 'Storgata 5'
            assert parsed_hints.get('post_place') == '4512 Mandal'
            assert parsed_hints.get('phone') == '41234567'
            assert parsed_hints.get('hummer_participant_no') == 'H-2026-123'
            assert parsed_hints.get('gear_marker_id') == 'LOB-HUM-1323'

            import app.services.ocr_service as ocr_service
            synthetic_ocr = None
            try:
                synthetic_ocr = ocr_service.extract_text_from_image(build_synthetic_ocr_image_bytes(), filename='syntetisk-ocr.jpg', timeout_seconds=20)
            except RuntimeError as exc:
                if 'ikke installert' not in str(exc).lower():
                    raise
            if synthetic_ocr is not None:
                synthetic_hints = synthetic_ocr.get('hints') or {}
                assert synthetic_hints.get('name') == 'Ola Nordmann'
                assert synthetic_hints.get('address') == 'Sjøveien 12'
                assert synthetic_hints.get('post_place') == '8123 HAVN'
                assert synthetic_hints.get('phone') == '90123456'
                assert synthetic_hints.get('hummer_participant_no') == 'H-2026-123'
                assert synthetic_hints.get('gear_marker_id') == 'LOB-HUM-1323'
                ocr_api = client.post('/api/ocr/extract', headers={'X-CSRF-Token': dashboard_csrf}, files={'file': ('syntetisk-ocr.jpg', build_synthetic_ocr_image_bytes(), 'image/jpeg')})
                assert ocr_api.status_code == 200, ocr_api.text
                ocr_api_json = ocr_api.json()
                assert ocr_api_json.get('ok') is True
                assert (ocr_api_json.get('hints') or {}).get('name') == 'Ola Nordmann'

            summary_suggest = client.post('/api/summary/suggest', json={
                'case_basis': 'patruljeobservasjon',
                'control_type': 'Fritidsfiske',
                'species': 'Hummer',
                'gear_type': 'Teine',
                'location_name': 'Tofte',
                'area_name': 'Hummerfredningsområde Tofte',
                'area_status': 'fredningsområde',
                'suspect_name': 'Test Person',
                'basis_details': 'Planlagt kontroll i testområde.',
                'start_time': '2026-04-18T12:00',
                'latitude': 59.5354,
                'longitude': 10.5366,
                'findings': [{
                    'key': 'hummer_fredningsomrade_redskap',
                    'label': 'Valgt redskap i hummerfredningsområde',
                    'status': 'avvik',
                    'summary_text': 'I oppgitt posisjon ble teine observert og kontrollert i Hummerfredningsområde Tofte. Dette redskapet er ikke tillatt i hummerfredningsområdet.',
                    'notes': 'I oppgitt posisjon står redskapet i Hummerfredningsområde Tofte, registrert som hummerfredningsområde. Valgt redskap (teine) er ikke tillatt i dette området.'
                }]
            }, headers={'x-csrf-token': dashboard_csrf, 'origin': 'https://testserver'})
            assert summary_suggest.status_code == 200, summary_suggest.text
            summary_json = summary_suggest.json()
            summary_text = summary_json.get('summary', '').lower()
            assert 'teine' in summary_text
            assert 'hummerfredningsområde tofte' in summary_text
            assert any(token in summary_text for token in ['regulering', 'begrensning', 'ikke tillatt', 'forbud'])

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
            if zone_json.get('match'):
                assert any((item.get('feature') or {}).get('geometry') for item in zone_json.get('hits') or [])

        return 0
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


if __name__ == '__main__':
    # Some native OCR/PDF dependencies keep background handles alive after all
    # assertions have completed. Flush output and terminate explicitly so CI and
    # Render smoke checks do not wait for unrelated native cleanup.
    import os as _os
    import sys as _sys
    _code = main()
    _sys.stdout.flush()
    _sys.stderr.flush()
    _os._exit(_code)
