from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from starlette.status import HTTP_303_SEE_OTHER

from .. import db
from ..auth import hash_password, password_needs_rehash, verify_password
from ..dependencies import current_user, first_allowed_path
from ..security import check_login_rate_limit, clear_login_failures, enforce_csrf, issue_authenticated_session, record_login_failure
from ..ui import render_template

router = APIRouter()


@router.get('/', response_class=HTMLResponse)
def index(request: Request):
    user = current_user(request)
    if user:
        return RedirectResponse(first_allowed_path(user) or '/login', status_code=HTTP_303_SEE_OTHER)
    return RedirectResponse('/login', status_code=HTTP_303_SEE_OTHER)


@router.get('/login', response_class=HTMLResponse)
def login_page(request: Request):
    user = current_user(request)
    if user:
        return RedirectResponse(first_allowed_path(user) or '/dashboard', status_code=HTTP_303_SEE_OTHER)
    return render_template(request, 'login.html')


@router.post('/login')
async def login(request: Request):
    form = await request.form()
    try:
        enforce_csrf(request, form)
    except HTTPException:
        return render_template(request, 'login.html', error='Sikkerhetssjekk feilet. Last siden på nytt og prøv igjen.')
    email = str(form.get('email') or '').strip().lower()
    password = str(form.get('password') or '')
    try:
        check_login_rate_limit(request, email)
    except HTTPException as exc:
        return render_template(request, 'login.html', error=exc.detail)
    user = db.get_user_by_email(email)
    if not user or not verify_password(password, user['password_hash']):
        record_login_failure(request, email)
        return render_template(request, 'login.html', error='Feil e-post eller passord.')
    if not int(user.get('active', 1)):
        record_login_failure(request, email)
        return render_template(request, 'login.html', error='Brukeren er deaktivert av admin.')
    landing = first_allowed_path(user)
    if not landing:
        return render_template(request, 'login.html', error='Brukeren har ingen aktive moduler. Kontakt admin.')
    if password_needs_rehash(user['password_hash']):
        db.set_user_password(int(user['id']), hash_password(password))
    clear_login_failures(request, email)
    issue_authenticated_session(request, int(user['id']))
    db.record_audit(user['id'], 'login', 'user', user['id'], {'email': user['email']})
    return RedirectResponse(landing, status_code=HTTP_303_SEE_OTHER)


@router.post('/logout')
def logout(request: Request):
    try:
        enforce_csrf(request)
    except HTTPException:
        request.session.clear()
        return RedirectResponse('/login', status_code=HTTP_303_SEE_OTHER)
    user = current_user(request)
    if user:
        db.record_audit(user['id'], 'logout', 'user', user['id'], {'email': user['email']})
    request.session.clear()
    return RedirectResponse('/login', status_code=HTTP_303_SEE_OTHER)
