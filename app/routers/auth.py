from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from starlette.status import HTTP_303_SEE_OTHER

from .. import db
from ..auth import verify_password
from ..dependencies import current_user, first_allowed_path
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
    return render_template(request, 'login.html')


@router.post('/login')
async def login(request: Request):
    form = await request.form()
    email = str(form.get('email') or '').strip().lower()
    password = str(form.get('password') or '')
    user = db.get_user_by_email(email)
    if not user or not verify_password(password, user['password_hash']):
        return render_template(request, 'login.html', error='Feil e-post eller passord.')
    if not int(user.get('active', 1)):
        return render_template(request, 'login.html', error='Brukeren er deaktivert av admin.')
    landing = first_allowed_path(user)
    if not landing:
        return render_template(request, 'login.html', error='Brukeren har ingen aktive moduler. Kontakt admin.')
    request.session['user_id'] = user['id']
    db.record_audit(user['id'], 'login', 'user', user['id'], {'email': user['email']})
    return RedirectResponse(landing, status_code=HTTP_303_SEE_OTHER)


@router.post('/logout')
def logout(request: Request):
    user = current_user(request)
    if user:
        db.record_audit(user['id'], 'logout', 'user', user['id'], {'email': user['email']})
    request.session.clear()
    return RedirectResponse('/login', status_code=HTTP_303_SEE_OTHER)
