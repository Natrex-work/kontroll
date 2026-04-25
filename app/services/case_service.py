from __future__ import annotations

import json
import os
import uuid
from pathlib import Path
from typing import Any

from fastapi import HTTPException, UploadFile

from .. import db
from ..config import settings
from ..pdf_export import CASE_BASIS_LABELS, build_text_drafts
from ..validation import sanitize_original_filename, validate_saved_file_size, validate_upload_file, validate_upload_signature

LEGACY_PLACEHOLDER_EVIDENCE_FILENAMES = {'legacy_evidence_case1.png', 'legacy_placeholder_image.png'}


def clean_json_array(raw: str | None) -> str:
    try:
        data = json.loads(raw or '[]')
        if isinstance(data, list):
            return json.dumps(data, ensure_ascii=False)
    except Exception:
        pass
    return '[]'


def clean_float(value: str | None) -> float | None:
    raw = (value or '').strip().replace(',', '.')
    if not raw:
        return None
    try:
        parsed = float(raw)
    except ValueError:
        return None
    if parsed < -180 or parsed > 180:
        return None
    return parsed


def clean_int(value: str | None) -> int | None:
    raw = (value or '').strip().replace(',', '.')
    if not raw:
        return None
    try:
        parsed = int(float(raw))
    except ValueError:
        return None
    return max(0, parsed)


def clean_case_basis(value: str | None) -> str:
    raw = (value or '').strip()
    if raw in CASE_BASIS_LABELS:
        return raw
    return 'patruljeobservasjon'


def case_data_from_form(form: Any, user: dict[str, Any], status_options: list[str]) -> dict[str, Any]:
    data = {
        'investigator_name': str(form.get('investigator_name') or '').strip() or user['full_name'],
        'complainant_name': str(form.get('complainant_name') or '').strip() or None,
        'witness_name': str(form.get('witness_name') or '').strip() or None,
        'case_basis': clean_case_basis(str(form.get('case_basis') or 'patruljeobservasjon')),
        'basis_source_name': str(form.get('basis_source_name') or '').strip() or None,
        'basis_details': str(form.get('basis_details') or '').strip() or None,
        'control_type': str(form.get('control_type') or '').strip() or None,
        'fishery_type': str(form.get('fishery_type') or '').strip() or None,
        'species': str(form.get('species') or '').strip() or None,
        'gear_type': str(form.get('gear_type') or '').strip() or None,
        'start_time': str(form.get('start_time') or '').strip() or None,
        'end_time': str(form.get('end_time') or '').strip() or None,
        'location_name': str(form.get('location_name') or '').strip() or None,
        'latitude': clean_float(str(form.get('latitude') or '')),
        'longitude': clean_float(str(form.get('longitude') or '')),
        'area_status': str(form.get('area_status') or '').strip() or None,
        'area_name': str(form.get('area_name') or '').strip() or None,
        'suspect_name': str(form.get('suspect_name') or '').strip() or None,
        'suspect_phone': str(form.get('suspect_phone') or '').strip() or None,
        'suspect_birthdate': str(form.get('suspect_birthdate') or '').strip() or None,
        'suspect_address': str(form.get('suspect_address') or '').strip() or None,
        'suspect_post_place': str(form.get('suspect_post_place') or '').strip() or None,
        'lookup_text': str(form.get('lookup_text') or '').strip() or None,
        'vessel_name': str(form.get('vessel_name') or '').strip() or None,
        'vessel_reg': str(form.get('vessel_reg') or '').strip() or None,
        'radio_call_sign': str(form.get('radio_call_sign') or '').strip() or None,
        'notes': str(form.get('notes') or '').strip() or None,
        'hearing_text': str(form.get('hearing_text') or '').strip() or None,
        'seizure_notes': str(form.get('seizure_notes') or '').strip() or None,
        'summary': str(form.get('summary') or '').strip() or None,
        'findings_json': clean_json_array(str(form.get('findings_json') or '[]')),
        'source_snapshot_json': clean_json_array(str(form.get('source_snapshot_json') or '[]')),
        'crew_json': clean_json_array(str(form.get('crew_json') or '[]')),
        'external_actors_json': clean_json_array(str(form.get('external_actors_json') or '[]')),
        'persons_json': clean_json_array(str(form.get('persons_json') or '[]')),
        'interview_sessions_json': clean_json_array(str(form.get('interview_sessions_json') or '[]')),
        'interview_not_conducted': 1 if str(form.get('interview_not_conducted') or '').strip().lower() in {'1', 'true', 'on', 'yes'} else 0,
        'interview_not_conducted_reason': str(form.get('interview_not_conducted_reason') or '').strip() or None,
        'interview_guidance_text': str(form.get('interview_guidance_text') or '').strip() or None,
        'hummer_participant_no': str(form.get('hummer_participant_no') or '').strip() or None,
        'hummer_last_registered': str(form.get('hummer_last_registered') or '').strip() or None,
        'observed_gear_count': clean_int(str(form.get('observed_gear_count') or '')),
        'complaint_override': str(form.get('complaint_override') or '').strip() or None,
        'own_report_override': str(form.get('own_report_override') or '').strip() or None,
        'interview_report_override': str(form.get('interview_report_override') or '').strip() or None,
        'seizure_report_override': str(form.get('seizure_report_override') or '').strip() or None,
        'complainant_signature': str(form.get('complainant_signature') or '').strip() or None,
        'witness_signature': str(form.get('witness_signature') or '').strip() or None,
        'investigator_signature': str(form.get('investigator_signature') or '').strip() or None,
        'suspect_signature': str(form.get('suspect_signature') or '').strip() or None,
        'status': str(form.get('status') or 'Utkast').strip() or 'Utkast',
    }
    if data['status'] not in status_options:
        data['status'] = 'Utkast'
    if data['species'] and not data['fishery_type']:
        data['fishery_type'] = data['species']
    lat = data.get('latitude')
    lng = data.get('longitude')
    if lat is not None and (lat < -90 or lat > 90):
        data['latitude'] = None
    if lng is not None and (lng < -180 or lng > 180):
        data['longitude'] = None
    return data


def preview_overrides_from_form(form: Any) -> dict[str, Any]:
    return {
        'complaint_override': str(form.get('complaint_override') or '').strip() or None,
        'own_report_override': str(form.get('own_report_override') or '').strip() or None,
        'interview_report_override': str(form.get('interview_report_override') or '').strip() or None,
        'interview_not_conducted': 1 if str(form.get('interview_not_conducted') or '').strip().lower() in {'1', 'true', 'on', 'yes'} else 0,
        'interview_not_conducted_reason': str(form.get('interview_not_conducted_reason') or '').strip() or None,
        'interview_guidance_text': str(form.get('interview_guidance_text') or '').strip() or None,
        'seizure_report_override': str(form.get('seizure_report_override') or '').strip() or None,
        'complainant_signature': str(form.get('complainant_signature') or '').strip() or None,
        'witness_signature': str(form.get('witness_signature') or '').strip() or None,
        'investigator_signature': str(form.get('investigator_signature') or '').strip() or None,
        'suspect_signature': str(form.get('suspect_signature') or '').strip() or None,
        'last_previewed_at': db.utcnow_iso(),
    }


def autofill_case_drafts(case_row: dict[str, Any]) -> dict[str, Any]:
    findings = db.case_to_findings(case_row)
    drafts = build_text_drafts(case_row, findings)
    updates: dict[str, Any] = {}
    for field in ('basis_details', 'notes', 'summary'):
        if not str(case_row.get(field) or '').strip() and str(drafts.get(field) or '').strip():
            updates[field] = str(drafts[field]).strip()
    return updates


def case_has_avvik(case_row: dict[str, Any]) -> bool:
    findings = db.case_to_findings(case_row)
    return any(str((item or {}).get('status') or '').strip().lower() == 'avvik' for item in findings if isinstance(item, dict))


def delete_case_files(evidence_rows: list[dict[str, Any]]) -> None:
    for item in evidence_rows:
        filename = str(item.get('filename') or '')
        if not filename or filename in LEGACY_PLACEHOLDER_EVIDENCE_FILENAMES:
            continue
        path = settings.upload_dir / filename
        if path.exists():
            path.unlink(missing_ok=True)


def _stream_upload_to_path(upload_file: UploadFile, dest: Path, original_filename: str) -> tuple[int, str]:
    max_bytes = settings.max_upload_size_mb * 1024 * 1024
    first_chunk = upload_file.file.read(64 * 1024)
    if not first_chunk:
        raise HTTPException(status_code=400, detail='Filen er tom.')
    normalized_mime = validate_upload_signature(original_filename, first_chunk)
    total = len(first_chunk)
    if total > max_bytes:
        raise HTTPException(status_code=400, detail=f'Filen er for stor. Maks tillatt størrelse er {settings.max_upload_size_mb} MB.')
    try:
        with dest.open('wb') as buffer:
            buffer.write(first_chunk)
            while True:
                chunk = upload_file.file.read(1024 * 1024)
                if not chunk:
                    break
                total += len(chunk)
                if total > max_bytes:
                    raise HTTPException(status_code=400, detail=f'Filen er for stor. Maks tillatt størrelse er {settings.max_upload_size_mb} MB.')
                buffer.write(chunk)
        os.chmod(dest, 0o600)
        validate_saved_file_size(total)
        return total, normalized_mime
    except Exception:
        dest.unlink(missing_ok=True)
        raise
    finally:
        try:
            upload_file.file.close()
        except Exception:
            pass


def store_evidence_upload(*, case_id: int, upload_file: UploadFile, caption: str, created_by: int, finding_key: str = '', law_text: str = '', violation_reason: str = '', seizure_ref: str = '') -> tuple[int, str]:
    original_filename = validate_upload_file(upload_file)
    original_filename = sanitize_original_filename(original_filename)
    suffix = Path(original_filename).suffix.lower() or '.bin'
    unique_name = f'{uuid.uuid4().hex}{suffix}'
    dest = settings.upload_dir / unique_name
    _, mime_type = _stream_upload_to_path(upload_file, dest, original_filename)
    evidence_id = db.add_evidence(case_id, unique_name, original_filename, caption or None, mime_type, created_by, finding_key or None, law_text or None, violation_reason or None, seizure_ref or None)
    return evidence_id, unique_name


def delete_evidence_file(filename: str | None) -> None:
    clean_name = str(filename or '').strip()
    if not clean_name or clean_name in LEGACY_PLACEHOLDER_EVIDENCE_FILENAMES:
        return
    path = settings.upload_dir / clean_name
    if path.exists():
        path.unlink(missing_ok=True)


def merge_source_rows(*source_lists: list[dict[str, Any]] | None) -> list[dict[str, Any]]:
    seen: set[tuple[str, str, str]] = set()
    out: list[dict[str, Any]] = []
    for source_list in source_lists:
        for item in source_list or []:
            key = (str(item.get('name') or '').strip(), str(item.get('ref') or '').strip(), str(item.get('url') or '').strip())
            if key in seen or not key[1]:
                continue
            seen.add(key)
            out.append(dict(item))
    return out
