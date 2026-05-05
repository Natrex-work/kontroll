from __future__ import annotations

from typing import Any

from fastapi import Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from . import area, catalog, db, live_sources
from .config import settings
from .dependencies import current_user, first_allowed_path, has_permission, user_permissions
from .pdf_export import CASE_BASIS_LABELS
from .security import ensure_csrf_token

templates = Jinja2Templates(directory=str(settings.templates_dir))

CONTROL_TYPES = catalog.control_labels()
FISHERY_TYPES = catalog.species_suggestions()
GEAR_TYPES = sorted({gear for label in CONTROL_TYPES for gear in catalog.regulated_gears(label)})
SPECIES_SUGGESTIONS = catalog.species_suggestions()
STATUS_OPTIONS = ['Utkast', 'Anmeldt', 'Anmeldt og sendt', 'Ingen reaksjon', 'Advarsel']
USER_ROLE_OPTIONS = ['investigator', 'admin']
INVESTIGATOR_PERMISSION_OPTIONS = [
    {'value': 'kv_kontroll', 'label': db.USER_PERMISSION_LABELS['kv_kontroll']},
    {'value': 'kart', 'label': db.USER_PERMISSION_LABELS['kart']},
    {'value': 'regelverk', 'label': db.USER_PERMISSION_LABELS['regelverk']},
]
ADMIN_PERMISSION_OPTIONS = [
    {'value': 'user_admin', 'label': db.USER_PERMISSION_LABELS['user_admin']},
    {'value': 'control_admin', 'label': db.USER_PERMISSION_LABELS['control_admin']},
]
EXTERNAL_ACTOR_OPTIONS = catalog.EXTERNAL_ACTORS
CREW_ROLE_OPTIONS = catalog.CREW_ROLES
CASE_BASIS_OPTIONS = [
    {'value': 'patruljeobservasjon', 'label': CASE_BASIS_LABELS['patruljeobservasjon']},
    {'value': 'tips', 'label': CASE_BASIS_LABELS['tips']},
]


def visible_app_name(name: str | None) -> str:
    raw = (name or '').strip()
    if not raw:
        return 'Kontroll'
    if raw.lower().startswith('kv '):
        trimmed = raw[3:].strip()
        return trimmed or 'Kontroll'
    if raw.lower() == 'kv':
        return 'Kontroll'
    return raw


def visible_brand_org_name(name: str | None) -> str:
    raw = (name or '').strip()
    if not raw:
        return 'Minfiskerikontroll'
    lowered = raw.lower()
    if lowered.startswith('fiskeridirektoratet'):
        return 'Minfiskerikontroll'
    return raw


VISIBLE_APP_NAME = visible_app_name(settings.app_name)
VISIBLE_BRAND_ORG_NAME = visible_brand_org_name(settings.brand_org_name)


def build_nav_links(user: dict[str, Any] | None) -> list[dict[str, str]]:
    if not user:
        return []
    links: list[dict[str, str]] = []
    if has_permission(user, 'kv_kontroll'):
        links.extend([
            {'href': '/dashboard', 'label': 'Hjem', 'dock_label': 'Hjem', 'icon': '⌂', 'method': 'get', 'key': 'home'},
            {'href': '/cases/new', 'label': 'Ny kontroll', 'dock_label': 'Ny', 'icon': '➕', 'method': 'post', 'key': 'new_case'},
            {'href': '/kontroller', 'label': 'Kontroller og historikk', 'dock_label': 'Saker', 'icon': '🗂', 'method': 'get', 'key': 'history'},
        ])
    if has_permission(user, 'kart'):
        links.append({'href': '/kart', 'label': 'Kart og områder', 'dock_label': 'Kart', 'icon': '🗺', 'method': 'get', 'key': 'map'})
    if has_permission(user, 'regelverk'):
        links.append({'href': '/regelverk', 'label': 'Regelverk', 'dock_label': 'Regler', 'icon': '📘', 'method': 'get', 'key': 'rules'})
    if has_permission(user, 'user_admin'):
        links.append({'href': '/admin/users', 'label': 'Brukere', 'dock_label': 'Brukere', 'icon': '👤', 'method': 'get', 'key': 'users'})
    if has_permission(user, 'control_admin'):
        links.append({'href': '/admin/controls', 'label': 'Kontroller', 'dock_label': 'Admin', 'icon': '♻', 'method': 'get', 'key': 'admin_controls'})
    return links


MOBILE_NAV_ORDER = ('home', 'new_case', 'map', 'rules', 'history')


def build_mobile_nav_links(nav_links: list[dict[str, str]]) -> list[dict[str, str]]:
    by_key = {str(link.get('key')): link for link in nav_links}
    mobile_links: list[dict[str, str]] = []
    for key in MOBILE_NAV_ORDER:
        link = by_key.get(key)
        if link:
            mobile_links.append(link)
    return mobile_links


def render_template(request: Request, name: str, **context: Any) -> HTMLResponse:
    user = current_user(request)
    nav_links = build_nav_links(user)
    base_context = {
        'request': request,
        'current_user': user,
        'current_permissions': user_permissions(user),
        'nav_links': nav_links,
        'mobile_nav_links': build_mobile_nav_links(nav_links),
        'default_home_path': first_allowed_path(user) or '/login',
        'can_case_admin': has_permission(user, 'control_admin'),
        'control_types': CONTROL_TYPES,
        'fishery_types': FISHERY_TYPES,
        'gear_types': GEAR_TYPES,
        'species_suggestions': SPECIES_SUGGESTIONS,
        'status_options': STATUS_OPTIONS,
        'user_role_options': USER_ROLE_OPTIONS,
        'investigator_permission_options': INVESTIGATOR_PERMISSION_OPTIONS,
        'admin_permission_options': ADMIN_PERMISSION_OPTIONS,
        'permission_labels': db.USER_PERMISSION_LABELS,
        'case_basis_options': CASE_BASIS_OPTIONS,
        'live_enabled': live_sources.LIVE_ENABLED,
        'external_actor_options': EXTERNAL_ACTOR_OPTIONS,
        'crew_role_options': CREW_ROLE_OPTIONS,
        'portal_map_url': live_sources.MAP_PORTAL_URL,
        'portal_mapserver_url': live_sources.YGG_BASE,
        'portal_vern_mapserver_url': getattr(live_sources, 'VERN_BASE', 'https://portal.fiskeridir.no/server/rest/services/Fiskeridir_vern/MapServer'),
        'portal_layers': context.get('portal_layers', []),
        'dashboard_zones': area.ZONES,
        'app_version': settings.app_version_label,
        'app_name': settings.app_name,
        'display_app_name': VISIBLE_APP_NAME,
        'brand_org_name': VISIBLE_BRAND_ORG_NAME,
        'csrf_token': ensure_csrf_token(request),
        'server_url': settings.server_url,
        'production_mode': settings.production_mode,
    }
    base_context.update(context)
    return templates.TemplateResponse(request, name, base_context)
