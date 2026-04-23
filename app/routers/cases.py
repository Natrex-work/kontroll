from __future__ import annotations

import mimetypes
from pathlib import Path
from urllib.parse import quote

from fastapi import APIRouter, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, RedirectResponse
from starlette.status import HTTP_303_SEE_OTHER

from .. import catalog, db, live_sources
from ..config import settings
from ..dependencies import get_case_for_user, require_control_admin, require_permission
from ..security import enforce_csrf
from ..services.case_service import autofill_case_drafts, case_data_from_form, case_has_avvik, delete_evidence_file, preview_overrides_from_form, store_evidence_upload
from ..services.pdf_service import build_case_preview_packet, export_case_bundle, export_case_pdf, export_interview_pdf
from ..ui import STATUS_OPTIONS, render_template

router = APIRouter()


def _build_case_number_from_suffix(existing_case_number: str, suffix_value: str | None) -> str | None:
    raw_suffix = str(suffix_value or '').strip()
    if not raw_suffix:
        return None
    try:
        suffix_int = int(raw_suffix)
    except ValueError:
        return None
    if suffix_int < 1 or suffix_int > 999:
        return None
    match = __import__('re').match(r'^(.*?\s\d{2}\s)(\d{3})$', str(existing_case_number or '').strip())
    if not match:
        return None
    return f"{match.group(1)}{suffix_int:03d}"


def _inline_file_headers(filename: str) -> dict[str, str]:
    safe_name = Path(str(filename or 'fil')).name
    return {'Content-Disposition': "inline; filename*=UTF-8''" + quote(safe_name), 'Cache-Control': 'no-store'}



def _offline_case_shell(user: dict[str, object], local_id: str = '') -> dict[str, object]:
    local_now = db.localnow_form()
    year_short = local_now[:4][2:4] if len(local_now) >= 4 else '00'
    prefix = settings.bootstrap_admin_case_prefix or 'LBHN'
    return {
        'id': str(local_id or ''),
        'case_number': f'{prefix} {year_short} xxx',
        'investigator_name': str(user.get('full_name') or ''),
        'complainant_name': str(user.get('last_complainant_name') or ''),
        'witness_name': str(user.get('last_witness_name') or ''),
        'case_basis': 'patruljeobservasjon',
        'basis_source_name': 'Kystvakten lettbåt',
        'basis_details': 'Det ble fra Kystvakten lettbåt gjennomført kontroll med fokus på faststående fiskeredskap. Kontrollgrunnlaget bygger på egen observasjon og planlagt kontrollvirksomhet.',
        'control_type': '',
        'fishery_type': '',
        'species': '',
        'gear_type': '',
        'start_time': local_now,
        'end_time': '',
        'location_name': '',
        'latitude': None,
        'longitude': None,
        'area_status': '',
        'area_name': '',
        'suspect_name': '',
        'suspect_phone': '',
        'suspect_birthdate': '',
        'suspect_address': '',
        'suspect_post_place': '',
        'lookup_text': '',
        'vessel_name': '',
        'vessel_reg': '',
        'radio_call_sign': '',
        'notes': '',
        'hearing_text': '',
        'seizure_notes': '',
        'summary': '',
        'findings_json': '[]',
        'source_snapshot_json': '[]',
        'crew_json': '[]',
        'external_actors_json': '[]',
        'interview_sessions_json': '[]',
        'hummer_participant_no': '',
        'hummer_last_registered': '',
        'observed_gear_count': 0,
        'complaint_override': '',
        'own_report_override': '',
        'interview_report_override': '',
        'seizure_report_override': '',
        'complainant_signature': '',
        'witness_signature': '',
        'investigator_signature': str(user.get('full_name') or ''),
        'suspect_signature': '',
        'status': 'Utkast',
        'updated_at': '',
    }


@router.get('/cases/new')
def new_case_get(request: Request):
    require_permission(request, 'kv_kontroll', detail='Brukeren har ikke tilgang til KV Kontroll.')
    return RedirectResponse('/dashboard', status_code=HTTP_303_SEE_OTHER)


@router.post('/cases/new')
async def new_case(request: Request):
    user = require_permission(request, 'kv_kontroll', detail='Brukeren har ikke tilgang til KV Kontroll.')
    form = await request.form()
    enforce_csrf(request, form)
    case_id = db.create_case(created_by=user['id'], investigator_name=user['full_name'], complainant_name=user.get('last_complainant_name'), witness_name=user.get('last_witness_name'))
    db.record_audit(user['id'], 'create_case', 'case', case_id, {})
    return RedirectResponse(f'/cases/{case_id}/edit', status_code=HTTP_303_SEE_OTHER)




@router.get('/cases/offline/new', response_class=HTMLResponse)
def offline_new_case(request: Request, local_id: str = ''):
    user = require_permission(request, 'kv_kontroll', detail='Brukeren har ikke tilgang til KV Kontroll.')
    shell = _offline_case_shell(user, local_id)
    return render_template(
        request,
        'case_form.html',
        case=shell,
        evidence=[],
        findings=[],
        sources=[],
        crew=[],
        external_actors=[],
        interviews=[],
        law_browser=catalog.law_browser_data(),
        leisure_fields=catalog.LEISURE_FIELDS,
        commercial_fields=catalog.COMMERCIAL_FIELDS,
        portal_layers=live_sources.portal_layer_catalog(),
        case_number_error=None,
        case_number_saved=None,
        offline_new=True,
        offline_local_id=str(local_id or ''),
    )


@router.post('/api/cases/create-from-draft')
async def create_case_from_draft(request: Request):
    user = require_permission(request, 'kv_kontroll', detail='Brukeren har ikke tilgang til KV Kontroll.')
    form = await request.form()
    enforce_csrf(request, form)
    local_case_id = str(form.get('local_case_id') or '').strip()
    case_id = db.create_case(
        created_by=user['id'],
        investigator_name=user['full_name'],
        complainant_name=user.get('last_complainant_name'),
        witness_name=user.get('last_witness_name'),
    )
    case_row = db.get_case(case_id) or {}
    data = case_data_from_form(form, user, STATUS_OPTIONS)
    updated_case_number = _build_case_number_from_suffix(str(case_row.get('case_number') or ''), form.get('case_number_suffix'))
    if updated_case_number and updated_case_number != str(case_row.get('case_number') or ''):
        if db.case_number_exists(updated_case_number, exclude_case_id=case_id):
            return JSONResponse({'ok': False, 'error': 'duplicate_case_number'}, status_code=409)
        data['case_number'] = updated_case_number
    db.save_case(case_id, data)
    db.update_user_last_names(user['id'], data['complainant_name'], data['witness_name'])
    saved = db.get_case(case_id) or case_row
    db.record_audit(user['id'], 'create_case_from_draft', 'case', case_id, {'local_case_id': local_case_id, 'status': data['status'], 'case_number': saved.get('case_number')})
    return JSONResponse({
        'ok': True,
        'case_id': int(case_id),
        'case_number': str(saved.get('case_number') or ''),
        'case_url': f'/cases/{case_id}/edit',
        'saved_at': db.utcnow_iso(),
    })

@router.get('/cases/{case_id}/edit', response_class=HTMLResponse)
def edit_case(request: Request, case_id: int):
    user = require_permission(request, 'kv_kontroll', detail='Brukeren har ikke tilgang til KV Kontroll.')
    case_row = get_case_for_user(user, case_id)
    evidence = db.list_evidence(case_id)
    findings = db.case_to_findings(case_row)
    sources = db.case_to_sources(case_row)
    crew = db.case_to_crew(case_row)
    external_actors = db.case_to_external_actors(case_row)
    interviews = db.case_to_interviews(case_row)
    return render_template(request, 'case_form.html', case=case_row, evidence=evidence, findings=findings, sources=sources, crew=crew, external_actors=external_actors, interviews=interviews, law_browser=catalog.law_browser_data(), leisure_fields=catalog.LEISURE_FIELDS, commercial_fields=catalog.COMMERCIAL_FIELDS, portal_layers=live_sources.portal_layer_catalog(), case_number_error=request.query_params.get('case_number_error'), case_number_saved=request.query_params.get('case_number_saved'))


@router.post('/cases/{case_id}/save')
async def save_case(request: Request, case_id: int):
    user = require_permission(request, 'kv_kontroll', detail='Brukeren har ikke tilgang til KV Kontroll.')
    case_row = get_case_for_user(user, case_id)
    form = await request.form()
    enforce_csrf(request, form)
    data = case_data_from_form(form, user, STATUS_OPTIONS)
    updated_case_number = _build_case_number_from_suffix(str(case_row.get('case_number') or ''), form.get('case_number_suffix'))
    redirect_suffix = '?saved=1'
    if updated_case_number and updated_case_number != str(case_row.get('case_number') or ''):
        if db.case_number_exists(updated_case_number, exclude_case_id=case_id):
            return RedirectResponse(f'/cases/{case_id}/edit?case_number_error=duplicate', status_code=HTTP_303_SEE_OTHER)
        data['case_number'] = updated_case_number
        redirect_suffix = '?saved=1&case_number_saved=1'
    db.save_case(case_id, data)
    db.update_user_last_names(user['id'], data['complainant_name'], data['witness_name'])
    db.record_audit(user['id'], 'save_case', 'case', case_id, {'status': data['status'], 'case_number': data.get('case_number') or case_row.get('case_number')})
    return RedirectResponse(f'/cases/{case_id}/edit{redirect_suffix}', status_code=HTTP_303_SEE_OTHER)


@router.post('/api/cases/{case_id}/autosave')
async def autosave_case(request: Request, case_id: int):
    user = require_permission(request, 'kv_kontroll', detail='Brukeren har ikke tilgang til KV Kontroll.')
    get_case_for_user(user, case_id)
    form = await request.form()
    enforce_csrf(request, form)
    data = case_data_from_form(form, user, STATUS_OPTIONS)
    db.save_case(case_id, data)
    db.update_user_last_names(user['id'], data['complainant_name'], data['witness_name'])
    db.record_audit(user['id'], 'autosave_case', 'case', case_id, {'status': data['status']})
    return JSONResponse({'ok': True, 'saved_at': db.utcnow_iso()})


@router.post('/cases/{case_id}/delete')
async def delete_case(request: Request, case_id: int):
    admin = require_control_admin(request)
    form = await request.form()
    enforce_csrf(request, form)
    case_row = db.get_case(case_id)
    if not case_row:
        return RedirectResponse('/admin/controls', status_code=HTTP_303_SEE_OTHER)
    db.soft_delete_case(case_id, admin['id'])
    db.record_audit(admin['id'], 'soft_delete_case', 'case', case_id, {'case_number': case_row['case_number']})
    return RedirectResponse('/admin/controls?deleted=1', status_code=HTTP_303_SEE_OTHER)


@router.post('/cases/{case_id}/evidence')
async def upload_evidence(request: Request, case_id: int, caption: str = Form(default=''), finding_key: str = Form(default=''), law_text: str = Form(default=''), violation_reason: str = Form(default=''), seizure_ref: str = Form(default=''), file: UploadFile = File(...)):
    user = require_permission(request, 'kv_kontroll', detail='Brukeren har ikke tilgang til KV Kontroll.')
    form = await request.form()
    enforce_csrf(request, form)
    get_case_for_user(user, case_id)
    evidence_id, filename = store_evidence_upload(case_id=case_id, upload_file=file, caption=caption, created_by=user['id'], finding_key=finding_key, law_text=law_text, violation_reason=violation_reason, seizure_ref=seizure_ref)
    db.record_audit(user['id'], 'upload_evidence', 'evidence', evidence_id, {'case_id': case_id, 'filename': filename})
    return RedirectResponse(f'/cases/{case_id}/edit', status_code=HTTP_303_SEE_OTHER)


@router.post('/api/cases/{case_id}/evidence')
async def upload_evidence_api(request: Request, case_id: int, caption: str = Form(default=''), finding_key: str = Form(default=''), law_text: str = Form(default=''), violation_reason: str = Form(default=''), seizure_ref: str = Form(default=''), file: UploadFile = File(...)):
    user = require_permission(request, 'kv_kontroll', detail='Brukeren har ikke tilgang til KV Kontroll.')
    form = await request.form()
    enforce_csrf(request, form)
    get_case_for_user(user, case_id)
    evidence_id, filename = store_evidence_upload(case_id=case_id, upload_file=file, caption=caption, created_by=user['id'], finding_key=finding_key, law_text=law_text, violation_reason=violation_reason, seizure_ref=seizure_ref)
    row = db.get_evidence_by_id(evidence_id) or {}
    payload = dict(row)
    payload['url'] = f"/cases/{case_id}/evidence/{evidence_id}/file"
    db.record_audit(user['id'], 'upload_evidence_api', 'evidence', evidence_id, {'case_id': case_id, 'filename': filename})
    return JSONResponse({'ok': True, 'message': 'Bildebevis er lagret i illustrasjonsrapporten.', 'evidence': payload})


@router.post('/evidence/{evidence_id}/delete')
async def delete_evidence(request: Request, evidence_id: int):
    user = require_permission(request, 'kv_kontroll', detail='Brukeren har ikke tilgang til KV Kontroll.')
    form = await request.form()
    enforce_csrf(request, form)
    row = db.get_evidence_by_id(evidence_id)
    if not row:
        return RedirectResponse('/dashboard', status_code=HTTP_303_SEE_OTHER)
    get_case_for_user(user, int(row['case_id']))
    db.delete_evidence(evidence_id)
    delete_evidence_file(row.get('filename'))
    db.record_audit(user['id'], 'delete_evidence', 'evidence', evidence_id, {'case_id': row['case_id']})
    return RedirectResponse(f"/cases/{row['case_id']}/edit", status_code=HTTP_303_SEE_OTHER)


@router.get('/cases/{case_id}/evidence/{evidence_id}/file')
def evidence_file(request: Request, case_id: int, evidence_id: int):
    user = require_permission(request, 'kv_kontroll', detail='Brukeren har ikke tilgang til KV Kontroll.')
    get_case_for_user(user, case_id)
    row = db.get_evidence_by_id(evidence_id)
    if not row or int(row.get('case_id') or 0) != int(case_id):
        raise HTTPException(status_code=404, detail='Fant ikke vedlegget.')
    filename = Path(str(row.get('filename') or '')).name
    path = settings.upload_dir / filename
    if not path.exists():
        raise HTTPException(status_code=404, detail='Fant ikke filen.')
    media_type = str(row.get('mime_type') or '') or mimetypes.guess_type(filename)[0] or 'application/octet-stream'
    headers = _inline_file_headers(str(row.get('original_filename') or filename))
    return FileResponse(path=str(path), media_type=media_type, headers=headers)


@router.get('/cases/{case_id}/generated/{filename}')
def generated_file(request: Request, case_id: int, filename: str):
    user = require_permission(request, 'kv_kontroll', detail='Brukeren har ikke tilgang til KV Kontroll.')
    case_row = get_case_for_user(user, case_id)
    safe_name = Path(filename).name
    if safe_name != filename:
        raise HTTPException(status_code=404, detail='Fant ikke filen.')
    case_prefix = str(case_row.get('case_number') or '').replace(' ', '_')
    if case_prefix and not safe_name.startswith(case_prefix):
        raise HTTPException(status_code=403, detail='Ingen tilgang til filen.')
    path = settings.generated_dir / safe_name
    if not path.exists():
        raise HTTPException(status_code=404, detail='Fant ikke filen.')
    media_type = mimetypes.guess_type(safe_name)[0] or 'application/octet-stream'
    headers = _inline_file_headers(safe_name)
    return FileResponse(path=str(path), media_type=media_type, headers=headers)


@router.get('/cases/{case_id}/preview', response_class=HTMLResponse)
def preview_case(request: Request, case_id: int):
    user = require_permission(request, 'kv_kontroll', detail='Brukeren har ikke tilgang til KV Kontroll.')
    case_row = get_case_for_user(user, case_id)
    evidence = db.list_evidence(case_id)
    preview_case_row = dict(case_row)
    preview_case_row.update(autofill_case_drafts(case_row))
    packet = build_case_preview_packet(preview_case_row, evidence)
    return render_template(request, 'case_preview.html', case=preview_case_row, evidence=evidence, packet=packet)


@router.post('/cases/{case_id}/preview/save')
async def preview_save_case(request: Request, case_id: int):
    user = require_permission(request, 'kv_kontroll', detail='Brukeren har ikke tilgang til KV Kontroll.')
    get_case_for_user(user, case_id)
    form = await request.form()
    enforce_csrf(request, form)
    updates = preview_overrides_from_form(form)
    db.save_case(case_id, updates)
    db.record_audit(user['id'], 'save_preview_overrides', 'case', case_id, {})
    return RedirectResponse(f'/cases/{case_id}/preview?saved=1', status_code=HTTP_303_SEE_OTHER)


@router.post('/cases/{case_id}/pdf')
async def export_case_pdf_route(request: Request, case_id: int):
    user = require_permission(request, 'kv_kontroll', detail='Brukeren har ikke tilgang til KV Kontroll.')
    form = await request.form()
    enforce_csrf(request, form)
    case_row = get_case_for_user(user, case_id)
    outpath = export_case_pdf(case_id, case_row, user)
    refreshed_case = db.get_case(case_id) or case_row
    db.record_audit(user['id'], 'export_pdf', 'case', case_id, {'filename': outpath.name, 'has_avvik': case_has_avvik(refreshed_case)})
    return FileResponse(path=str(outpath), media_type='application/pdf', filename=outpath.name, headers={'Cache-Control': 'no-store'})


@router.post('/cases/{case_id}/interview-pdf')
async def export_interview_pdf_route(request: Request, case_id: int):
    user = require_permission(request, 'kv_kontroll', detail='Brukeren har ikke tilgang til KV Kontroll.')
    form = await request.form()
    enforce_csrf(request, form)
    case_row = get_case_for_user(user, case_id)
    outpath = export_interview_pdf(case_id, case_row, user)
    db.record_audit(user['id'], 'export_interview_pdf', 'case', case_id, {'filename': outpath.name})
    return FileResponse(path=str(outpath), media_type='application/pdf', filename=outpath.name, headers={'Cache-Control': 'no-store'})


@router.post('/cases/{case_id}/bundle')
async def export_case_bundle_route(request: Request, case_id: int):
    user = require_permission(request, 'kv_kontroll', detail='Brukeren har ikke tilgang til KV Kontroll.')
    form = await request.form()
    enforce_csrf(request, form)
    case_row = get_case_for_user(user, case_id)
    bundle_path = export_case_bundle(case_id, case_row, user)
    refreshed_case = db.get_case(case_id) or case_row
    db.record_audit(user['id'], 'export_bundle', 'case', case_id, {'filename': bundle_path.name, 'has_avvik': case_has_avvik(refreshed_case)})
    return FileResponse(path=str(bundle_path), media_type='application/zip', filename=bundle_path.name, headers={'Cache-Control': 'no-store'})
