from __future__ import annotations

import json
import zipfile
from pathlib import Path
from typing import Any

from .. import db
from ..config import settings
from ..pdf_export import build_case_packet, build_case_pdf as build_case_pdf_document, build_interview_only_pdf
from .case_service import autofill_case_drafts, case_has_avvik


def build_case_preview_packet(case_row: dict[str, Any], evidence: list[dict[str, Any]]) -> dict[str, Any]:
    try:
        return build_case_packet(case_row, evidence)
    except Exception as exc:
        # Preview must not crash the whole control flow. Return a minimal packet so
        # the user can still go back, edit the case, and retry export.
        title = str(case_row.get('case_number') or 'Kontrollsak')
        return {
            'documents': [
                {'number': '01', 'title': 'Dokumentliste'},
                {'number': '02', 'title': 'Anmeldelse'},
                {'number': '03', 'title': 'Egenrapport'},
                {'number': '04', 'title': 'Avhør / forklaring'},
                {'number': '05', 'title': 'Rapport om ransaking / beslag'},
                {'number': '06', 'title': 'Illustrasjonsrapport'},
            ],
            'primary_document_title': 'Anmeldelse',
            'has_offences': False,
            'title': title,
            'summary': '',
            'short_complaint': 'Forhåndsvisningen kunne ikke bygges automatisk. Kontroller at saken har saksnummer, kontrolltype, posisjon og lagrede kontrollpunkter. Teknisk feil: ' + str(exc),
            'own_report': str(case_row.get('notes') or ''),
            'interview_report': str(case_row.get('hearing_text') or ''),
            'seizure_report': str(case_row.get('seizure_notes') or ''),
            'illustration_texts': ['Ingen illustrasjoner registrert i saken.'],
            'legal_refs': [],
            'findings': [],
            'sources': [],
            'evidence': [],
            'audio_files': [],
            'interview_entries': [],
            'notes': str(case_row.get('notes') or ''),
            'hearing_text': str(case_row.get('hearing_text') or ''),
            'seizure_text': str(case_row.get('seizure_notes') or ''),
            'meta_rows': [
                ('Saksnummer', str(case_row.get('case_number') or '-')),
                ('Etterforsker', str(case_row.get('investigator_name') or '-')),
                ('Kontrollsted', str(case_row.get('location_name') or '-')),
            ],
            'preview_error': str(exc),
        }


def prepare_case_for_export(case_id: int, case_row: dict[str, Any], user: dict[str, Any], *, set_end_time: bool) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    updates = autofill_case_drafts(case_row)
    if set_end_time:
        updates['end_time'] = db.localnow_form()
    if not str(case_row.get('investigator_signature') or '').strip():
        updates['investigator_signature'] = str(case_row.get('investigator_name') or user.get('full_name') or '').strip() or None
    if updates:
        db.save_case(case_id, updates)
    refreshed_case = db.get_case(case_id) or case_row
    evidence = db.list_evidence(case_id)
    return refreshed_case, evidence


def export_case_pdf(case_id: int, case_row: dict[str, Any], user: dict[str, Any]) -> Path:
    prepared_case, evidence = prepare_case_for_export(case_id, case_row, user, set_end_time=True)
    outpath = build_case_pdf_document(prepared_case, evidence, settings.generated_dir)
    has_avvik = case_has_avvik(prepared_case)
    next_status = prepared_case.get('status') or 'Utkast'
    if next_status == 'Utkast':
        next_status = 'Anmeldt' if has_avvik else 'Ingen reaksjon'
    db.save_case(case_id, {'last_generated_pdf': outpath.name, 'status': next_status, 'end_time': prepared_case.get('end_time') or db.localnow_form()})
    return outpath


def export_interview_pdf(case_id: int, case_row: dict[str, Any], user: dict[str, Any]) -> Path:
    prepared_case, evidence = prepare_case_for_export(case_id, case_row, user, set_end_time=False)
    return build_interview_only_pdf(prepared_case, evidence, settings.generated_dir)


def export_case_bundle(case_id: int, case_row: dict[str, Any], user: dict[str, Any]) -> Path:
    prepared_case, evidence = prepare_case_for_export(case_id, case_row, user, set_end_time=True)
    pdf_path = build_case_pdf_document(prepared_case, evidence, settings.generated_dir)
    bundle_name = f"{str(prepared_case['case_number']).replace(' ', '_')}_pakke.zip"
    bundle_path = settings.generated_dir / bundle_name
    packet = build_case_packet(prepared_case, evidence)
    metadata: dict[str, Any] = {
        'case_number': prepared_case.get('case_number'),
        'generated_at': db.utcnow_iso(),
        'packet_title': packet.get('title'),
        'documents': packet.get('documents'),
        'meta_rows': packet.get('meta_rows'),
        'summary': packet.get('summary'),
        'interview_entries': packet.get('interview_entries'),
    }
    with zipfile.ZipFile(bundle_path, 'w', compression=zipfile.ZIP_DEFLATED) as zf:
        zf.write(pdf_path, arcname=f'pdf/{pdf_path.name}')
        zf.writestr('metadata/case.json', json.dumps(metadata, ensure_ascii=False, indent=2))
        for item in evidence:
            filename = str(item.get('filename') or '').strip()
            if not filename:
                continue
            src = settings.upload_dir / filename
            if not src.exists():
                continue
            mime = str(item.get('mime_type') or '')
            prefix = 'audio' if mime.startswith('audio/') else 'bilder'
            zf.write(src, arcname=f'{prefix}/{Path(filename).name}')
    has_avvik = case_has_avvik(prepared_case)
    next_status = prepared_case.get('status') or 'Utkast'
    if next_status in {'Utkast', 'Anmeldt'}:
        next_status = 'Anmeldt og sendt' if has_avvik else 'Ingen reaksjon'
    db.save_case(case_id, {'status': next_status, 'last_generated_pdf': pdf_path.name, 'end_time': prepared_case.get('end_time') or db.localnow_form()})
    return bundle_path
