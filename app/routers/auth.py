from __future__ import annotations

from datetime import datetime, timedelta, timezone
import hashlib
import hmac
import secrets

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from starlette.status import HTTP_303_SEE_OTHER

from .. import db
from ..auth import hash_password, password_needs_rehash, verify_password
from ..config import settings
from ..dependencies import current_user, first_allowed_path
from ..security import check_login_rate_limit, check_otp_send_rate_limit, clear_login_failures, client_ip, enforce_csrf, issue_authenticated_session, record_login_failure, record_otp_send_attempt
from ..services.sms_service import send_login_code, sms_configured
from ..ui import render_template

router = APIRouter()



PENDING_OTP_USER_ID = 'pending_otp_user_id'
PENDING_OTP_CHALLENGE_ID = 'pending_otp_challenge_id'
PENDING_OTP_LANDING = 'pending_otp_landing'


def _otp_required_for_user(user: dict) -> bool:
    if not settings.otp_enabled:
        return False
    if str(user.get('role') or '').strip().lower() == 'admin':
        return False
    return True


def _hash_otp_code(code: str) -> str:
    key = settings.session_secret.encode('utf-8', errors='ignore')
    return hmac.new(key, str(code or '').strip().encode('utf-8'), hashlib.sha256).hexdigest()


def _generate_otp_code() -> str:
    length = max(6, min(8, int(settings.otp_length or 6)))
    upper = 10 ** length
    return f'{secrets.randbelow(upper):0{length}d}'


def _otp_expires_at() -> str:
    return (datetime.now(timezone.utc) + timedelta(seconds=settings.otp_ttl_seconds)).strftime('%Y-%m-%dT%H:%M:%SZ')


def _is_expired_iso(value: str) -> bool:
    try:
        expires = datetime.strptime(str(value), '%Y-%m-%dT%H:%M:%SZ').replace(tzinfo=timezone.utc)
    except Exception:
        return True
    return datetime.now(timezone.utc) > expires


def _mask_phone(phone: str) -> str:
    digits = ''.join(ch for ch in str(phone or '') if ch.isdigit())
    if len(digits) >= 8:
        return f'*** ** {digits[-3:]}'
    return 'registrert mobilnummer'


def _start_otp_challenge(request: Request, user: dict, landing: str) -> HTMLResponse:
    phone = str(user.get('phone') or '').strip()
    if not phone:
        return render_template(request, 'login.html', error='Brukeren mangler registrert mobilnummer. Kontakt admin for å legge inn mobilnummer før innlogging.')
    try:
        check_otp_send_rate_limit(request, int(user['id']))
    except HTTPException as exc:
        return render_template(request, 'login.html', error=exc.detail)

    code = _generate_otp_code()
    challenge_id = db.create_login_otp_challenge(
        user_id=int(user['id']),
        phone=phone,
        code_hash=_hash_otp_code(code),
        expires_at=_otp_expires_at(),
        max_attempts=settings.otp_max_attempts,
        ip_address=client_ip(request),
        user_agent=str(request.headers.get('user-agent') or '')[:250],
    )
    try:
        send_result = send_login_code(phone, code)
    except Exception as exc:
        db.record_audit(user['id'], 'otp_send_failed', 'user', user['id'], {'error': str(exc), 'phone': _mask_phone(phone)})
        return render_template(request, 'login.html', error=f'Kunne ikke sende innloggingskode: {exc}')

    record_otp_send_attempt(request, int(user['id']))
    request.session.clear()
    request.session[PENDING_OTP_USER_ID] = int(user['id'])
    request.session[PENDING_OTP_CHALLENGE_ID] = int(challenge_id)
    request.session[PENDING_OTP_LANDING] = landing
    db.record_audit(user['id'], 'otp_sent', 'user', user['id'], {'phone': _mask_phone(phone), 'provider': send_result.get('provider')})
    dev_code = code if (send_result.get('provider') == 'dev-log' and settings.otp_dev_log_codes) else ''
    return render_template(
        request,
        'login_2fa.html',
        masked_phone=_mask_phone(phone),
        dev_code=dev_code,
        sms_configured=sms_configured(),
        otp_ttl_minutes=max(1, settings.otp_ttl_seconds // 60),
    )


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
    if _otp_required_for_user(user):
        return _start_otp_challenge(request, user, landing)
    issue_authenticated_session(request, int(user['id']))
    db.record_audit(user['id'], 'login', 'user', user['id'], {'email': user['email'], 'two_factor': False})
    return RedirectResponse(landing, status_code=HTTP_303_SEE_OTHER)


@router.get('/login/2fa', response_class=HTMLResponse)
def login_2fa_page(request: Request):
    if not settings.otp_enabled:
        return RedirectResponse('/login', status_code=HTTP_303_SEE_OTHER)
    challenge_id = request.session.get(PENDING_OTP_CHALLENGE_ID)
    user_id = request.session.get(PENDING_OTP_USER_ID)
    if not challenge_id or not user_id:
        return RedirectResponse('/login', status_code=HTTP_303_SEE_OTHER)
    user = db.get_user_by_id(int(user_id))
    challenge = db.get_login_otp_challenge(int(challenge_id))
    if not user or not challenge or challenge.get('consumed_at') or _is_expired_iso(str(challenge.get('expires_at') or '')):
        request.session.clear()
        return RedirectResponse('/login', status_code=HTTP_303_SEE_OTHER)
    return render_template(request, 'login_2fa.html', masked_phone=_mask_phone(str(challenge.get('phone') or user.get('phone') or '')), otp_ttl_minutes=max(1, settings.otp_ttl_seconds // 60), sms_configured=sms_configured())


@router.post('/login/2fa')
async def login_2fa(request: Request):
    if not settings.otp_enabled:
        return RedirectResponse('/login', status_code=HTTP_303_SEE_OTHER)
    form = await request.form()
    try:
        enforce_csrf(request, form)
    except HTTPException:
        return render_template(request, 'login_2fa.html', error='Sikkerhetssjekk feilet. Last siden på nytt og prøv igjen.')
    challenge_id = request.session.get(PENDING_OTP_CHALLENGE_ID)
    user_id = request.session.get(PENDING_OTP_USER_ID)
    landing = str(request.session.get(PENDING_OTP_LANDING) or '/dashboard')
    if not challenge_id or not user_id:
        return RedirectResponse('/login', status_code=HTTP_303_SEE_OTHER)
    user = db.get_user_by_id(int(user_id))
    challenge = db.get_login_otp_challenge(int(challenge_id))
    if not user or not int(user.get('active', 1)) or not challenge:
        request.session.clear()
        return RedirectResponse('/login', status_code=HTTP_303_SEE_OTHER)
    masked_phone = _mask_phone(str(challenge.get('phone') or user.get('phone') or ''))
    if challenge.get('consumed_at'):
        request.session.clear()
        return render_template(request, 'login.html', error='Innloggingskoden er allerede brukt. Logg inn på nytt.')
    if _is_expired_iso(str(challenge.get('expires_at') or '')):
        request.session.clear()
        return render_template(request, 'login.html', error='Innloggingskoden er utløpt. Logg inn på nytt for å få ny kode.')
    if int(challenge.get('attempts') or 0) >= int(challenge.get('max_attempts') or settings.otp_max_attempts):
        request.session.clear()
        db.record_audit(user['id'], 'otp_locked', 'user', user['id'], {'phone': masked_phone})
        return render_template(request, 'login.html', error='For mange feil kodeforsøk. Logg inn på nytt for å få ny kode.')

    code = ''.join(ch for ch in str(form.get('code') or '') if ch.isdigit())
    if not code or not hmac.compare_digest(_hash_otp_code(code), str(challenge.get('code_hash') or '')):
        attempts = db.record_login_otp_attempt(int(challenge_id))
        remaining = max(0, int(challenge.get('max_attempts') or settings.otp_max_attempts) - attempts)
        db.record_audit(user['id'], 'otp_failed', 'user', user['id'], {'remaining_attempts': remaining})
        return render_template(request, 'login_2fa.html', error=f'Feil kode. Forsøk igjen. Gjenstående forsøk: {remaining}.', masked_phone=masked_phone, otp_ttl_minutes=max(1, settings.otp_ttl_seconds // 60), sms_configured=sms_configured())

    db.consume_login_otp_challenge(int(challenge_id))
    issue_authenticated_session(request, int(user['id']))
    db.record_audit(user['id'], 'login', 'user', user['id'], {'email': user['email'], 'two_factor': True})
    return RedirectResponse(landing, status_code=HTTP_303_SEE_OTHER)


@router.post('/login/2fa/resend')
async def resend_login_2fa(request: Request):
    if not settings.otp_enabled:
        return RedirectResponse('/login', status_code=HTTP_303_SEE_OTHER)
    form = await request.form()
    try:
        enforce_csrf(request, form)
    except HTTPException:
        return render_template(request, 'login_2fa.html', error='Sikkerhetssjekk feilet. Last siden på nytt og prøv igjen.')
    user_id = request.session.get(PENDING_OTP_USER_ID)
    landing = str(request.session.get(PENDING_OTP_LANDING) or '/dashboard')
    if not user_id:
        return RedirectResponse('/login', status_code=HTTP_303_SEE_OTHER)
    user = db.get_user_by_id(int(user_id))
    if not user or not int(user.get('active', 1)):
        request.session.clear()
        return RedirectResponse('/login', status_code=HTTP_303_SEE_OTHER)
    return _start_otp_challenge(request, user, landing)


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
