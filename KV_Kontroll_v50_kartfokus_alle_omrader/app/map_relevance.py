from __future__ import annotations

import re
import unicodedata
from typing import Any


def normalize_text(value: Any) -> str:
    text = unicodedata.normalize('NFKD', str(value or ''))
    text = ''.join(ch for ch in text if not unicodedata.combining(ch))
    text = text.replace('_', ' ').replace('-', ' ').replace('/', ' ')
    text = re.sub(r'\s+', ' ', text).strip().lower()
    return text


FISHERY_ALIASES: dict[str, tuple[str, ...]] = {
    'hummer': ('hummer',),
    'taskekrabbe': ('taskekrabbe',),
    'torsk': ('torsk', 'kysttorsk', 'skrei'),
    'kveite': ('kveite',),
    'laks i sjø': ('laks i sjo', 'laks', 'laksefjord', 'laksefjorder'),
    'sjøørret': ('sjoorret', 'sjøørret', 'sjorret'),
    'makrell': ('makrell',),
    'hyse': ('hyse',),
    'sei': ('sei', 'seinot'),
    'leppefisk': ('leppefisk',),
    'sjøkreps': ('sjokreps', 'sjøkreps'),
    'kongekrabbe': ('kongekrabbe',),
    'snøkrabbe': ('snokrabbe', 'snøkrabbe'),
    'makrellstørje': ('makrellstorje', 'makrellstørje', 'storje'),
    'sild': ('sild', 'nvg sild', 'nvgsild'),
    'nvg-sild': ('nvg sild', 'nvgsild'),
    'reke': ('reke', 'reker'),
    'breiflabb': ('breiflabb',),
    'blåkveite': ('blakveite', 'blåkveite'),
    'lange': ('lange',),
    'brosme': ('brosme',),
    'kolmule': ('kolmule',),
    'øyepål': ('oyepal', 'øyepål'),
    'hestmakrell': ('hestmakrell',),
    'flatøsters': ('flatosters', 'flatøsters'),
    'steinbit': ('steinbit',),
    'tare': ('tare',),
    'korallrev': ('korallrev',),
}

GEAR_ALIASES: dict[str, tuple[str, ...]] = {
    'teine': ('teine', 'teiner'),
    'samleteine / sanketeine': ('samleteine', 'sanketeine'),
    'garn': ('garn',),
    'line': ('line',),
    'ruse': ('ruse',),
    'trål': ('tral', 'trål', 'stormasket tral', 'stormasket trål'),
    'pelagisk trål': ('pelagisk tral', 'pelagisk trål'),
    'snurrevad': ('snurrevad',),
    'not': ('not', 'seinot'),
    'ringnot': ('ringnot',),
    'jukse': ('jukse',),
    'krokredskap': ('krokredskap', 'krokbegrensning', 'krokbegrensning line'),
    'fiskestang': ('fiskestang',),
    'håndsnøre': ('handsnore', 'håndsnøre'),
    'dorg': ('dorg',),
}

CONTROL_ALIASES: dict[str, tuple[str, ...]] = {
    'fritidsfiske': ('fritidsfiske', 'fritids'),
    'kommersiell': ('kommersiell', 'yrkesfiske', 'yrkes'),
}

COMMERCIAL_HINTS = (
    'j melding',
    'tral',
    'trål',
    'pelagisk',
    'ringnot',
    'seinot',
    'snurrevad',
    'stormasket',
    'krokbegrensning',
)

_GENERIC_STATUS_NAME_HINTS = (
    'hostingsforskriften',
    'høstingsforskriften',
    'j melding',
    'j-melding',
    'nullfiske',
    'svalbard',
    'verneomrade',
    'verneområde',
    'bunnhabitat',
    'raet',
    'oslofjorden',
    'fiskeforbud',
    'breivikfjorden',
    'borgundfjorden',
)


# Håndplukkede lagprofiler for å vise bare relevante lag i kontrollkartet.
# Dette gjør kartet raskere og stopper irrelevante lag som Lofotfiske/Henningsvær
# fra å vises i fritidskontroller for hummer i Oslofjorden.
COMMON_GENERAL_LAYERS = {75}
PROFILE_LAYER_GROUPS: dict[str, set[int]] = {
    'fritids_generell': {3, 35, 75, 87, 91},
    'fritids_hummer': {3, 35, 75, 76, 77},
    'fritids_torsk': {3, 35, 75, 82, 83, 85, 94, 91},
    'fritids_flatosters': {3, 35, 73, 75},
    'fritids_leppefisk': {3, 35, 75, 84},
    'fritids_steinbit': {75, 200},
    'fritids_laks': {75, 87},
    'fritids_sjoorret': {75, 87},
    'kommersiell_generell': {75, 78, 88, 89, 90, 91, 92, 139, 140, 32, 33, 74, 95, 96, 97, 25, 26},
    'kommersiell_tral': {75, 78, 88, 89, 90, 91, 139, 140, 25, 26},
    'kommersiell_torsk_hyse_sei': {75, 78, 88, 91, 95, 96, 97, 74, 82, 83, 85, 94},
    'kommersiell_tare': {75, 89, 90, 91},
}


def _canonical_from_aliases(value: Any, aliases: dict[str, tuple[str, ...]]) -> str:
    norm = normalize_text(value)
    if not norm:
        return ''
    for canonical, tokens in aliases.items():
        canonical_norm = normalize_text(canonical)
        if norm == canonical_norm:
            return canonical
        for token in tokens:
            token_norm = normalize_text(token)
            if norm == token_norm:
                return canonical
            if token_norm and token_norm in norm:
                return canonical
    return norm


def normalize_fishery(value: Any) -> str:
    return _canonical_from_aliases(value, FISHERY_ALIASES)


def normalize_gear(value: Any) -> str:
    return _canonical_from_aliases(value, GEAR_ALIASES)


def normalize_control_type(value: Any) -> str:
    norm = normalize_text(value)
    if not norm:
        return ''
    if norm.startswith('kom') or 'yrkes' in norm:
        return 'kommersiell'
    return 'fritidsfiske'


def selection_profile_layer_ids(*, fishery: Any = '', control_type: Any = '', gear_type: Any = '') -> set[int]:
    fishery_sel = normalize_fishery(fishery)
    control_sel = normalize_control_type(control_type)
    gear_sel = normalize_gear(gear_type)

    if control_sel == 'fritidsfiske':
        if fishery_sel == 'hummer':
            return set(PROFILE_LAYER_GROUPS['fritids_hummer'])
        if fishery_sel == 'torsk':
            return set(PROFILE_LAYER_GROUPS['fritids_torsk'])
        if fishery_sel == 'flatøsters':
            return set(PROFILE_LAYER_GROUPS['fritids_flatosters'])
        if fishery_sel == 'leppefisk':
            return set(PROFILE_LAYER_GROUPS['fritids_leppefisk'])
        if fishery_sel == 'steinbit':
            return set(PROFILE_LAYER_GROUPS['fritids_steinbit'])
        if fishery_sel == 'laks i sjø':
            return set(PROFILE_LAYER_GROUPS['fritids_laks'])
        if fishery_sel == 'sjøørret':
            return set(PROFILE_LAYER_GROUPS['fritids_sjoorret'])
        if fishery_sel:
            return set(PROFILE_LAYER_GROUPS['fritids_generell'])
        return set(PROFILE_LAYER_GROUPS['fritids_generell'])

    if control_sel == 'kommersiell':
        if gear_sel in {'trål', 'pelagisk trål'}:
            base = set(PROFILE_LAYER_GROUPS['kommersiell_tral'])
        else:
            base = set(PROFILE_LAYER_GROUPS['kommersiell_generell'])
        if fishery_sel in {'torsk', 'hyse', 'sei'}:
            base |= set(PROFILE_LAYER_GROUPS['kommersiell_torsk_hyse_sei'])
        if fishery_sel == 'tare':
            base |= set(PROFILE_LAYER_GROUPS['kommersiell_tare'])
        return base

    if fishery_sel == 'hummer':
        return set(PROFILE_LAYER_GROUPS['fritids_hummer'])
    if fishery_sel == 'torsk':
        return set(PROFILE_LAYER_GROUPS['fritids_torsk'])
    if fishery_sel == 'flatøsters':
        return set(PROFILE_LAYER_GROUPS['fritids_flatosters'])
    if fishery_sel == 'leppefisk':
        return set(PROFILE_LAYER_GROUPS['fritids_leppefisk'])
    if fishery_sel == 'steinbit':
        return set(PROFILE_LAYER_GROUPS['fritids_steinbit'])
    if fishery_sel == 'laks i sjø':
        return set(PROFILE_LAYER_GROUPS['fritids_laks'])
    if fishery_sel == 'sjøørret':
        return set(PROFILE_LAYER_GROUPS['fritids_sjoorret'])
    return set()


def _find_matching_tags(blob: str, aliases: dict[str, tuple[str, ...]]) -> list[str]:
    tags: list[str] = []
    for canonical, tokens in aliases.items():
        canonical_norm = normalize_text(canonical)
        match = canonical_norm and canonical_norm in blob
        if not match:
            for token in tokens:
                token_norm = normalize_text(token)
                if token_norm and token_norm in blob:
                    match = True
                    break
        if match and canonical not in tags:
            tags.append(canonical)
    return tags


def build_selection_summary(fishery_tags: list[str], gear_tags: list[str], control_tags: list[str], generic: bool) -> str:
    parts: list[str] = []
    if fishery_tags:
        parts.append('Arter/fiskeri: ' + ', '.join(fishery_tags))
    if gear_tags:
        parts.append('Redskap: ' + ', '.join(gear_tags))
    if control_tags:
        parts.append('Kontrolltype: ' + ', '.join(control_tags))
    if generic and not parts:
        return 'Gjelder generelt for flere fiskerier og kontrolltyper.'
    return ' · '.join(parts)


def build_layer_metadata(name: Any, description: Any = '', status: Any = '', geometry_type: Any = '') -> dict[str, Any]:
    blob = normalize_text(' '.join(str(part or '') for part in [name, description, status]))
    fishery_tags = _find_matching_tags(blob, FISHERY_ALIASES)
    gear_tags: list[str] = []

    if 'krokbegrensning' in blob or ' line' in (' ' + blob):
        gear_tags.extend(['line', 'krokredskap'])
    if 'stormasket' in blob or 'tral' in blob or 'trål' in str(name or '').lower():
        gear_tags.extend(['trål', 'pelagisk trål'])
    if 'seinot' in blob:
        gear_tags.extend(['not', 'ringnot'])
    elif 'ringnot' in blob:
        gear_tags.append('ringnot')
    if 'garn' in blob:
        gear_tags.append('garn')
    if 'teine' in blob:
        gear_tags.append('teine')

    seen_gears: list[str] = []
    for gear in gear_tags:
        canonical = normalize_gear(gear)
        if canonical and canonical not in seen_gears:
            seen_gears.append(canonical)
    gear_tags = seen_gears

    control_tags: list[str] = []
    if 'fritids' in blob:
        control_tags.append('fritidsfiske')
    if any(hint in blob for hint in COMMERCIAL_HINTS):
        control_tags.append('kommersiell')
    control_tags = [tag for idx, tag in enumerate(control_tags) if tag not in control_tags[:idx]]

    generic = not fishery_tags and not gear_tags and not control_tags
    if generic and any(hint in blob for hint in _GENERIC_STATUS_NAME_HINTS):
        generic = True

    return {
        'fishery_tags': fishery_tags,
        'gear_tags': gear_tags,
        'control_tags': control_tags,
        'is_generic': generic,
        'selection_blob': blob,
        'selection_summary': build_selection_summary(fishery_tags, gear_tags, control_tags, generic),
    }


def decorate_catalog_row(row: dict[str, Any]) -> dict[str, Any]:
    enriched = dict(row)
    meta = build_layer_metadata(row.get('name') or '', row.get('description') or '', row.get('status') or '', row.get('geometry_type') or '')
    enriched.update(meta)
    return enriched


def decorate_zone_row(zone: dict[str, Any]) -> dict[str, Any]:
    enriched = dict(zone)
    meta = build_layer_metadata(zone.get('name') or zone.get('layer_name') or '', zone.get('notes') or '', zone.get('status') or '', 'esriGeometryPolygon')
    enriched.update(meta)
    return enriched


def matches_selection(meta_like: dict[str, Any], *, fishery: Any = '', control_type: Any = '', gear_type: Any = '') -> bool:
    fishery_sel = normalize_fishery(fishery)
    control_sel = normalize_control_type(control_type)
    gear_sel = normalize_gear(gear_type)

    fishery_tags = [normalize_fishery(item) for item in list(meta_like.get('fishery_tags') or []) if str(item or '').strip()]
    control_tags = [normalize_control_type(item) for item in list(meta_like.get('control_tags') or []) if str(item or '').strip()]
    gear_tags = [normalize_gear(item) for item in list(meta_like.get('gear_tags') or []) if str(item or '').strip()]

    if control_sel and control_tags and control_sel not in control_tags:
        return False
    if fishery_sel and fishery_tags and fishery_sel not in fishery_tags:
        return False
    if gear_sel and gear_tags and gear_sel not in gear_tags:
        return False
    return True
