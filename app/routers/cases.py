from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, File, Form, Request, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, RedirectResponse
from starlette.background import BackgroundTask
from starlette.status import HTTP_303_SEE_OTHER

from .. import catalog, db
from ..dependencies import get_case_for_user, require_control_admin, require_permission
from ..services.case_service import autofill_case_drafts, case_data_from_form, case_has_avvik, delete_evidence_file, preview_overrides_from_form, store_evidence_upload
from ..services.pdf_service import build_case_preview_packet, export_case_bundle, export_case_pdf, export_interview_pdf
from ..ui import STATUS_OPTIONS, render_template
from ..security import verify_csrf

router = APIRouter()


def _evidence_url(evidence_row: dict) -> str:
    return f"/evidence/{int(evidence_row['id'])}/content"


def _decorate_evidence_rows(rows: list[dict]) -> list[dict]:
    decorated: list[dict] = []
    for row in rows:
        item = dict(row)
        item['url'] = _evidence_url(item)
        decorated.append(item)
    return decorated


def _cleanup_generated_file(path: Path | None) -> None:
    if not path:
        return
    try:
        if path.exists():
            path.unlink(missing_ok=True)
    except Exception:
        pass


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
    evidence = _decorate_evidence_rows(db.list_evidence(case_id))
    findings = db.case_to_findings(case_row)
    sources = db.case_to_sources(case_row)
    crew = db.case_to_crew(case_row)
    external_actors = db.case_to_external_actors(case_row)
    interviews = db.case_to_interviews(case_row)
    return render_template(request, 'case_form.html', case=case_row, evidence=evidence, findings=findings, sources=sources, crew=crew, external_actors=external_actors, interviews=interviews, law_browser=catalog.law_browser_data(), leisure_fields=catalog.LEISURE_FIELDS, commercial_fields=catalog.COMMERCIAL_FIELDS)


@router.post('/cases/{case_id}/save')
async def save_case(request: Request, case_id: int):
    await verify_csrf(request)
    user = require_permission(request, 'kv_kontroll', detail='Brukeren har ikke tilgang til KV Kontroll.')
    get_case_for_user(user, case_id)
    form = await request.form()
    data = case_data_from_form(form, user, STATUS_OPTIONS)
    db.save_case(case_id, data)
    db.update_user_last_names(user['id'], data['complainant_name'], data['witness_name'])
    db.record_audit(user['id'], 'save_case', 'case', case_id, {'status': data['status']})
    return RedirectResponse(f'/cases/{case_id}/edit?saved=1', status_code=HTTP_303_SEE_OTHER)


@router.post('/api/cases/{case_id}/autosave')
async def autosave_case(request: Request, case_id: int):
    await verify_csrf(request)
    user = require_permission(request, 'kv_kontroll', detail='Brukeren har ikke tilgang til KV Kontroll.')
    get_case_for_user(user, case_id)
    form = await request.form()
    data = case_data_from_form(form, user, STATUS_OPTIONS)
    db.save_case(case_id, data)
    db.update_user_last_names(user['id'], data['complainant_name'], data['witness_name'])
    db.record_audit(user['id'], 'autosave_case', 'case', case_id, {'status': data['status']})
    return JSONResponse({'ok': True, 'saved_at': db.utcnow_iso()})


@router.post('/cases/{case_id}/delete')
async def delete_case(request: Request, case_id: int):
    await verify_csrf(request)
    admin = require_control_admin(request)
    case_row = db.get_case(case_id)
    if not case_row:
        return RedirectResponse('/admin/controls', status_code=HTTP_303_SEE_OTHER)
    db.soft_delete_case(case_id, admin['id'])
    db.record_audit(admin['id'], 'soft_delete_case', 'case', case_id, {'case_number': case_row['case_number']})
    return RedirectResponse('/admin/controls?deleted=1', status_code=HTTP_303_SEE_OTHER)


@router.post('/cases/{case_id}/evidence')
async def upload_evidence(request: Request, case_id: int, caption: str = Form(default=''), finding_key: str = Form(default=''), law_text: str = Form(default=''), violation_reason: str = Form(default=''), seizure_ref: str = Form(default=''), file: UploadFile = File(...)):
    await verify_csrf(request)
    user = require_permission(request, 'kv_kontroll', detail='Brukeren har ikke tilgang til KV Kontroll.')
    get_case_for_user(user, case_id)
    evidence_id, filename = store_evidence_upload(case_id=case_id, upload_file=file, caption=caption, created_by=user['id'], finding_key=finding_key, law_text=law_text, violation_reason=violation_reason, seizure_ref=seizure_ref)
    db.record_audit(user['id'], 'upload_evidence', 'evidence', evidence_id, {'case_id': case_id, 'filename': filename})
    return RedirectResponse(f'/cases/{case_id}/edit', status_code=HTTP_303_SEE_OTHER)


@router.post('/api/cases/{case_id}/evidence')
async def upload_evidence_api(request: Request, case_id: int, caption: str = Form(default=''), finding_key: str = Form(default=''), law_text: str = Form(default=''), violation_reason: str = Form(default=''), seizure_ref: str = Form(default=''), file: UploadFile = File(...)):
    await verify_csrf(request)
    user = require_permission(request, 'kv_kontroll', detail='Brukeren har ikke tilgang til KV Kontroll.')
    get_case_for_user(user, case_id)
    evidence_id, filename = store_evidence_upload(case_id=case_id, upload_file=file, caption=caption, created_by=user['id'], finding_key=finding_key, law_text=law_text, violation_reason=violation_reason, seizure_ref=seizure_ref)
    row = db.get_evidence_by_id(evidence_id) or {}
    payload = dict(row)
    if payload.get('id'):
        payload['url'] = _evidence_url(payload)
    db.record_audit(user['id'], 'upload_evidence_api', 'evidence', evidence_id, {'case_id': case_id, 'filename': filename})
    return JSONResponse({'ok': True, 'message': 'Bildebevis er lagret i illustrasjonsrapporten.', 'evidence': payload})


@router.get('/evidence/{evidence_id}/content')
def serve_evidence_content(request: Request, evidence_id: int):
    user = require_permission(request, 'kv_kontroll', detail='Brukeren har ikke tilgang til KV Kontroll.')
    row = db.get_evidence_by_id(evidence_id)
    if not row:
        return JSONResponse({'ok': False, 'detail': 'Vedlegget finnes ikke.'}, status_code=404)
    get_case_for_user(user, int(row['case_id']))
    filename = str(row.get('filename') or '').strip()
    from ..config import settings
    src = settings.upload_dir / filename
    if not src.exists():
        return JSONResponse({'ok': False, 'detail': 'Vedleggsfilen finnes ikke.'}, status_code=404)
    return FileResponse(path=str(src), media_type=str(row.get('mime_type') or 'application/octet-stream'))


@router.post('/evidence/{evidence_id}/delete')
async def delete_evidence(request: Request, evidence_id: int):
    await verify_csrf(request)
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
    evidence = _decorate_evidence_rows(db.list_evidence(case_id))
    packet = build_case_preview_packet(case_row, evidence)
    db.record_audit(user['id'], 'preview_case', 'case', case_id, {})
    return render_template(request, 'case_preview.html', case=case_row, evidence=evidence, packet=packet)


@router.get('/cases/{case_id}/overview-map')
def preview_overview_map(request: Request, case_id: int):
    user = require_permission(request, 'kv_kontroll', detail='Brukeren har ikke tilgang til KV Kontroll.')
    case_row = get_case_for_user(user, case_id)
    evidence = _decorate_evidence_rows(db.list_evidence(case_id))
    packet = build_case_preview_packet(case_row, evidence)
    map_items = [item for item in list(packet.get('evidence') or []) if str(item.get('finding_key') or '') == 'oversiktskart']
    if not map_items:
        return JSONResponse({'ok': False, 'detail': 'Kartforhåndsvisning er ikke tilgjengelig.'}, status_code=404)
    generated_path = Path(str(map_items[0].get('generated_path') or ''))
    if not generated_path.exists():
        return JSONResponse({'ok': False, 'detail': 'Kartfilen finnes ikke.'}, status_code=404)
    return FileResponse(path=str(generated_path), media_type='image/png', background=BackgroundTask(_cleanup_generated_file, generated_path))


@router.post('/cases/{case_id}/preview/save')
async def preview_save_case(request: Request, case_id: int):
    await verify_csrf(request)
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
    return FileResponse(path=str(outpath), media_type='application/pdf', filename=outpath.name, background=BackgroundTask(_cleanup_generated_file, outpath))


@router.get('/cases/{case_id}/interview-pdf')
def export_interview_pdf_route(request: Request, case_id: int):
    user = require_permission(request, 'kv_kontroll', detail='Brukeren har ikke tilgang til KV Kontroll.')
    case_row = get_case_for_user(user, case_id)
    outpath = export_interview_pdf(case_id, case_row, user)
    db.record_audit(user['id'], 'export_interview_pdf', 'case', case_id, {'filename': outpath.name})
    return FileResponse(path=str(outpath), media_type='application/pdf', filename=outpath.name, background=BackgroundTask(_cleanup_generated_file, outpath))


@router.get('/cases/{case_id}/bundle')
def export_case_bundle_route(request: Request, case_id: int):
    user = require_permission(request, 'kv_kontroll', detail='Brukeren har ikke tilgang til KV Kontroll.')
    case_row = get_case_for_user(user, case_id)
    bundle_path = export_case_bundle(case_id, case_row, user)
    refreshed_case = db.get_case(case_id) or case_row
    db.record_audit(user['id'], 'export_bundle', 'case', case_id, {'filename': bundle_path.name, 'has_avvik': case_has_avvik(refreshed_case)})
    return FileResponse(path=str(bundle_path), media_type='application/zip', filename=bundle_path.name, background=BackgroundTask(_cleanup_generated_file, bundle_path))
