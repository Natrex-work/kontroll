from __future__ import annotations

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware

from .config import settings
from .logging_setup import configure_logging
from .routers import admin, api, auth, cases, pages
from .services.bootstrap_service import initialize_application_data, seed_default_users, seed_demo_cases_if_empty

configure_logging(settings.log_level)
settings.ensure_runtime_dirs()


def create_app() -> FastAPI:
    app = FastAPI(title=settings.app_name, version=settings.app_version)
    app.add_middleware(SessionMiddleware, secret_key=settings.session_secret, same_site=settings.session_same_site, https_only=settings.session_https_only)
    app.mount('/static', StaticFiles(directory=str(settings.static_dir)), name='static')
    app.mount('/uploads', StaticFiles(directory=str(settings.upload_dir)), name='uploads')
    app.mount('/generated', StaticFiles(directory=str(settings.generated_dir)), name='generated')

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

__all__ = ['app', 'create_app', 'seed_default_users', 'seed_demo_cases_if_empty']
