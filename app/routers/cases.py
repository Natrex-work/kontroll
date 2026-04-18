from __future__ import annotations

from fastapi import APIRouter, File, Form, Request, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, RedirectResponse
from starlette.status import HTTP_303_SEE_OTHER

from .. import catalog, db
from ..dependencies import get_case_for_user, require_control_admin, require_permission
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


@router.get('/cases/new')
def new_case(request: Request):
    user = require_permission(request, 'kv_kontroll', detail='Brukeren har ikke tilgang til KV Kontroll.')
    case_id = db.create_case(created_by=user['id'], investigator_name=user['full_name'], complainant_name=user.get('last_complainant_name'), witness_name=user.get('last_witness_name'))
    db.record_audit(user['id'], 'create_case', 'case', case_id, {})
    return RedirectResponse(f'/cases/{case_id}/edit', status_code=HTTP_303_SEE_OTHER)


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
    return render_template(request, 'case_form.html', case=case_row, evidence=evidence, findings=findings, sources=sources, crew=crew, external_actors=external_actors, interviews=interviews, law_browser=catalog.law_browser_data(), leisure_fields=catalog.LEISURE_FIELDS, commercial_fields=catalog.COMMERCIAL_FIELDS, case_number_error=request.query_params.get('case_number_error'), case_number_saved=request.query_params.get('case_number_saved'))


@router.post('/cases/{case_id}/save')
async def save_case(request: Request, case_id: int):
    user = require_permission(request, 'kv_kontroll', detail='Brukeren har ikke tilgang til KV Kontroll.')
    case_row = get_case_for_user(user, case_id)
    form = await request.form()
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
    data = case_data_from_form(form, user, STATUS_OPTIONS)
    db.save_case(case_id, data)
    db.update_user_last_names(user['id'], data['complainant_name'], data['witness_name'])
    db.record_audit(user['id'], 'autosave_case', 'case', case_id, {'status': data['status']})
    return JSONResponse({'ok': True, 'saved_at': db.utcnow_iso()})


@router.post('/cases/{case_id}/delete')
def delete_case(request: Request, case_id: int):
    admin = require_control_admin(request)
    case_row = db.get_case(case_id)
    if not case_row:
        return RedirectResponse('/admin/controls', status_code=HTTP_303_SEE_OTHER)
    db.soft_delete_case(case_id, admin['id'])
    db.record_audit(admin['id'], 'soft_delete_case', 'case', case_id, {'case_number': case_row['case_number']})
    return RedirectResponse('/admin/controls?deleted=1', status_code=HTTP_303_SEE_OTHER)


@router.post('/cases/{case_id}/evidence')
async def upload_evidence(request: Request, case_id: int, caption: str = Form(default=''), finding_key: str = Form(default=''), law_text: str = Form(default=''), violation_reason: str = Form(default=''), seizure_ref: str = Form(default=''), file: UploadFile = File(...)):
    user = require_permission(request, 'kv_kontroll', detail='Brukeren har ikke tilgang til KV Kontroll.')
    get_case_for_user(user, case_id)
    evidence_id, filename = store_evidence_upload(case_id=case_id, upload_file=file, caption=caption, created_by=user['id'], finding_key=finding_key, law_text=law_text, violation_reason=violation_reason, seizure_ref=seizure_ref)
    db.record_audit(user['id'], 'upload_evidence', 'evidence', evidence_id, {'case_id': case_id, 'filename': filename})
    return RedirectResponse(f'/cases/{case_id}/edit', status_code=HTTP_303_SEE_OTHER)


@router.post('/api/cases/{case_id}/evidence')
async def upload_evidence_api(request: Request, case_id: int, caption: str = Form(default=''), finding_key: str = Form(default=''), law_text: str = Form(default=''), violation_reason: str = Form(default=''), seizure_ref: str = Form(default=''), file: UploadFile = File(...)):
    user = require_permission(request, 'kv_kontroll', detail='Brukeren har ikke tilgang til KV Kontroll.')
    get_case_for_user(user, case_id)
    evidence_id, filename = store_evidence_upload(case_id=case_id, upload_file=file, caption=caption, created_by=user['id'], finding_key=finding_key, law_text=law_text, violation_reason=violation_reason, seizure_ref=seizure_ref)
    row = db.get_evidence_by_id(evidence_id) or {}
    payload = dict(row)
    payload['url'] = f"/uploads/{filename}"
    db.record_audit(user['id'], 'upload_evidence_api', 'evidence', evidence_id, {'case_id': case_id, 'filename': filename})
    return JSONResponse({'ok': True, 'message': 'Bildebevis er lagret i illustrasjonsrapporten.', 'evidence': payload})


@router.post('/evidence/{evidence_id}/delete')
def delete_evidence(request: Request, evidence_id: int):
    user = require_permission(request, 'kv_kontroll', detail='Brukeren har ikke tilgang til KV Kontroll.')
    row = db.get_evidence_by_id(evidence_id)
    if not row:
        return RedirectResponse('/dashboard', status_code=HTTP_303_SEE_OTHER)
    get_case_for_user(user, int(row['case_id']))
    db.delete_evidence(evidence_id)
    delete_evidence_file(row.get('filename'))
    db.record_audit(user['id'], 'delete_evidence', 'evidence', evidence_id, {'case_id': row['case_id']})
    return RedirectResponse(f"/cases/{row['case_id']}/edit", status_code=HTTP_303_SEE_OTHER)


@router.get('/cases/{case_id}/preview', response_class=HTMLResponse)
def preview_case(request: Request, case_id: int):
    user = require_permission(request, 'kv_kontroll', detail='Brukeren har ikke tilgang til KV Kontroll.')
    case_row = get_case_for_user(user, case_id)
    updates = autofill_case_drafts(case_row)
    updates['last_previewed_at'] = db.utcnow_iso()
    if updates:
        db.save_case(case_id, updates)
        case_row = db.get_case(case_id) or case_row
    evidence = db.list_evidence(case_id)
    packet = build_case_preview_packet(case_row, evidence)
    db.record_audit(user['id'], 'preview_case', 'case', case_id, {})
    return render_template(request, 'case_preview.html', case=case_row, evidence=evidence, packet=packet)


@router.post('/cases/{case_id}/preview/save')
async def preview_save_case(request: Request, case_id: int):
    user = require_permission(request, 'kv_kontroll', detail='Brukeren har ikke tilgang til KV Kontroll.')
    get_case_for_user(user, case_id)
    form = await request.form()
    updates = preview_overrides_from_form(form)
    db.save_case(case_id, updates)
    db.record_audit(user['id'], 'save_preview_overrides', 'case', case_id, {})
    return RedirectResponse(f'/cases/{case_id}/preview?saved=1', status_code=HTTP_303_SEE_OTHER)


@router.get('/cases/{case_id}/pdf')
def export_case_pdf_route(request: Request, case_id: int):
    user = require_permission(request, 'kv_kontroll', detail='Brukeren har ikke tilgang til KV Kontroll.')
    case_row = get_case_for_user(user, case_id)
    outpath = export_case_pdf(case_id, case_row, user)
    refreshed_case = db.get_case(case_id) or case_row
    db.record_audit(user['id'], 'export_pdf', 'case', case_id, {'filename': outpath.name, 'has_avvik': case_has_avvik(refreshed_case)})
    return FileResponse(path=str(outpath), media_type='application/pdf', filename=outpath.name)


@router.get('/cases/{case_id}/interview-pdf')
def export_interview_pdf_route(request: Request, case_id: int):
    user = require_permission(request, 'kv_kontroll', detail='Brukeren har ikke tilgang til KV Kontroll.')
    case_row = get_case_for_user(user, case_id)
    outpath = export_interview_pdf(case_id, case_row, user)
    db.record_audit(user['id'], 'export_interview_pdf', 'case', case_id, {'filename': outpath.name})
    return FileResponse(path=str(outpath), media_type='application/pdf', filename=outpath.name)


@router.get('/cases/{case_id}/bundle')
def export_case_bundle_route(request: Request, case_id: int):
    user = require_permission(request, 'kv_kontroll', detail='Brukeren har ikke tilgang til KV Kontroll.')
    case_row = get_case_for_user(user, case_id)
    bundle_path = export_case_bundle(case_id, case_row, user)
    refreshed_case = db.get_case(case_id) or case_row
    db.record_audit(user['id'], 'export_bundle', 'case', case_id, {'filename': bundle_path.name, 'has_avvik': case_has_avvik(refreshed_case)})
    return FileResponse(path=str(bundle_path), media_type='application/zip', filename=bundle_path.name)
