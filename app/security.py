from __future__ import annotations

import hmac
import secrets
import threading
import time
from collections import defaultdict, deque
from typing import Any
from urllib.parse import urlparse

from fastapi import HTTPException, Request

from . import db
from .config import settings
from .logging_setup import get_logger

logger = get_logger(__name__)

CSRF_SESSION_KEY = 'csrf_token'
AUTH_AT_SESSION_KEY = 'auth_at'
LAST_SEEN_SESSION_KEY = 'last_seen'
SESSION_NONCE_KEY = 'session_nonce'

_rate_lock = threading.Lock()
_login_attempts: dict[str, deque[float]] = defaultdict(deque)
_otp_send_attempts: dict[str, deque[float]] = defaultdict(deque)


def client_ip(request: Request) -> str:
    forwarded_for = str(request.headers.get('x-forwarded-for') or '').split(',')[0].strip()
    if forwarded_for:
        return forwarded_for
    if request.client and request.client.host:
        return request.client.host
    return 'unknown'


def effective_scheme(request: Request) -> str:
    forwarded_proto = str(request.headers.get('x-forwarded-proto') or '').strip().lower()
    if forwarded_proto in {'http', 'https'}:
        return forwarded_proto
    return request.url.scheme


def effective_host(request: Request) -> str:
    forwarded_host = str(request.headers.get('x-forwarded-host') or '').strip()
    if forwarded_host:
        return forwarded_host
    host = str(request.headers.get('host') or '').strip()
    if host:
        return host
    return request.url.netloc


def effective_origin(request: Request) -> str:
    return f'{effective_scheme(request)}://{effective_host(request)}'


def ensure_csrf_token(request: Request) -> str:
    token = str(request.session.get(CSRF_SESSION_KEY) or '').strip()
    if len(token) < 32:
        token = secrets.token_urlsafe(32)
        request.session[CSRF_SESSION_KEY] = token
    return token


def rotate_csrf_token(request: Request) -> str:
    token = secrets.token_urlsafe(32)
    request.session[CSRF_SESSION_KEY] = token
    return token


def _same_origin(header_value: str, request: Request) -> bool:
    if not header_value:
        return False
    try:
        parsed = urlparse(header_value)
    except Exception:
        return False
    if not parsed.scheme or not parsed.netloc:
        return False
    return f'{parsed.scheme}://{parsed.netloc}' == effective_origin(request)


def validate_same_origin(request: Request) -> None:
    origin = str(request.headers.get('origin') or '').strip()
    referer = str(request.headers.get('referer') or '').strip()
    if origin and not _same_origin(origin, request):
        raise HTTPException(status_code=403, detail='Sikkerhetssjekk feilet for forespørselen.')
    if not origin and referer and not _same_origin(referer, request):
        raise HTTPException(status_code=403, detail='Sikkerhetssjekk feilet for forespørselen.')


def enforce_csrf(request: Request, form: Any | None = None) -> None:
    validate_same_origin(request)
    expected = ensure_csrf_token(request)
    provided = str(request.headers.get('x-csrf-token') or '').strip()
    if not provided and form is not None:
        try:
            provided = str(form.get('csrf_token') or '').strip()
        except Exception:
            provided = ''
    if not provided or not hmac.compare_digest(provided, expected):
        audit_security_event('csrf_rejected', request, {'path': request.url.path})
        raise HTTPException(status_code=403, detail='Sikkerhetssjekk feilet. Last siden på nytt og prøv igjen.')


def issue_authenticated_session(request: Request, user_id: int) -> None:
    now = int(time.time())
    request.session.clear()
    request.session['user_id'] = int(user_id)
    request.session[AUTH_AT_SESSION_KEY] = now
    request.session[LAST_SEEN_SESSION_KEY] = now
    request.session[SESSION_NONCE_KEY] = secrets.token_urlsafe(16)
    request.session[CSRF_SESSION_KEY] = secrets.token_urlsafe(32)


def _expired(session: dict[str, Any]) -> bool:
    now = int(time.time())
    auth_at = int(session.get(AUTH_AT_SESSION_KEY) or 0)
    last_seen = int(session.get(LAST_SEEN_SESSION_KEY) or auth_at or 0)
    if auth_at and settings.session_absolute_minutes > 0 and (now - auth_at) > settings.session_absolute_minutes * 60:
        return True
    if last_seen and settings.session_idle_minutes > 0 and (now - last_seen) > settings.session_idle_minutes * 60:
        return True
    return False


def touch_authenticated_session(request: Request) -> bool:
    if not request.session.get('user_id'):
        return False
    if _expired(request.session):
        request.session.clear()
        return False
    request.session[LAST_SEEN_SESSION_KEY] = int(time.time())
    if not request.session.get(CSRF_SESSION_KEY):
        request.session[CSRF_SESSION_KEY] = secrets.token_urlsafe(32)
    return True


def _prune_attempts(queue: deque[float], *, window_seconds: int) -> None:
    cutoff = time.time() - window_seconds
    while queue and queue[0] < cutoff:
        queue.popleft()


def check_login_rate_limit(request: Request, email: str) -> None:
    key = f'{client_ip(request)}|{str(email or "").strip().lower()}'
    with _rate_lock:
        queue = _login_attempts[key]
        _prune_attempts(queue, window_seconds=settings.login_rate_limit_window_seconds)
        if len(queue) >= settings.login_rate_limit_attempts:
            audit_security_event('login_rate_limited', request, {'email': str(email or '').strip().lower()})
            raise HTTPException(status_code=429, detail='For mange innloggingsforsøk. Vent litt og prøv igjen.')


def record_login_failure(request: Request, email: str) -> None:
    normalized = str(email or '').strip().lower()
    key = f'{client_ip(request)}|{normalized}'
    with _rate_lock:
        queue = _login_attempts[key]
        queue.append(time.time())
        _prune_attempts(queue, window_seconds=settings.login_rate_limit_window_seconds)
    audit_security_event('failed_login', request, {'email': normalized})


def clear_login_failures(request: Request, email: str) -> None:
    key = f'{client_ip(request)}|{str(email or "").strip().lower()}'
    with _rate_lock:
        _login_attempts.pop(key, None)



def check_otp_send_rate_limit(request: Request, user_id: int) -> None:
    key = f'{client_ip(request)}|otp|{int(user_id)}'
    with _rate_lock:
        queue = _otp_send_attempts[key]
        _prune_attempts(queue, window_seconds=settings.otp_send_rate_limit_window_seconds)
        if len(queue) >= settings.otp_send_rate_limit_attempts:
            audit_security_event('otp_send_rate_limited', request, {'user_id': int(user_id)})
            raise HTTPException(status_code=429, detail='For mange kodeutsendinger. Vent litt og prøv igjen.')


def record_otp_send_attempt(request: Request, user_id: int) -> None:
    key = f'{client_ip(request)}|otp|{int(user_id)}'
    with _rate_lock:
        queue = _otp_send_attempts[key]
        queue.append(time.time())
        _prune_attempts(queue, window_seconds=settings.otp_send_rate_limit_window_seconds)


def audit_security_event(action: str, request: Request, details: dict[str, Any] | None = None) -> None:
    payload = dict(details or {})
    payload.setdefault('ip', client_ip(request))
    payload.setdefault('path', request.url.path)
    payload.setdefault('host', effective_host(request))
    try:
        db.record_audit(None, action, 'security', None, payload)
    except Exception:
        logger.warning('Kunne ikke skrive sikkerhetshendelse %s', action)
