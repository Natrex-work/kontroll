from __future__ import annotations

import json
from typing import Any

from .. import db, rules
from ..auth import hash_password
from ..config import settings
from ..logging_setup import get_logger

logger = get_logger(__name__)


def initialize_application_data() -> None:
    settings.ensure_runtime_dirs()
    db.init_db()
    seed_default_users()
    seed_demo_cases_if_empty()
    if settings.session_secret == 'dev-session-secret-change-me':
        logger.warning('SESSION_SECRET bruker standard utviklingsverdi. Sett en unik verdi i .env for produksjonsbruk.')


def seed_default_users() -> None:
    if db.get_user_by_email('admin@kv.demo') is None:
        admin_id = db.create_user(
            email='admin@kv.demo',
            full_name='KV Demo Admin',
            password_hash=hash_password('Admin123!'),
            role='admin',
            last_complainant_name='KV Demo Anmelder',
            last_witness_name='KV Demo Vitne',
            case_prefix='LBHN',
        )
        db.record_audit(admin_id, 'seed_user', 'user', admin_id, {'email': 'admin@kv.demo'})
    if db.get_user_by_email('kontrollor@kv.demo') is None:
        user_id = db.create_user(
            email='kontrollor@kv.demo',
            full_name='KV Demo Kontrollor',
            password_hash=hash_password('Demo123!'),
            role='investigator',
            last_complainant_name='KV Demo Anmelder',
            last_witness_name='KV Demo Vitne',
            case_prefix='LBHN',
        )
        db.record_audit(user_id, 'seed_user', 'user', user_id, {'email': 'kontrollor@kv.demo'})


def _bundle_findings(
    control_type: str,
    species: str,
    gear_type: str,
    overrides: dict[str, dict[str, str]] | None = None,
    area_status: str | None = None,
    control_date: str = '',
    area_name: str = '',
    area_notes: str = '',
    lat: float | None = None,
    lng: float | None = None,
) -> tuple[list[dict[str, str]], list[dict[str, str]]]:
    bundle = rules.get_rule_bundle(control_type, species, gear_type, area_status=area_status, control_date=control_date, area_name=area_name, area_notes=area_notes, lat=lat, lng=lng)
    findings: list[dict[str, str]] = []
    overrides = overrides or {}
    for item in bundle.get('items') or []:
        clone = dict(item)
        clone.update(overrides.get(clone.get('key') or '', {}))
        clone['status'] = clone.get('status') or 'godkjent'
        clone['notes'] = clone.get('notes') or ''
        findings.append(clone)
    return findings, list(bundle.get('sources') or [])


def seed_demo_cases_if_empty() -> None:
    if db.has_any_cases():
        return

    demo_user = db.get_user_by_email('kontrollor@kv.demo')
    if not demo_user:
        return

    scenarios: list[dict[str, Any]] = [
        {
            'title': 'Patrulje - hummerkontroll i fredningsområde',
            'case_basis': 'patruljeobservasjon',
            'basis_source_name': 'KV NORNEN patrulje',
            'basis_details': 'Planlagt patrulje med hummeroppsyn og kontroll av teiner i området ved Tofte.',
            'control_type': 'Fritidsfiske',
            'fishery_type': 'Hummer',
            'species': 'Hummer',
            'gear_type': 'Teine',
            'start_time': '2026-03-18T15:00',
            'end_time': '2026-03-18T15:45',
            'location_name': 'Tofte demo',
            'latitude': 59.535400,
            'longitude': 10.536600,
            'area_status': 'fredningsområde',
            'area_name': 'Fredningsområde demo - Tofte hummer',
            'suspect_name': 'Ola Havfisker',
            'suspect_phone': '91500001',
            'suspect_birthdate': '12.04.1976',
            'suspect_address': 'Bryggeveien 12, 3480 Demo',
            'vessel_name': 'MS Demofjord',
            'vessel_reg': 'LF-100-D',
            'notes': 'Patruljen ble gjennomført med lettbåt. Det ble kontrollert merking av teine, fluktåpning, råtnetråd og fangst. Tre hummer ble kontrollmålt til under minstemål og dokumentert med foto.',
            'hearing_text': 'Avhørte forklarer at hummeren ble målt i båt under variabelt vær. Han opplyser at han kjenner til minstemålet, men trodde hummeren var innenfor.',
            'seizure_notes': 'Tre hummer under minstemål ble dokumentert og gjenutsatt i demo-fredningsområde.',
            'summary': '',
            'status': 'Anmeldt',
            'finding_overrides': {
                'minstemal': {'status': 'avvik', 'notes': 'Tre hummer kontrollmålt til under minstemål ved kontroll på stedet.'},
                'omradekontroll': {'status': 'avvik', 'notes': 'Kontrollpunktet og oppbevaring ble registrert i demo-fredningsområde.'},
            },
            'attach_demo_image': True,
        },
        {
            'title': 'Tips - fritidsfiske med garn i stengt område',
            'case_basis': 'tips',
            'basis_source_name': 'Anonym tipstelefon',
            'basis_details': 'Det ble opplyst om mulig ulovlig garnsetting i et område som i demoen er merket som stengt.',
            'control_type': 'Fritidsfiske',
            'fishery_type': 'Torsk',
            'species': 'Torsk',
            'gear_type': 'Garn',
            'start_time': '2026-03-19T08:20',
            'end_time': '2026-03-19T09:05',
            'location_name': 'Drøbak demo',
            'latitude': 59.656000,
            'longitude': 10.628000,
            'area_status': 'stengt område',
            'area_name': 'Stengt område demo - Drøbak',
            'suspect_name': 'Per Garnsen',
            'suspect_phone': '91500003',
            'suspect_birthdate': '22.11.1968',
            'suspect_address': 'Sjøgata 7, 8001 Demo',
            'vessel_name': 'MS Nordhavet',
            'vessel_reg': 'T-88-P',
            'notes': 'Kontrollen ble iverksatt etter tips. Garnlenke ble funnet i demo-stengt område. Merking og områdekontroll ble dokumentert med foto og posisjon.',
            'hearing_text': 'Avhørte opplyser at han ikke kjente til stengingen og at garnene var satt kvelden før.',
            'seizure_notes': 'To bilder av garnsetting og posisjon ble sikret i saken. Ingen fysisk beslag i demoen.',
            'summary': '',
            'status': 'Anmeldt',
            'finding_overrides': {
                'omrade_generisk': {'status': 'avvik', 'notes': 'GPS-posisjon viste at garnene stod i demo-stengt område.'},
                'fangst': {'status': 'avvik', 'notes': 'Kontroll av fangst og oppbevaring ga grunnlag for videre vurdering.'},
            },
            'attach_demo_image': False,
        },
        {
            'title': 'Anmeldelse - kommersiell garnkontroll',
            'case_basis': 'anmeldelse',
            'basis_source_name': 'Innmeldt sak fra ekstern aktør',
            'basis_details': 'Saken ble registrert etter melding om mulig mangelfull merking og dokumentasjon ved kommersielt garnfiske.',
            'control_type': 'Kommersiell',
            'fishery_type': 'Torsk',
            'species': 'Torsk',
            'gear_type': 'Garn',
            'start_time': '2026-03-20T11:15',
            'end_time': '2026-03-20T12:05',
            'location_name': 'Nordhavet demo',
            'latitude': 68.000100,
            'longitude': 15.120100,
            'area_status': 'normalt område',
            'area_name': 'Ingen kjent demo-sone',
            'suspect_name': 'Kari Kyst',
            'suspect_phone': '91500002',
            'suspect_birthdate': '02.09.1981',
            'suspect_address': 'Naustvika 3, 8400 Demo',
            'vessel_name': 'KV Teine',
            'vessel_reg': 'NF-204-K',
            'notes': 'Kontrollen ble gjennomført etter registrert anmeldelse. Det ble kontrollert fartøyopplysninger, merking og dokumentasjon om bord.',
            'hearing_text': 'Avhørte forklarer at dokumentasjonen lå i annen mappe om bord og at merkingen skulle oppdateres før neste tur.',
            'seizure_notes': 'Dokumentasjon og merking ble fotografert i demoen.',
            'summary': '',
            'status': 'Anmeldt',
            'finding_overrides': {
                'redskap_merket': {'status': 'avvik', 'notes': 'Merkingen på garnsettet var mangelfull ved kontrolltidspunktet.'},
                'dokumentasjon': {'status': 'avvik', 'notes': 'Påkrevd dokumentasjon var ikke umiddelbart tilgjengelig for kontrollør.'},
            },
            'attach_demo_image': False,
        },
    ]

    demo_image = settings.upload_dir / 'demo_evidence_case1.png'
    extra_image = settings.upload_dir / '4e6749af8fc3498e879dbc692632e6a8.png'

    for scenario in scenarios:
        case_id = db.create_case(
            created_by=demo_user['id'],
            investigator_name=demo_user['full_name'],
            complainant_name=demo_user.get('last_complainant_name'),
            witness_name=demo_user.get('last_witness_name'),
        )
        findings, sources = _bundle_findings(str(scenario['control_type']), str(scenario['species']), str(scenario['gear_type']), scenario.get('finding_overrides') or {}, str(scenario.get('area_status') or ''), area_name=str(scenario.get('area_name') or ''), area_notes=str(scenario.get('notes') or ''))
        payload = {k: v for k, v in scenario.items() if k not in {'title', 'finding_overrides', 'attach_demo_image'}}
        payload['investigator_name'] = demo_user['full_name']
        payload['complainant_name'] = demo_user.get('last_complainant_name') or 'KV Demo Anmelder'
        payload['witness_name'] = demo_user.get('last_witness_name') or 'KV Demo Vitne'
        payload['findings_json'] = json.dumps(findings, ensure_ascii=False)
        payload['source_snapshot_json'] = json.dumps(sources, ensure_ascii=False)
        db.save_case(case_id, payload)

        if scenario.get('attach_demo_image') and demo_image.exists():
            db.add_evidence(case_id, demo_image.name, demo_image.name, 'Demo-bevis fra kontrollsted', 'image/png', demo_user['id'])
        elif extra_image.exists():
            db.add_evidence(case_id, extra_image.name, extra_image.name, 'Demo-bilde fra kontroll', 'image/png', demo_user['id'])

        case_row = db.get_case(case_id)
        db.record_audit(demo_user['id'], 'seed_case', 'case', case_id, {'title': scenario['title'], 'case_number': case_row['case_number'] if case_row else None})

    logger.info('Seedet demo-brukere og demo-saker for v25-oppsett.')
