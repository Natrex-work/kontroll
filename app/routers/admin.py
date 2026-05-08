from __future__ import annotations

import json
import sqlite3
import time
from pathlib import Path

from fastapi import APIRouter, File, HTTPException, Request, UploadFile
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from starlette.status import HTTP_303_SEE_OTHER

from .. import db, live_sources, registry
from ..auth import hash_password
from ..dependencies import require_control_admin, require_user_admin
from ..logging_setup import get_logger
from ..security import enforce_csrf
from ..services.sms_service import send_user_invitation
from ..ui import render_template
from ..validation import validate_case_prefix, validate_email, validate_login_mobile, validate_password, validate_role

logger = get_logger(__name__)

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
    """Opprett ny bruker. Defensiv mot alle feilmoduser:
    - Bevarer skjemaverdier ved valideringsfeil (slipper å fylle ut alt på nytt)
    - Logger detaljert hva som feilet
    - Returnerer alltid en HTML-side, aldri 500
    """
    admin = require_user_admin(request)
    form = await request.form()

    # Samle inn alle skjemaverdier først, slik at vi kan bevare dem ved feil
    raw = {
        'full_name': str(form.get('full_name') or '').strip(),
        'email': str(form.get('email') or '').strip(),
        'phone': str(form.get('phone') or '').strip(),
        'role': str(form.get('role') or 'investigator').strip(),
        'address': str(form.get('address') or '').strip(),
        'vessel_affiliation': str(form.get('vessel_affiliation') or '').strip(),
        'case_prefix': str(form.get('case_prefix') or 'LBHN').strip(),
        'last_complainant_name': str(form.get('last_complainant_name') or '').strip(),
        'last_witness_name': str(form.get('last_witness_name') or '').strip(),
        'permissions': [str(p).strip() for p in form.getlist('permissions') if str(p).strip()],
    }

    def _render_error(detail: str):
        try:
            users = db.list_users()
        except Exception as exc:
            logger.error('Kunne ikke hente brukerliste i feilflyt: %s', exc)
            users = []
        return render_template(
            request,
            'admin_users.html',
            users=users,
            error=detail,
            preserved=raw,
        )

    try:
        enforce_csrf(request, form)
    except HTTPException as exc:
        logger.info('CSRF-feil ved brukeropprettelse: %s', exc.detail)
        return _render_error('Sikkerhetssjekk feilet. Last siden på nytt og prøv igjen.')

    try:
        email = validate_email(raw['email'])
        if not raw['full_name']:
            raise HTTPException(status_code=400, detail='Fyll ut fullt navn.')
        password = validate_password(form.get('password'))
        role = validate_role(raw['role'] or 'investigator', ('investigator', 'admin'))
        existing = db.get_user_by_email(email)
        if existing:
            raise HTTPException(status_code=400, detail='Det finnes allerede en bruker med denne e-postadressen.')
        permissions = _selected_permissions(form, role)
        case_prefix = validate_case_prefix(raw['case_prefix'] or 'LBHN')
        phone = validate_login_mobile(raw['phone'], required=False)
    except HTTPException as exc:
        logger.info('Valideringsfeil ved brukeropprettelse: %s', exc.detail)
        return _render_error(str(exc.detail))
    except Exception as exc:
        logger.exception('Uventet valideringsfeil ved brukeropprettelse')
        return _render_error(f'Kunne ikke validere skjemaet: {exc}')

    # Opprett bruker
    try:
        user_id = db.create_user(
            email=email,
            full_name=raw['full_name'],
            password_hash=hash_password(password),
            role=role,
            address=raw['address'] or None,
            phone=phone,
            vessel_affiliation=raw['vessel_affiliation'] or None,
            permissions=permissions,
            last_complainant_name=raw['last_complainant_name'] or None,
            last_witness_name=raw['last_witness_name'] or None,
            case_prefix=case_prefix,
            active=True,
            two_factor_required=False,
        )
    except sqlite3.IntegrityError as exc:
        logger.warning('IntegrityError ved create_user: %s', exc)
        return _render_error('Kunne ikke opprette bruker. E-postadressen er trolig allerede registrert.')
    except Exception as exc:
        logger.exception('Uventet feil i db.create_user')
        return _render_error(f'Kunne ikke opprette bruker i databasen: {exc}')

    # Audit
    try:
        db.record_audit(admin['id'], 'create_user', 'user', user_id,
                        {'email': email, 'role': role, 'permissions': permissions, 'case_prefix': case_prefix})
    except Exception as exc:
        # Audit failure should not block user creation
        logger.warning('Audit-logg for create_user feilet (ignorert): %s', exc)

    # Optional: SMS invitation (available for any user with a phone number)
    invite_status = ''
    send_invite = str(form.get('send_invitation_sms') or '').strip() in {'1', 'true', 'on', 'yes'}
    if send_invite and phone:
        try:
            login_url = str(request.base_url).rstrip('/') + '/login'
            send_user_invitation(phone, raw['full_name'], password, login_url=login_url)
            invite_status = 'sent'
            try:
                db.record_audit(admin['id'], 'send_invitation_sms', 'user', user_id, {'phone': phone})
            except Exception:
                pass
        except Exception as exc:
            logger.warning('Kunne ikke sende invitasjons-SMS til %s: %s', phone, exc)
            invite_status = 'failed'

    from urllib.parse import urlencode
    qs = urlencode({
        'created': '1',
        'email': email,
        'phone': phone or '',
        'invite': invite_status,
    })
    return RedirectResponse(f'/admin/users?{qs}', status_code=HTTP_303_SEE_OTHER)



@router.post('/admin/users/{user_id}/update')
async def admin_update_user(request: Request, user_id: int):
    admin = require_user_admin(request)
    user_row = db.get_user_by_id(user_id)
    if not user_row:
        raise HTTPException(status_code=404, detail='Fant ikke bruker.')
    form = await request.form()
    users = db.list_users()
    try:
        enforce_csrf(request, form)
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
        phone = validate_login_mobile(form.get('phone'), required=False)
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
            two_factor_required=False,
        )
        db.record_audit(admin['id'], 'update_user', 'user', user_id, {'role': role, 'active': active, 'permissions': permissions, 'case_prefix': case_prefix})
    except HTTPException as exc:
        return render_template(request, 'admin_users.html', users=users, error=exc.detail)
    except Exception as exc:
        return render_template(request, 'admin_users.html', users=users, error=f'Kunne ikke oppdatere bruker: {exc}')
    return RedirectResponse('/admin/users?updated=1', status_code=HTTP_303_SEE_OTHER)


@router.post('/admin/users/{user_id}/reset-password')
async def admin_reset_password(request: Request, user_id: int):
    admin = require_user_admin(request)
    user_row = db.get_user_by_id(user_id)
    if not user_row:
        raise HTTPException(status_code=404, detail='Fant ikke bruker.')
    form = await request.form()
    users = db.list_users()
    try:
        enforce_csrf(request, form)
        password = validate_password(form.get('password'))
        db.set_user_password(user_id, hash_password(password))
        db.record_audit(admin['id'], 'reset_password', 'user', user_id, {'email': user_row['email']})
    except HTTPException as exc:
        return render_template(request, 'admin_users.html', users=users, error=exc.detail)
    except Exception as exc:
        return render_template(request, 'admin_users.html', users=users, error=f'Kunne ikke nullstille passord: {exc}')
    return RedirectResponse('/admin/users?password=1', status_code=HTTP_303_SEE_OTHER)


@router.post('/admin/users/{user_id}/remove')
async def admin_remove_user(request: Request, user_id: int):
    admin = require_user_admin(request)
    user_row = db.get_user_by_id(user_id)
    if not user_row:
        raise HTTPException(status_code=404, detail='Fant ikke bruker.')
    form = await request.form()
    try:
        enforce_csrf(request, form)
    except HTTPException as exc:
        raise HTTPException(status_code=403, detail=exc.detail) from exc
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
    admin = require_control_admin(request)
    form = await request.form()
    enforce_csrf(request, form)
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
    admin = require_control_admin(request)
    form = await request.form()
    enforce_csrf(request, form)
    case_row = db.get_case(case_id)
    if not case_row:
        raise HTTPException(status_code=404, detail='Fant ikke saken.')
    if not case_row.get('deleted_at'):
        return RedirectResponse('/admin/controls?state=active', status_code=HTTP_303_SEE_OTHER)
    db.restore_case(case_id)
    db.record_audit(admin['id'], 'restore_case', 'case', case_id, {'case_number': case_row['case_number']})
    return RedirectResponse('/admin/controls?state=deleted&restored=1', status_code=HTTP_303_SEE_OTHER)


# ---------------------------------------------------------------------------
# Hummerregister-administrasjon (Tableau-import)
# ---------------------------------------------------------------------------

def _hummer_cache_status() -> dict:
    """Return current cache status for display in admin UI."""
    status = {
        'has_cache': False,
        'count': 0,
        'fetched_at_iso': '',
        'fetched_age_hours': None,
        'source_url': '',
        'tableau_url': live_sources.HUMMER_REGISTER_URL,
        'fallback_url': live_sources.HUMMER_REGISTER_FALLBACK_URL,
    }
    try:
        if live_sources.HUMMER_CACHE_JSON.exists():
            data = json.loads(live_sources.HUMMER_CACHE_JSON.read_text(encoding='utf-8'))
            if isinstance(data, list):
                status['has_cache'] = True
                status['count'] = len(data)
        if live_sources.HUMMER_CACHE_META.exists():
            meta = json.loads(live_sources.HUMMER_CACHE_META.read_text(encoding='utf-8'))
            fetched_at = float(meta.get('fetched_at') or 0)
            if fetched_at:
                from datetime import datetime, timezone
                dt = datetime.fromtimestamp(fetched_at, tz=timezone.utc)
                status['fetched_at_iso'] = dt.strftime('%Y-%m-%d %H:%M UTC')
                status['fetched_age_hours'] = round((time.time() - fetched_at) / 3600, 1)
            status['source_url'] = str(meta.get('source_url') or '')
    except Exception as exc:
        logger.warning('Kunne ikke lese hummercache-status: %s', exc)
    return status


@router.get('/admin/registry', response_class=HTMLResponse)
def admin_registry_page(request: Request):
    require_user_admin(request)
    return render_template(
        request,
        'admin_registry.html',
        hummer_status=_hummer_cache_status(),
    )


@router.post('/admin/registry/hummer/upload')
async def admin_registry_hummer_upload(request: Request, file: UploadFile = File(...)):
    """Manuelt opplasting av hummer-CSV fra Tableau.

    Admin kan laste ned CSV fra
    https://tableau.fiskeridir.no/t/Internet/views/Pmeldehummarfiskarargjeldander/Pmeldehummarfiskarar
    (via «Last ned» / «Crosstab» / «Data»-alternativene i Tableau-UI),
    og laste den opp her. Filen parses og lagres i samme cache som
    automatisk live-henting bruker.
    """
    admin = require_user_admin(request)
    form = await request.form()
    try:
        enforce_csrf(request, form)
    except HTTPException:
        return RedirectResponse('/admin/registry?error=csrf', status_code=HTTP_303_SEE_OTHER)

    filename = (file.filename or 'hummer.csv').lower()
    if not filename.endswith(('.csv', '.tsv', '.txt')):
        return RedirectResponse('/admin/registry?error=format', status_code=HTTP_303_SEE_OTHER)

    try:
        raw = await file.read()
    except Exception as exc:
        logger.warning('Kunne ikke lese opplastet hummer-CSV: %s', exc)
        return RedirectResponse('/admin/registry?error=read', status_code=HTTP_303_SEE_OTHER)

    if not raw:
        return RedirectResponse('/admin/registry?error=empty', status_code=HTTP_303_SEE_OTHER)
    if len(raw) > 25 * 1024 * 1024:  # 25 MB hard cap
        return RedirectResponse('/admin/registry?error=size', status_code=HTTP_303_SEE_OTHER)

    # Try common encodings used by Tableau exports (UTF-8 BOM, UTF-16, latin-1)
    text = ''
    for encoding in ('utf-8-sig', 'utf-8', 'utf-16', 'iso-8859-1', 'cp1252'):
        try:
            text = raw.decode(encoding)
            break
        except Exception:
            continue
    if not text:
        return RedirectResponse('/admin/registry?error=encoding', status_code=HTTP_303_SEE_OTHER)

    try:
        rows = live_sources._parse_hummer_csv(text, source_url=f'admin-upload:{file.filename}')
    except Exception as exc:
        logger.warning('Parse av hummer-CSV feilet: %s', exc)
        return RedirectResponse('/admin/registry?error=parse', status_code=HTTP_303_SEE_OTHER)

    if not rows:
        return RedirectResponse('/admin/registry?error=norows', status_code=HTTP_303_SEE_OTHER)

    try:
        live_sources.HUMMER_CACHE_JSON.parent.mkdir(parents=True, exist_ok=True)
        live_sources.HUMMER_CACHE_JSON.write_text(
            json.dumps(rows, ensure_ascii=False, indent=2),
            encoding='utf-8',
        )
        live_sources.HUMMER_CACHE_META.write_text(
            json.dumps(
                {
                    'fetched_at': time.time(),
                    'source_url': f'Manuell opplasting: {file.filename}',
                    'count': len(rows),
                    'uploaded_by': admin.get('email'),
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding='utf-8',
        )
    except Exception as exc:
        logger.error('Kunne ikke skrive hummercache-fil: %s', exc)
        return RedirectResponse('/admin/registry?error=write', status_code=HTTP_303_SEE_OTHER)

    try:
        db.record_audit(admin['id'], 'hummer_registry_upload', 'registry', 0,
                        {'rows': len(rows), 'filename': file.filename})
    except Exception:
        pass

    return RedirectResponse(f'/admin/registry?uploaded={len(rows)}', status_code=HTTP_303_SEE_OTHER)


@router.post('/admin/registry/hummer/refresh')
async def admin_registry_hummer_refresh(request: Request):
    admin = require_user_admin(request)
    form = await request.form()
    try:
        enforce_csrf(request, form)
    except HTTPException:
        return RedirectResponse('/admin/registry?error=csrf', status_code=HTTP_303_SEE_OTHER)

    try:
        rows = live_sources.refresh_hummer_registry_cache(force=True)
    except Exception as exc:
        logger.warning('Live-henting av hummerregister feilet: %s', exc)
        return RedirectResponse('/admin/registry?error=live', status_code=HTTP_303_SEE_OTHER)

    try:
        db.record_audit(admin['id'], 'hummer_registry_live_refresh', 'registry', 0,
                        {'rows': len(rows or [])})
    except Exception:
        pass

    if not rows:
        return RedirectResponse('/admin/registry?error=empty_live', status_code=HTTP_303_SEE_OTHER)
    return RedirectResponse(f'/admin/registry?refreshed={len(rows)}', status_code=HTTP_303_SEE_OTHER)


@router.post('/admin/registry/hummer/clear')
async def admin_registry_hummer_clear(request: Request):
    admin = require_user_admin(request)
    form = await request.form()
    try:
        enforce_csrf(request, form)
    except HTTPException:
        return RedirectResponse('/admin/registry?error=csrf', status_code=HTTP_303_SEE_OTHER)
    try:
        if live_sources.HUMMER_CACHE_JSON.exists():
            live_sources.HUMMER_CACHE_JSON.unlink()
        if live_sources.HUMMER_CACHE_META.exists():
            live_sources.HUMMER_CACHE_META.unlink()
    except Exception as exc:
        logger.warning('Kunne ikke slette hummercache: %s', exc)
        return RedirectResponse('/admin/registry?error=clear', status_code=HTTP_303_SEE_OTHER)
    try:
        db.record_audit(admin['id'], 'hummer_registry_clear', 'registry', 0, {})
    except Exception:
        pass
    return RedirectResponse('/admin/registry?cleared=1', status_code=HTTP_303_SEE_OTHER)


@router.get('/admin/registry/hummer/sample.json')
def admin_registry_hummer_sample(request: Request):
    """Returnerer 10 første rader fra cache for verifisering i admin-UI."""
    require_user_admin(request)
    if not live_sources.HUMMER_CACHE_JSON.exists():
        return JSONResponse({'rows': []})
    try:
        data = json.loads(live_sources.HUMMER_CACHE_JSON.read_text(encoding='utf-8'))
        if isinstance(data, list):
            return JSONResponse({'rows': data[:10], 'total': len(data)})
    except Exception:
        pass
    return JSONResponse({'rows': []})
