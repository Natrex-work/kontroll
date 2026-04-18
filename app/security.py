from __future__ import annotations

import base64
import hashlib
import secrets
import time
from collections import defaultdict, deque
from typing import Awaitable, Callable

from cryptography.fernet import Fernet, InvalidToken
from fastapi import HTTPException, Request
from fastapi.responses import JSONResponse, PlainTextResponse
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response

from .config import settings

ENCRYPTION_PREFIX = 'enc::'
SAFE_METHODS = {'GET', 'HEAD', 'OPTIONS', 'TRACE'}


class CryptoService:
    def __init__(self, secret_seed: str, explicit_key: str = '') -> None:
        raw_key = (explicit_key or '').strip() or secret_seed
        if not raw_key:
            raw_key = 'kv-fallback-development-key'
        self._fernet = Fernet(self._normalize_key(raw_key))

    @staticmethod
    def _normalize_key(value: str) -> bytes:
        raw = value.strip().encode('utf-8')
        try:
            decoded = base64.urlsafe_b64decode(raw)
            if len(decoded) == 32:
                return raw
        except Exception:
            pass
        digest = hashlib.sha256(raw).digest()
        return base64.urlsafe_b64encode(digest)

    def encrypt_text(self, value: str | None) -> str | None:
        if value is None:
            return None
        text = str(value)
        if not text:
            return text
        if text.startswith(ENCRYPTION_PREFIX):
            return text
        token = self._fernet.encrypt(text.encode('utf-8')).decode('utf-8')
        return ENCRYPTION_PREFIX + token

    def decrypt_text(self, value: str | None) -> str | None:
        if value is None:
            return None
        text = str(value)
        if not text:
            return text
        if not text.startswith(ENCRYPTION_PREFIX):
            return text
        token = text[len(ENCRYPTION_PREFIX):]
        try:
            return self._fernet.decrypt(token.encode('utf-8')).decode('utf-8')
        except InvalidToken:
            return text


crypto_service = CryptoService(settings.session_secret, settings.data_encryption_key)


def encrypt_text(value: str | None) -> str | None:
    return crypto_service.encrypt_text(value)


def decrypt_text(value: str | None) -> str | None:
    return crypto_service.decrypt_text(value)


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: Callable[[Request], Awaitable[Response]]) -> Response:
        response = await call_next(request)
        response.headers.setdefault('X-Frame-Options', 'DENY')
        response.headers.setdefault('X-Content-Type-Options', 'nosniff')
        response.headers.setdefault('Referrer-Policy', 'no-referrer')
        response.headers.setdefault('Permissions-Policy', 'camera=(self), geolocation=(self), microphone=(self)')
        response.headers.setdefault('Cross-Origin-Opener-Policy', 'same-origin')
        response.headers.setdefault('Cross-Origin-Resource-Policy', 'same-origin')
        response.headers.setdefault('Content-Security-Policy', (
            "default-src 'self'; "
            "script-src 'self' https://unpkg.com; "
            "style-src 'self' 'unsafe-inline' https://unpkg.com; "
            "img-src 'self' data: blob: https://tile.openstreetmap.org https://*.tile.openstreetmap.org; "
            "media-src 'self' blob:; "
            "font-src 'self' data:; "
            "connect-src 'self' https://gis.fiskeridir.no https://www.fiskeridir.no https://www.1881.no https://www.gulesider.no https://tile.openstreetmap.org https://*.tile.openstreetmap.org; "
            "form-action 'self'; base-uri 'self'; frame-ancestors 'none'"
        ))
        if request.url.scheme == 'https':
            response.headers.setdefault('Strict-Transport-Security', 'max-age=31536000; includeSubDomains')
        if 'text/html' in response.headers.get('content-type', '') or request.url.path.startswith('/api/'):
            response.headers.setdefault('Cache-Control', 'no-store')
            response.headers.setdefault('Pragma', 'no-cache')
        return response


def ensure_csrf_token(request: Request) -> str:
    token = request.session.get('_csrf_token')
    if not token:
        token = secrets.token_urlsafe(32)
        request.session['_csrf_token'] = token
    return str(token)


async def csrf_middleware(request: Request, call_next: Callable[[Request], Awaitable[Response]]) -> Response:
    if not settings.csrf_enabled or request.method in SAFE_METHODS:
        if request.method in SAFE_METHODS and hasattr(request, 'session'):
            ensure_csrf_token(request)
        return await call_next(request)

    if request.url.path.startswith('/static/'):
        return await call_next(request)

    expected = str(request.session.get('_csrf_token') or '')
    if not expected:
        return PlainTextResponse('CSRF-token mangler i økten.', status_code=403)

    provided = request.headers.get('X-CSRF-Token', '')
    if not provided:
        content_type = (request.headers.get('content-type') or '').lower()
        if 'multipart/form-data' in content_type or 'application/x-www-form-urlencoded' in content_type:
            form = await request.form()
            provided = str(form.get('_csrf') or '')

    if not provided or not secrets.compare_digest(expected, provided):
        if request.url.path.startswith('/api/'):
            return JSONResponse({'ok': False, 'detail': 'Ugyldig CSRF-token.'}, status_code=403)
        return PlainTextResponse('Ugyldig CSRF-token.', status_code=403)

    return await call_next(request)


async def verify_csrf(request: Request) -> None:
    if not settings.csrf_enabled:
        return
    expected = str(request.session.get('_csrf_token') or '')
    if not expected:
        raise HTTPException(status_code=403, detail='CSRF-token mangler i økten.')
    provided = request.headers.get('X-CSRF-Token', '')
    if not provided:
        content_type = (request.headers.get('content-type') or '').lower()
        if 'multipart/form-data' in content_type or 'application/x-www-form-urlencoded' in content_type:
            form = await request.form()
            provided = str(form.get('_csrf') or '')
    if not provided or not secrets.compare_digest(expected, provided):
        raise HTTPException(status_code=403, detail='Ugyldig CSRF-token.')


class LoginAttemptLimiter:
    def __init__(self, *, max_attempts: int = 8, window_seconds: int = 900) -> None:
        self.max_attempts = max_attempts
        self.window_seconds = window_seconds
        self._attempts: dict[str, deque[float]] = defaultdict(deque)

    def _trim(self, key: str) -> deque[float]:
        bucket = self._attempts[key]
        now = time.time()
        while bucket and now - bucket[0] > self.window_seconds:
            bucket.popleft()
        if not bucket:
            self._attempts.pop(key, None)
            return deque()
        return bucket

    def is_blocked(self, key: str) -> bool:
        bucket = self._trim(key)
        return len(bucket) >= self.max_attempts

    def add_failure(self, key: str) -> None:
        bucket = self._trim(key)
        bucket.append(time.time())
        self._attempts[key] = bucket

    def clear(self, key: str) -> None:
        self._attempts.pop(key, None)


login_attempt_limiter = LoginAttemptLimiter()
