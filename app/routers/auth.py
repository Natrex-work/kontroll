from __future__ import annotations

import secrets
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from starlette.status import HTTP_303_SEE_OTHER

from .. import db
from ..auth import hash_password, password_needs_rehash, verify_password
from ..dependencies import current_user, first_allowed_path
from ..security import (
    check_login_rate_limit,
    clear_login_failures,
    enforce_csrf,
    issue_authenticated_session,
    record_login_failure,
)
from ..services.sms_service import (
    OTP_EXPIRE_SECONDS,
    OTP_MAX_ATTEMPTS,
    check_otp_rate_limit,
    generate_otp,
    hash_otp,
    normalize_norwegian_phone,
    record_otp_request,
    send_otp_sms,
    verify_otp,
)
from ..ui import render_template

router = APIRouter()

_OTP_SESSION_KEY = "otp_token"
_OTP_PHONE_KEY = "otp_phone"


def _otp_expires_at() -> str:
    return (datetime.now(timezone.utc) + timedelta(seconds=OTP_EXPIRE_SECONDS)).strftime(
        "%Y-%m-%dT%H:%M:%SZ"
    )


@router.get("/", response_class=HTMLResponse)
def index(request: Request):
    user = current_user(request)
    if user:
        return RedirectResponse(first_allowed_path(user) or "/login", status_code=HTTP_303_SEE_OTHER)
    return RedirectResponse("/login", status_code=HTTP_303_SEE_OTHER)


@router.get("/login", response_class=HTMLResponse)
def login_page(request: Request):
    user = current_user(request)
    if user:
        return RedirectResponse(first_allowed_path(user) or "/dashboard", status_code=HTTP_303_SEE_OTHER)
    return render_template(request, "login.html")


@router.post("/login")
async def login(request: Request):
    form = await request.form()
    try:
        enforce_csrf(request, form)
    except HTTPException:
        return render_template(
            request, "login.html", error="Sikkerhetssjekk feilet. Last siden på nytt og prøv igjen."
        )
    email = str(form.get("email") or "").strip().lower()
    password = str(form.get("password") or "")
    try:
        check_login_rate_limit(request, email)
    except HTTPException as exc:
        return render_template(request, "login.html", error=exc.detail)
    user = db.get_user_by_email(email)
    if not user or not verify_password(password, user["password_hash"]):
        record_login_failure(request, email)
        return render_template(request, "login.html", error="Feil e-post eller passord.")
    if not int(user.get("active", 1)):
        record_login_failure(request, email)
        return render_template(request, "login.html", error="Brukeren er deaktivert av admin.")
    landing = first_allowed_path(user)
    if not landing:
        return render_template(
            request, "login.html", error="Brukeren har ingen aktive moduler. Kontakt admin."
        )
    if password_needs_rehash(user["password_hash"]):
        db.set_user_password(int(user["id"]), hash_password(password))
    clear_login_failures(request, email)
    issue_authenticated_session(request, int(user["id"]))
    db.record_audit(user["id"], "login", "user", user["id"], {"email": user["email"], "method": "password"})
    return RedirectResponse(landing, status_code=HTTP_303_SEE_OTHER)


@router.get("/login/telefon", response_class=HTMLResponse)
def phone_login_page(request: Request):
    user = current_user(request)
    if user:
        return RedirectResponse(first_allowed_path(user) or "/dashboard", status_code=HTTP_303_SEE_OTHER)
    return render_template(request, "login_phone.html")


@router.post("/login/telefon")
async def phone_login_request(request: Request):
    form = await request.form()
    try:
        enforce_csrf(request, form)
    except HTTPException:
        return render_template(
            request, "login_phone.html",
            error="Sikkerhetssjekk feilet. Last siden på nytt og prøv igjen.",
        )

    raw_phone = str(form.get("phone") or "").strip()
    phone = normalize_norwegian_phone(raw_phone)
    if not phone:
        return render_template(
            request, "login_phone.html",
            error="Ugyldig mobilnummer. Bruk norsk mobilnummer (8 siffer, starter med 4 eller 9).",
        )

    if not check_otp_rate_limit(phone):
        return render_template(
            request, "login_phone.html",
            error="For mange kodeforespørsler for dette nummeret. Vent 15 minutter og prøv igjen.",
        )

    user = db.get_user_by_phone(phone)

    if user and int(user.get("active", 1)):
        code = generate_otp()
        code_hash = hash_otp(code)
        token = secrets.token_urlsafe(32)
        db.create_otp_session(phone, token, code_hash, _otp_expires_at())
        record_otp_request(phone)
        sent = send_otp_sms(phone, code)
        if not sent:
            return render_template(
                request, "login_phone.html",
                error="Kunne ikke sende SMS akkurat nå. Prøv igjen eller bruk e-post og passord.",
            )
        request.session[_OTP_SESSION_KEY] = token
        request.session[_OTP_PHONE_KEY] = phone
    else:
        record_otp_request(phone)

    return RedirectResponse("/login/kode", status_code=HTTP_303_SEE_OTHER)


@router.get("/login/kode", response_class=HTMLResponse)
def otp_page(request: Request):
    user = current_user(request)
    if user:
        return RedirectResponse(first_allowed_path(user) or "/dashboard", status_code=HTTP_303_SEE_OTHER)
    token = request.session.get(_OTP_SESSION_KEY)
    if not token:
        return RedirectResponse("/login/telefon", status_code=HTTP_303_SEE_OTHER)
    phone = str(request.session.get(_OTP_PHONE_KEY) or "")
    masked = f"+47 ****{phone[-4:]}" if len(phone) >= 4 else "ditt nummer"
    return render_template(request, "login_otp.html", masked_phone=masked)


@router.post("/login/kode")
async def otp_verify(request: Request):
    form = await request.form()
    try:
        enforce_csrf(request, form)
    except HTTPException:
        return render_template(
            request, "login_otp.html", error="Sikkerhetssjekk feilet. Last siden på nytt.", masked_phone=""
        )

    token = request.session.get(_OTP_SESSION_KEY)
    phone = str(request.session.get(_OTP_PHONE_KEY) or "")
    if not token:
        return RedirectResponse("/login/telefon", status_code=HTTP_303_SEE_OTHER)

    masked = f"+47 ****{phone[-4:]}" if len(phone) >= 4 else "ditt nummer"
    code = "".join(ch for ch in str(form.get("code") or "") if ch.isdigit())

    session_row = db.get_otp_session(token)
    if not session_row:
        request.session.pop(_OTP_SESSION_KEY, None)
        request.session.pop(_OTP_PHONE_KEY, None)
        return render_template(
            request, "login_otp.html",
            error="Koden er utløpt eller allerede brukt. Start innlogging på nytt.",
            masked_phone=masked, expired=True,
        )

    expires_at_str = str(session_row.get("expires_at") or "")
    try:
        from datetime import timezone as tz
        expires_dt = datetime.strptime(expires_at_str, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=tz.utc)
        if datetime.now(tz.utc) > expires_dt:
            request.session.pop(_OTP_SESSION_KEY, None)
            request.session.pop(_OTP_PHONE_KEY, None)
            return render_template(
                request, "login_otp.html",
                error="Koden er utløpt. Start innlogging på nytt.",
                masked_phone=masked, expired=True,
            )
    except Exception:
        pass

    attempts = int(session_row.get("attempts", 0))
    if attempts >= OTP_MAX_ATTEMPTS:
        request.session.pop(_OTP_SESSION_KEY, None)
        request.session.pop(_OTP_PHONE_KEY, None)
        return render_template(
            request, "login_otp.html",
            error="For mange feil forsøk. Start innlogging på nytt.",
            masked_phone=masked, expired=True,
        )

    if not verify_otp(code, str(session_row.get("code_hash") or "")):
        new_attempts = db.increment_otp_attempts(int(session_row["id"]))
        remaining = max(0, OTP_MAX_ATTEMPTS - new_attempts)
        msg = f"Feil kode. {remaining} forsøk gjenstår." if remaining else "Feil kode. Ingen forsøk gjenstår – start på nytt."
        return render_template(request, "login_otp.html", error=msg, masked_phone=masked)

    db.mark_otp_used(int(session_row["id"]))
    request.session.pop(_OTP_SESSION_KEY, None)
    request.session.pop(_OTP_PHONE_KEY, None)

    user = db.get_user_by_phone(phone)
    if not user or not int(user.get("active", 1)):
        return render_template(
            request, "login_otp.html", error="Fant ingen aktiv bruker for dette nummeret.", masked_phone=masked
        )

    landing = first_allowed_path(user)
    if not landing:
        return render_template(
            request, "login_otp.html",
            error="Brukeren har ingen aktive moduler. Kontakt admin.",
            masked_phone=masked,
        )

    issue_authenticated_session(request, int(user["id"]))
    db.record_audit(user["id"], "login", "user", user["id"], {"phone_masked": masked, "method": "otp_sms"})

    try:
        db.purge_expired_otp_sessions()
    except Exception:
        pass

    return RedirectResponse(landing, status_code=HTTP_303_SEE_OTHER)


@router.post("/logout")
def logout(request: Request):
    try:
        enforce_csrf(request)
    except HTTPException:
        request.session.clear()
        return RedirectResponse("/login", status_code=HTTP_303_SEE_OTHER)
    user = current_user(request)
    if user:
        db.record_audit(user["id"], "logout", "user", user["id"], {"email": user["email"]})
    request.session.clear()
    return RedirectResponse("/login", status_code=HTTP_303_SEE_OTHER)
