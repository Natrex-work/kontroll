from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from starlette.status import HTTP_303_SEE_OTHER

from .. import db
from ..auth import verify_password
from ..dependencies import current_user, first_allowed_path
from ..security import login_attempt_limiter, verify_csrf
from ..ui import render_template

router = APIRouter()


def _login_page(request: Request, *, error: str | None = None):
    has_users = db.count_users() > 0
    return render_template(request, 'login.html', error=error, has_users=has_users)


@router.get('/', response_class=HTMLResponse)
def index(request: Request):
    user = current_user(request)
    if user:
        return RedirectResponse(first_allowed_path(user) or '/login', status_code=HTTP_303_SEE_OTHER)
    return RedirectResponse('/login', status_code=HTTP_303_SEE_OTHER)


@router.get('/login', response_class=HTMLResponse)
def login_page(request: Request):
    return _login_page(request)


@router.post('/login')
async def login(request: Request):
    await verify_csrf(request)
    client_ip = getattr(request.client, 'host', '') or 'unknown'
    form = await request.form()
    email = str(form.get('email') or '').strip().lower()
    password = str(form.get('password') or '')
    rate_key = f'{client_ip}:{email}'
    if login_attempt_limiter.is_blocked(rate_key):
        return _login_page(request, error='For mange innloggingsforsøk. Vent litt og prøv igjen.')

    user = db.get_user_by_email(email)
    if not user or not verify_password(password, user['password_hash']):
        login_attempt_limiter.add_failure(rate_key)
        return _login_page(request, error='Feil e-post eller passord.')
    if not int(user.get('active', 1)):
        return _login_page(request, error='Brukeren er deaktivert av admin.')
    landing = first_allowed_path(user)
    if not landing:
        return _login_page(request, error='Brukeren har ingen aktive moduler. Kontakt admin.')
    request.session.clear()
    request.session['user_id'] = user['id']
    db.record_audit(user['id'], 'login', 'user', user['id'], {'email': user['email']})
    login_attempt_limiter.clear(rate_key)
    return RedirectResponse(landing, status_code=HTTP_303_SEE_OTHER)


@router.post('/logout')
async def logout(request: Request):
    await verify_csrf(request)
    user = current_user(request)
    if user:
        db.record_audit(user['id'], 'logout', 'user', user['id'], {'email': user['email']})
    request.session.clear()
    return RedirectResponse('/login', status_code=HTTP_303_SEE_OTHER)
