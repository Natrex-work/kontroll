from __future__ import annotations

import io
import json
import zipfile

from fastapi.testclient import TestClient

from app.main import app, seed_default_users, seed_demo_cases_if_empty
from app import db, live_sources


def main() -> None:
    db.init_db()
    seed_default_users()
    seed_demo_cases_if_empty()
    with TestClient(app) as client:
        assert client.get('/login').status_code == 200

        admin_login = client.post('/login', data={'email': 'admin@kv.demo', 'password': 'Admin123!'}, follow_redirects=False)
        assert admin_login.status_code in {302, 303}
        assert admin_login.headers['location'] == '/admin/users'
        assert client.get('/admin/users').status_code == 200
        assert client.get('/admin/controls').status_code == 200
        assert client.get('/dashboard').status_code == 403
        assert client.get('/kart').status_code == 403

        create_user_resp = client.post(
            '/admin/users',
            data={
                'full_name': 'Kart Testbruker',
                'email': 'kartbruker@kv.demo',
                'password': 'Kart1234!',
                'phone': '90000000',
                'address': 'Kaiveien 1, 0001 Oslo',
                'vessel_affiliation': 'KV Demo',
                'case_prefix': 'LBHN',
                'role': 'investigator',
                'permissions': ['kart'],
                'last_complainant_name': 'KV Demo Anmelder',
                'last_witness_name': 'KV Demo Vitne',
            },
            follow_redirects=False,
        )
        assert create_user_resp.status_code in {302, 303}
        created_user = db.get_user_by_email('kartbruker@kv.demo')
        assert created_user is not None
        assert db.get_user_permissions(created_user) == ['kart']
        assert created_user.get('phone') == '90000000'
        assert created_user.get('vessel_affiliation') == 'KV Demo'

        client.post('/logout')

        login = client.post('/login', data={'email': 'kontrollor@kv.demo', 'password': 'Demo123!'}, follow_redirects=False)
        assert login.status_code in {302, 303}
        assert login.headers['location'] == '/dashboard'
        assert client.get('/dashboard').status_code == 200
        assert client.get('/kart').status_code == 200
        assert client.get('/regelverk').status_code == 200
        assert client.get('/kontroller').status_code == 200

        case_redirect = client.get('/cases/new', follow_redirects=False)
        assert case_redirect.status_code in {302, 303}
        case_id = int(case_redirect.headers['location'].split('/')[2])
        edit = client.get(case_redirect.headers['location'])
        assert edit.status_code == 200
        assert 'interview-list' in edit.text
        assert 'Sletting og gjenoppretting gjøres av admin' in edit.text

        reg = client.get('/api/registry/lookup', params={'hummer_participant_no': 'H-2026-001'})
        assert reg.status_code == 200
        reg_json = reg.json()
        assert reg_json.get('found') is True
        assert reg_json.get('person', {}).get('hummer_participant_no') == 'H-2026-001'

        reg_demo = client.get('/api/registry/lookup', params={'hummer_participant_no': 'RUN-AAR-850'})
        assert reg_demo.status_code == 200
        reg_demo_json = reg_demo.json()
        assert reg_demo_json.get('found') is True
        assert reg_demo_json.get('person', {}).get('name') == 'Rune Aarland'
        assert reg_demo_json.get('person', {}).get('hummer_last_registered') in {'2026', '2026-sesongen'}

        reg_name = client.get('/api/registry/lookup', params={'name': 'Aarland, Rune'})
        assert reg_name.status_code == 200
        reg_name_json = reg_name.json()
        assert reg_name_json.get('found') is True
        assert reg_name_json.get('person', {}).get('name') == 'Rune Aarland'

        parsed_hummer_rows = live_sources._parse_hummer_csv('Namn;Deltakarnummer;Type fiskar\nAarland, Rune;RUN-AAR-850;fritidsfiskar\n')
        assert parsed_hummer_rows and parsed_hummer_rows[0].get('name') == 'Rune Aarland'
        assert parsed_hummer_rows[0].get('participant_no') == 'RUN-AAR-850'
        assert parsed_hummer_rows[0].get('fisher_type') == 'fritidsfiskar'

        for layer_id in [1, 23, 35, 37]:
            map_features = client.get('/api/map/features', params={'layer_id': layer_id})
            assert map_features.status_code == 200
            assert map_features.json().get('features')

        bundle = client.get('/api/rules', params={'control_type': 'Fritidsfiske', 'species': 'Hummer', 'gear_type': 'Samleteine / sanketeine'})
        assert bundle.status_code == 200
        bundle_json = bundle.json()
        assert 'items' in bundle_json
        assert any(item.get('key') in {'samleteine_merking', 'hummer_merking'} for item in bundle_json.get('items', []))
        assert any(item.get('key') in {'hummer_minstemal', 'minstemal_hummer'} for item in bundle_json.get('items', []))

        bundle_south = client.get('/api/rules', params={'control_type': 'Fritidsfiske', 'species': 'Hummer', 'gear_type': 'Teine', 'lat': 58.35, 'lng': 8.65})
        assert bundle_south.status_code == 200
        south_items = bundle_south.json().get('items', [])
        assert any(item.get('key') == 'hummer_lengdekrav' for item in south_items)
        assert all(item.get('key') != 'hummer_maksimalmal' for item in south_items)

        bundle_north = client.get('/api/rules', params={'control_type': 'Fritidsfiske', 'species': 'Hummer', 'gear_type': 'Teine', 'lat': 68.2, 'lng': 14.6})
        assert bundle_north.status_code == 200
        north_items = bundle_north.json().get('items', [])
        assert all(item.get('key') != 'hummer_lengdekrav' for item in north_items)

        polish = client.post('/api/text/polish', json={'mode': 'basis', 'text': 'patrulje med fokus på hummerkontroll'})
        assert polish.status_code == 200
        assert polish.json().get('text')

        summary_drafts = client.post('/api/summary/suggest', json={
            'case_basis': 'patruljeobservasjon',
            'control_type': 'Fritidsfiske',
            'species': 'Hummer',
            'fishery_type': 'Skalldyr',
            'gear_type': 'Hummerteine',
            'location_name': 'Demohamn',
            'area_name': 'Stengt testomrade',
            'area_status': 'stengt område',
            'suspect_name': 'Ola Havfisker',
            'basis_details': 'Den 14.04.2026 ble det gjennomført hummeroppsyn fra KV Nornen ved Demohamn. Patruljeformålet var å kontrollere påmelding, antall teiner og minstemål.',
            'start_time': '2026-04-14T10:00',
            'latitude': 58.2,
            'longitude': 8.4,
            'findings': [
                {
                    'key': 'hummer_lengdekrav',
                    'label': 'Lengdekrav hummer (min. 25 cm / maks. 32 cm i sør)',
                    'status': 'avvik',
                    'notes': 'To hummer kontrollmålt og dokumentert.',
                    'measurements': [
                        {
                            'reference': 'LBHN-TEST-001',
                            'length_cm': '22.3',
                            'delta_text': '2,7 cm (27 mm) under minstemålet (25 cm)',
                            'violation_text': 'Målt 22,3 cm – 2,7 cm (27 mm) under minstemålet (25 cm).',
                            'measurement_state': 'under_min',
                        }
                    ],
                },
                {'key': 'hummer_merking', 'label': 'Merking av vak', 'status': 'godkjent', 'notes': 'Merking kontrollert og funnet i orden.'}
            ],
        })
        assert summary_drafts.status_code == 200
        summary_json = summary_drafts.json()
        assert summary_json.get('basis_details', '').startswith('Den 14.04.2026 ble det gjennomført hummeroppsyn')
        assert 'Patruljeformål og begrunnelse:' in summary_json.get('summary', '')
        assert 'Registrerte avvik og forhold som anmeldes' in summary_json.get('complaint_preview', '')
        assert 'Beslag nummer LBHN-TEST-001' in summary_json.get('summary', '')
        assert 'Merking av vak' not in summary_json.get('summary', '')
        assert 'Merking av vak' not in summary_json.get('complaint_preview', '')

        save_payload = {
            'case_basis': 'patruljeobservasjon',
            'basis_details': 'Patrulje med fokus på kontroll av hummerteiner og oppbevaring av hummer.',
            'control_type': 'Fritidsfiske',
            'fishery_type': 'Skalldyr',
            'species': 'Hummer',
            'gear_type': 'Samleteine / sanketeine',
            'start_time': '2026-04-08T12:00',
            'location_name': 'Demohamn',
            'latitude': '58.2000',
            'longitude': '8.4000',
            'area_status': 'ingen treff',
            'area_name': '',
            'suspect_name': 'Ola Havfisker',
            'suspect_phone': '91500001',
            'suspect_address': 'Bryggeveien 12',
            'suspect_post_place': '3480 Demo',
            'hummer_participant_no': 'H-2026-001',
            'notes': 'Kontroll gjennomført uten bemerkninger utover demoavvik.',
            'hearing_text': '',
            'seizure_notes': '',
            'summary': '',
            'findings_json': json.dumps([
                {
                    'key': 'hummer_lengdekrav',
                    'label': 'Lengdekrav hummer (min. 25 cm / maks. 32 cm i sør)',
                    'status': 'avvik',
                    'notes': 'To hummer kontrollmålt og dokumentert.',
                    'measurements': [
                        {
                            'reference': 'LBHN-TEST-002',
                            'length_cm': '22.3',
                            'delta_text': '2,7 cm (27 mm) under minstemålet (25 cm)',
                            'violation_text': 'Målt 22,3 cm – 2,7 cm (27 mm) under minstemålet (25 cm).',
                            'measurement_state': 'under_min',
                        }
                    ],
                }
            ]),
            'source_snapshot_json': '[]',
            'crew_json': '[]',
            'external_actors_json': '[]',
            'interview_sessions_json': json.dumps([
                {
                    'id': 'i1',
                    'name': 'Ola Havfisker',
                    'role': 'mistenkte',
                    'method': 'telefon',
                    'place': 'Demohamn',
                    'start': '2026-04-08T12:10',
                    'end': '2026-04-08T12:20',
                    'transcript': 'Avhørte forklarte at han trodde hummeren var lovlig målt.',
                    'summary': 'Avhørte opplyste at målingen skjedde i god tro.',
                }
            ]),
            'observed_gear_count': '12',
        }
        save_resp = client.post(f'/cases/{case_id}/save', data=save_payload, follow_redirects=False)
        assert save_resp.status_code in {302, 303}

        autosave_resp = client.post(f'/api/cases/{case_id}/autosave', data=save_payload)
        assert autosave_resp.status_code == 200
        assert autosave_resp.json().get('ok') is True

        upload = client.post(
            f'/cases/{case_id}/evidence',
            data={'caption': 'Lydopptak avhør - Ola Havfisker'},
            files={'file': ('avhor.wav', b'RIFF\x00\x00\x00\x00WAVEfmt ', 'audio/wav')},
            follow_redirects=False,
        )
        assert upload.status_code in {302, 303}

        preview = client.get(f'/cases/{case_id}/preview')
        assert preview.status_code == 200
        assert 'Eksporter PDF og filer (ZIP)' in preview.text

        pdf_resp = client.get(f'/cases/{case_id}/pdf')
        assert pdf_resp.status_code == 200
        assert pdf_resp.headers.get('content-type', '').startswith('application/pdf')

        interview_pdf = client.get(f'/cases/{case_id}/interview-pdf')
        assert interview_pdf.status_code == 200
        assert interview_pdf.headers.get('content-type', '').startswith('application/pdf')

        zip_resp = client.get(f'/cases/{case_id}/bundle')
        assert zip_resp.status_code == 200
        assert zip_resp.headers.get('content-type', '').startswith('application/zip')
        archive = zipfile.ZipFile(io.BytesIO(zip_resp.content))
        names = archive.namelist()
        assert any(name.startswith('pdf/') and name.endswith('.pdf') for name in names)
        assert any(name.startswith('audio/') for name in names)
        assert 'metadata/case.json' in names

        client.post('/logout')

        admin_login2 = client.post('/login', data={'email': 'admin@kv.demo', 'password': 'Admin123!'}, follow_redirects=False)
        assert admin_login2.status_code in {302, 303}
        delete_resp = client.post(f'/admin/controls/{case_id}/delete', follow_redirects=False)
        assert delete_resp.status_code in {302, 303}
        deleted_case = db.get_case(case_id)
        assert deleted_case is not None and deleted_case.get('deleted_at')

        restore_resp = client.post(f'/admin/controls/{case_id}/restore', follow_redirects=False)
        assert restore_resp.status_code in {302, 303}
        restored_case = db.get_case(case_id)
        assert restored_case is not None and not restored_case.get('deleted_at')

        print('OK - smoke test bestatt')


if __name__ == '__main__':
    main()
