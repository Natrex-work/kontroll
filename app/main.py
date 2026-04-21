from __future__ import annotations

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
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
