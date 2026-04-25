from __future__ import annotations

from fastapi import FastAPI, HTTPException, Request
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, JSONResponse, Response
from starlette.middleware.sessions import SessionMiddleware
from starlette.middleware.trustedhost import TrustedHostMiddleware

from .config import settings
from .logging_setup import configure_logging
from .middleware import BodySizeLimitMiddleware, SecurityHeadersMiddleware
from .routers import admin, api, auth, cases, pages
from .services.bootstrap_service import ensure_bootstrap_admin, initialize_application_data

configure_logging(settings.log_level)
settings.ensure_runtime_dirs()


def create_app() -> FastAPI:
    app = FastAPI(
        title=settings.app_name,
        version=settings.app_version,
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
    )
    if settings.allowed_hosts and '*' not in settings.allowed_hosts:
        app.add_middleware(TrustedHostMiddleware, allowed_hosts=list(settings.allowed_hosts))
    app.add_middleware(BodySizeLimitMiddleware)
    app.add_middleware(
        SessionMiddleware,
        secret_key=settings.session_secret,
        same_site=settings.session_same_site,
        https_only=settings.session_https_only,
        max_age=settings.session_max_age_seconds,
        session_cookie='kv_session',
    )
    app.add_middleware(SecurityHeadersMiddleware)
    app.mount('/static', StaticFiles(directory=str(settings.static_dir)), name='static')

    @app.on_event('startup')
    def startup() -> None:
        initialize_application_data()

    @app.exception_handler(HTTPException)
    async def friendly_http_exception(request: Request, exc: HTTPException):
        detail = exc.detail
        detail_text = str(detail or '')
        accept = str(request.headers.get('accept') or '')
        wants_html = request.method in {'GET', 'HEAD'} and ('text/html' in accept or '*/*' in accept or not accept)
        if exc.status_code == 404 and detail_text.startswith('Fant ikke saken') and wants_html:
            html = '<!doctype html><html lang="nb"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Saken ble ikke funnet</title><style>body{font-family:system-ui,-apple-system,BlinkMacSystemFont,Segoe UI,sans-serif;background:#eef4f8;color:#10273d;margin:0;padding:24px}.card{max-width:720px;margin:10vh auto;background:#fff;border:1px solid #d7e3ee;border-radius:22px;padding:24px;box-shadow:0 18px 42px rgba(16,39,61,.12)}a{display:inline-flex;margin-top:14px;padding:12px 16px;border-radius:999px;background:#123b5d;color:#fff;text-decoration:none;font-weight:700}.muted{color:#5f7186;line-height:1.45}</style></head><body><main class="card"><h1>Saken ble ikke funnet</h1><p class="muted">Saken finnes ikke på serveren. Dette skjer oftest etter deploy/restart hvis databasen ikke ligger på persistent lagring, eller hvis en lokal kladd ikke ble synket.</p><p class="muted">Gå tilbake til kontrolloversikten og opprett/åpne saken på nytt. Nye versjoner forsøker å lagre og synke før forhåndsvisning og eksport.</p><a href="/dashboard">Til kontrolloversikten</a></main></body></html>'
            return HTMLResponse(html, status_code=404)
        return JSONResponse({'detail': detail}, status_code=exc.status_code, headers=getattr(exc, 'headers', None))

    @app.head('/')
    def root_head() -> Response:
        return Response(status_code=200)

    @app.head('/healthz')
    def healthz_head() -> Response:
        return Response(status_code=200)

    @app.get('/healthz')
    def healthz() -> dict[str, str]:
        return {'status': 'ok'}

    app.include_router(auth.router)
    app.include_router(pages.router)
    app.include_router(admin.router)
    app.include_router(cases.router)
    app.include_router(api.router)
    return app


app = create_app()

__all__ = ['app', 'create_app', 'ensure_bootstrap_admin']
