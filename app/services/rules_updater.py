from __future__ import annotations

import asyncio
import json
import logging
import os
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from .. import rules
from ..config import settings
from . import rules_service

logger = logging.getLogger(__name__)

CACHE_PATH = getattr(settings, 'data_dir', settings.base_dir / 'data') / 'cache' / 'control_rules_refresh.json'
UPDATE_TIME = os.getenv('KV_RULE_UPDATE_TIME', '23:30')
ENABLED = os.getenv('KV_RULE_UPDATE_ENABLED', '1').lower() in {'1', 'true', 'yes', 'on'}
TZ = ZoneInfo(os.getenv('KV_RULE_UPDATE_TZ', 'Europe/Oslo'))

DEFAULT_PROFILES: tuple[tuple[str, str, str], ...] = (
    ('fritidsfiske', 'hummer', 'teine'),
    ('fritidsfiske', 'hummer', 'samleteine / sanketeine'),
    ('fritidsfiske', 'taskekrabbe', 'teine'),
    ('fritidsfiske', 'torsk', 'garn'),
    ('fritidsfiske', 'torsk', 'ruse'),
    ('fritidsfiske', 'sjøørret', 'fiskestang'),
    ('kommersiell', 'torsk', 'garn'),
    ('kommersiell', 'torsk', 'trål'),
    ('kommersiell', 'reke', 'trål'),
)

_started = False


def _next_run(now: datetime | None = None) -> datetime:
    now = now or datetime.now(TZ)
    try:
        hour, minute = [int(part) for part in UPDATE_TIME.split(':', 1)]
    except Exception:
        hour, minute = 23, 30
    candidate = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
    if candidate <= now:
        candidate += timedelta(days=1)
    return candidate


def refresh_control_rules_cache() -> dict[str, object]:
    CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
    refreshed_at = datetime.now(TZ).isoformat(timespec='seconds')
    profiles: dict[str, object] = {}
    errors: list[str] = []
    for control_type, species, gear_type in DEFAULT_PROFILES:
        key = f'{control_type}:{species}:{gear_type}'
        try:
            bundle = rules_service.get_rule_bundle_with_live_sources(control_type=control_type, species=species, gear_type=gear_type)
            profiles[key] = {
                'title': bundle.get('title') or '',
                'description': bundle.get('description') or '',
                'sources': bundle.get('sources') or [],
                'items': bundle.get('items') or [],
            }
        except Exception as exc:  # pragma: no cover - network/runtime dependent
            errors.append(f'{key}: {exc}')
            try:
                fallback = rules.get_rule_bundle(control_type, species, gear_type)
                profiles[key] = {
                    'title': fallback.get('title') or '',
                    'description': fallback.get('description') or '',
                    'sources': fallback.get('sources') or [],
                    'items': fallback.get('items') or [],
                    'fallback': True,
                }
            except Exception as inner:
                errors.append(f'{key} fallback: {inner}')
    payload = {'refreshed_at': refreshed_at, 'update_time': UPDATE_TIME, 'profiles': profiles, 'errors': errors}
    tmp = CACHE_PATH.with_suffix('.tmp')
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding='utf-8')
    tmp.replace(CACHE_PATH)
    return payload


async def _rule_refresh_loop() -> None:
    while True:
        target = _next_run()
        await asyncio.sleep(max(1.0, (target - datetime.now(TZ)).total_seconds()))
        try:
            await asyncio.to_thread(refresh_control_rules_cache)
            logger.info('Oppdatert kontrollpunkt-/regelcache kl. %s.', UPDATE_TIME)
        except Exception as exc:  # pragma: no cover
            logger.warning('Kunne ikke oppdatere kontrollpunkt-/regelcache: %s', exc)


def start_background_rule_refresh() -> None:
    global _started
    if _started or not ENABLED:
        return
    _started = True
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        return
    loop.create_task(_rule_refresh_loop())
