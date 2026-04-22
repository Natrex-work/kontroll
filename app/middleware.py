from __future__ import annotations

from fnmatch import fnmatch

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import PlainTextResponse, Response

from .config import settings
from .security import effective_scheme


class AllowedHostsMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, allowed_hosts: tuple[str, ...] | list[str] | None = None, exempt_paths: tuple[str, ...] | list[str] | None = None):
        super().__init__(app)
        self.allowed_hosts = [str(item).strip().lower() for item in list(allowed_hosts or []) if str(item).strip()]
        self.exempt_paths = tuple(str(item).strip() for item in list(exempt_paths or []) if str(item).strip())

    @staticmethod
    def _normalize_host(raw_host: str | None) -> str:
        value = str(raw_host or '').strip().lower()
        if not value:
            return ''
        if value.startswith('['):
            return value.split(']', 1)[0].lstrip('[')
        return value.split(':', 1)[0]

    def _is_allowed(self, host: str) -> bool:
        if not self.allowed_hosts or '*' in self.allowed_hosts:
            return True
        return any(fnmatch(host, pattern) for pattern in self.allowed_hosts)

    async def dispatch(self, request: Request, call_next):
        if self.exempt_paths and request.url.path in self.exempt_paths:
            return await call_next(request)
        host = self._normalize_host(request.headers.get('host'))
        if not host:
            return PlainTextResponse('Ugyldig Host-header.', status_code=400)
        if not self._is_allowed(host):
            return PlainTextResponse('Host ikke tillatt.', status_code=400)
        return await call_next(request)


class BodySizeLimitMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        if request.method in {'POST', 'PUT', 'PATCH'}:
            raw_length = str(request.headers.get('content-length') or '').strip()
            if raw_length:
                try:
                    content_length = int(raw_length)
                except ValueError:
                    content_length = 0
                if content_length > settings.max_request_size_mb * 1024 * 1024:
                    return PlainTextResponse('Forespørselen er for stor.', status_code=413)
        return await call_next(request)


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    def _csp(self) -> str:
        return '; '.join(
            [
                "default-src 'self'",
                "base-uri 'self'",
                "object-src 'none'",
                "frame-ancestors 'none'",
                "form-action 'self'",
                "manifest-src 'self'",
                "script-src 'self' https://unpkg.com https://cdn.jsdelivr.net",
                "style-src 'self' 'unsafe-inline' https://unpkg.com",
                "img-src 'self' data: blob: https://tile.openstreetmap.org https://*.tile.openstreetmap.org https://gis.fiskeridir.no https://portal.fiskeridir.no",
                "font-src 'self' data:",
                "connect-src 'self' https://cdn.jsdelivr.net https://gis.fiskeridir.no https://portal.fiskeridir.no",
                "media-src 'self' blob:",
                "worker-src 'self' blob:",
                'upgrade-insecure-requests',
            ]
        )

    async def dispatch(self, request: Request, call_next):
        response: Response = await call_next(request)
        response.headers.setdefault('Content-Security-Policy', self._csp())
        response.headers.setdefault('Referrer-Policy', 'strict-origin-when-cross-origin')
        response.headers.setdefault('X-Content-Type-Options', 'nosniff')
        response.headers.setdefault('X-Frame-Options', 'DENY')
        response.headers.setdefault('Permissions-Policy', 'geolocation=(self), camera=(self), microphone=(self), fullscreen=(self)')
        response.headers.setdefault('Cross-Origin-Opener-Policy', 'same-origin')
        response.headers.setdefault('Cross-Origin-Resource-Policy', 'same-origin')
        if effective_scheme(request) == 'https':
            response.headers.setdefault('Strict-Transport-Security', 'max-age=63072000; includeSubDomains; preload')
        if not request.url.path.startswith('/static/'):
            response.headers.setdefault('Cache-Control', 'no-store')
            response.headers.setdefault('Pragma', 'no-cache')
        return response
