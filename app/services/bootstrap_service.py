from __future__ import annotations

import json
from typing import Any

from .. import db, rules
from ..auth import hash_password
from ..config import settings
from ..logging_setup import get_logger

logger = get_logger(__name__)


def _validate_security_settings() -> None:
    if settings.session_secret == 'dev-session-secret-change-me':
        logger.warning('SESSION_SECRET bruker standard utviklingsverdi. Sett en unik verdi i .env før appen tas i bruk.')
    if not settings.data_encryption_key:
        logger.warning('KV_DATA_ENCRYPTION_KEY er ikke satt. Appen vil avlede krypteringsnøkkel fra SESSION_SECRET. Sett egen nøkkel i produksjon.')
    if settings.production_mode and not settings.session_https_only:
        logger.warning('KV_PRODUCTION_MODE er aktiv, men KV_SESSION_HTTPS_ONLY er ikke slått på. Slå på sikre cookies før produksjonsbruk.')



def initialize_application_data() -> None:
    settings.ensure_runtime_dirs()
    db.init_db()
    bootstrap_admin_if_configured()
    if settings.bootstrap_demo_users:
        seed_default_users()
    if settings.bootstrap_demo_cases:
        seed_demo_cases_if_empty()
    _validate_security_settings()
    if db.count_users() == 0:
        logger.warning('Ingen brukere er opprettet ennå. Kjør manage.py create-admin eller sett KV_BOOTSTRAP_ADMIN_* i miljøet.')



def bootstrap_admin_if_configured() -> None:
    if db.count_users() > 0:
        return
    if not (settings.bootstrap_admin_email and settings.bootstrap_admin_name and settings.bootstrap_admin_password):
        return
    admin_id = db.create_user(
        email=settings.bootstrap_admin_email,
        full_name=settings.bootstrap_admin_name,
        password_hash=hash_password(settings.bootstrap_admin_password),
        role='admin',
        case_prefix='LBHN',
    )
    db.record_audit(admin_id, 'bootstrap_admin', 'user', admin_id, {'email': settings.bootstrap_admin_email})
    logger.info('Opprettet første administrator fra miljøvariabler.')



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
            'attach_demo_image': False,
        },
    ]

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

        case_row = db.get_case(case_id)
        db.record_audit(demo_user['id'], 'seed_case', 'case', case_id, {'title': scenario['title'], 'case_number': case_row['case_number'] if case_row else None})

    logger.info('Seedet demo-saker fordi KV_BOOTSTRAP_DEMO_CASES=1.')
