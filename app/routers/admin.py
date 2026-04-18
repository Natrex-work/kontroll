from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from starlette.status import HTTP_303_SEE_OTHER

from .. import db
from ..auth import hash_password
from ..dependencies import require_control_admin, require_user_admin
from ..ui import render_template
from ..validation import validate_case_prefix, validate_email, validate_password, validate_role
from ..security import verify_csrf

router = APIRouter()


def _selected_permissions(form, role: str) -> list[str]:
    if role == 'admin':
        return list(db.DEFAULT_ADMIN_PERMISSIONS)
    allowed = list(db.INVESTIGATOR_PERMISSION_OPTIONS)
    selected = {str(value).strip() for value in form.getlist('permissions') if str(value).strip() in allowed}
    cleaned = [permission for permission in allowed if permission in selected]
    if not cleaned:
        raise HTTPException(status_code=400, detail='Velg minst én modul for brukeren.')
    return cleaned


@router.get('/admin/users', response_class=HTMLResponse)
def admin_users(request: Request):
    require_user_admin(request)
    users = db.list_users()
    return render_template(request, 'admin_users.html', users=users)


@router.post('/admin/users')
async def admin_create_user(request: Request):
    await verify_csrf(request)
    admin = require_user_admin(request)
    form = await request.form()
    users = db.list_users()
    try:
        email = validate_email(form.get('email'))
        full_name = str(form.get('full_name') or '').strip()
        if not full_name:
            raise HTTPException(status_code=400, detail='Fyll ut navn.')
        password = validate_password(form.get('password'))
        role = validate_role(form.get('role') or 'investigator', ('investigator', 'admin'))
        permissions = _selected_permissions(form, role)
        complainant = str(form.get('last_complainant_name') or '').strip() or None
        witness = str(form.get('last_witness_name') or '').strip() or None
        case_prefix = validate_case_prefix(form.get('case_prefix') or 'LBHN')
        address = str(form.get('address') or '').strip() or None
        phone = str(form.get('phone') or '').strip() or None
        vessel_affiliation = str(form.get('vessel_affiliation') or '').strip() or None
        user_id = db.create_user(
            email=email,
            full_name=full_name,
            password_hash=hash_password(password),
            role=role,
            address=address,
            phone=phone,
            vessel_affiliation=vessel_affiliation,
            permissions=permissions,
            last_complainant_name=complainant,
            last_witness_name=witness,
            case_prefix=case_prefix,
            active=True,
        )
        db.record_audit(admin['id'], 'create_user', 'user', user_id, {'email': email, 'role': role, 'permissions': permissions, 'case_prefix': case_prefix})
    except HTTPException as exc:
        return render_template(request, 'admin_users.html', users=users, error=exc.detail)
    except Exception as exc:
        return render_template(request, 'admin_users.html', users=users, error=f'Kunne ikke opprette bruker: {exc}')
    return RedirectResponse('/admin/users?created=1', status_code=HTTP_303_SEE_OTHER)


@router.post('/admin/users/{user_id}/update')
async def admin_update_user(request: Request, user_id: int):
    await verify_csrf(request)
    admin = require_user_admin(request)
    user_row = db.get_user_by_id(user_id)
    if not user_row:
        raise HTTPException(status_code=404, detail='Fant ikke bruker.')
    form = await request.form()
    users = db.list_users()
    try:
        full_name = str(form.get('full_name') or '').strip()
        if not full_name:
            raise HTTPException(status_code=400, detail='Navn mangler.')
        role = validate_role(form.get('role') or 'investigator', ('investigator', 'admin'))
        if int(user_row['id']) == int(admin['id']) and role != 'admin':
            raise HTTPException(status_code=400, detail='Admin kan ikke endre sin egen rolle bort fra admin.')
        active = str(form.get('active') or '0') == '1'
        if int(user_row['id']) == int(admin['id']) and not active:
            raise HTTPException(status_code=400, detail='Admin kan ikke deaktivere sin egen bruker.')
        permissions = _selected_permissions(form, role)
        complainant = str(form.get('last_complainant_name') or '').strip() or None
        witness = str(form.get('last_witness_name') or '').strip() or None
        case_prefix = validate_case_prefix(form.get('case_prefix') or user_row.get('case_prefix') or 'LBHN')
        address = str(form.get('address') or '').strip() or None
        phone = str(form.get('phone') or '').strip() or None
        vessel_affiliation = str(form.get('vessel_affiliation') or '').strip() or None
        db.update_user(
            user_id,
            full_name=full_name,
            role=role,
            active=active,
            address=address,
            phone=phone,
            vessel_affiliation=vessel_affiliation,
            permissions=permissions,
            last_complainant_name=complainant,
            last_witness_name=witness,
            case_prefix=case_prefix,
        )
        db.record_audit(admin['id'], 'update_user', 'user', user_id, {'role': role, 'active': active, 'permissions': permissions, 'case_prefix': case_prefix})
    except HTTPException as exc:
        return render_template(request, 'admin_users.html', users=users, error=exc.detail)
    return RedirectResponse('/admin/users?updated=1', status_code=HTTP_303_SEE_OTHER)


@router.post('/admin/users/{user_id}/reset-password')
async def admin_reset_password(request: Request, user_id: int):
    await verify_csrf(request)
    admin = require_user_admin(request)
    user_row = db.get_user_by_id(user_id)
    if not user_row:
        raise HTTPException(status_code=404, detail='Fant ikke bruker.')
    form = await request.form()
    users = db.list_users()
    try:
        password = validate_password(form.get('password'))
        db.set_user_password(user_id, hash_password(password))
        db.record_audit(admin['id'], 'reset_password', 'user', user_id, {'email': user_row['email']})
    except HTTPException as exc:
        return render_template(request, 'admin_users.html', users=users, error=exc.detail)
    return RedirectResponse('/admin/users?password=1', status_code=HTTP_303_SEE_OTHER)


@router.post('/admin/users/{user_id}/remove')
async def admin_remove_user(request: Request, user_id: int):
    await verify_csrf(request)
    admin = require_user_admin(request)
    user_row = db.get_user_by_id(user_id)
    if not user_row:
        raise HTTPException(status_code=404, detail='Fant ikke bruker.')
    if int(user_row['id']) == int(admin['id']):
        raise HTTPException(status_code=400, detail='Admin kan ikke fjerne sin egen bruker.')
    db.remove_user(user_id)
    db.record_audit(admin['id'], 'remove_user', 'user', user_id, {'email': user_row['email']})
    return RedirectResponse('/admin/users?removed=1', status_code=HTTP_303_SEE_OTHER)


@router.get('/admin/controls', response_class=HTMLResponse)
def admin_controls(request: Request, state: str = 'active', q: str = ''):
    require_control_admin(request)
    counts = db.admin_case_counts()
    cases = db.list_cases_for_admin(deleted_filter=state, search=q)
    return render_template(request, 'admin_controls.html', cases=cases, counts=counts, state=state, q=q)


@router.post('/admin/controls/{case_id}/delete')
async def admin_delete_control(request: Request, case_id: int):
    await verify_csrf(request)
    admin = require_control_admin(request)
    case_row = db.get_case(case_id)
    if not case_row:
        raise HTTPException(status_code=404, detail='Fant ikke saken.')
    if case_row.get('deleted_at'):
        return RedirectResponse('/admin/controls?state=deleted', status_code=HTTP_303_SEE_OTHER)
    db.soft_delete_case(case_id, admin['id'])
    db.record_audit(admin['id'], 'soft_delete_case', 'case', case_id, {'case_number': case_row['case_number']})
    return RedirectResponse('/admin/controls?state=active&deleted=1', status_code=HTTP_303_SEE_OTHER)


@router.post('/admin/controls/{case_id}/restore')
async def admin_restore_control(request: Request, case_id: int):
    await verify_csrf(request)
    admin = require_control_admin(request)
    case_row = db.get_case(case_id)
    if not case_row:
        raise HTTPException(status_code=404, detail='Fant ikke saken.')
    if not case_row.get('deleted_at'):
        return RedirectResponse('/admin/controls?state=active', status_code=HTTP_303_SEE_OTHER)
    db.restore_case(case_id)
    db.record_audit(admin['id'], 'restore_case', 'case', case_id, {'case_number': case_row['case_number']})
    return RedirectResponse('/admin/controls?state=deleted&restored=1', status_code=HTTP_303_SEE_OTHER)
