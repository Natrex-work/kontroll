from __future__ import annotations

from typing import Any

from . import rules

CREW_ROLES = ['Vitne', 'Båtfører', 'Båtassistent']
EXTERNAL_ACTORS = ['Politiet', 'SNO', 'Fiskeridirektoratet']

# Regelmotoren er bygd for test/test med tydelige, regulerte valg.
# Kontrollpunktene genereres i rules.py, mens denne modulen beskriver
# hvilke valg som skal tilbys i UI-et og i regelverksoversikten.

LAW_CATALOG: dict[str, dict[str, Any]] = {
    'fritidsfiske': {
        'label': 'Fritidsfiske',
        'intro': 'Velg art og redskap. Appen viser bare relevante kontrollpunkter og periode-/områderegler for valgt fiskeri.',
        'species': list(rules.FRITID_SPECIES),
        'gear': list(rules.FRITID_GEARS),
        'sources': [
            {'name': 'Fiskeridirektoratet', 'ref': 'Fritidsfiske - arter og redskap', 'url': 'https://www.fiskeridir.no/Fritidsfiske'},
            {'name': 'Fiskeridirektoratet', 'ref': 'Registrerte hummarfiskarar', 'url': 'https://www.fiskeridir.no/statistikk-tall-og-analyse/data-og-statistikk-om-turist--og-fritidsfiske/registrerte-hummarfiskarar'},
            {'name': 'Lovdata', 'ref': 'Forskrift om høsting av hummer', 'url': 'https://lovdata.no/forskrift/2021-12-23-3890'},
            {'name': 'Lovdata', 'ref': 'Høstingsforskriften', 'url': 'https://lovdata.no/dokument/SF/forskrift/2021-12-23-3910'},
            {'name': 'Fiskeridirektoratet kartportal', 'ref': 'Frednings- og forbudsområder', 'url': 'https://portal.fiskeridir.no/portal/apps/webappviewer/index.html?id=ea6c536f760548fe9f56e6edcc4825d8'},
        ],
    },
    'kommersiell': {
        'label': 'Kommersiell',
        'intro': 'Velg art og redskap. Appen viser bare relevante kontrollpunkter og område-/periodekrav for valgt kommersielt fiskeri.',
        'species': list(rules.KOMM_SPECIES),
        'gear': list(rules.KOMM_GEARS),
        'sources': [
            {'name': 'Fiskeridirektoratet', 'ref': 'J-meldinger', 'url': 'https://www.fiskeridir.no/Yrkesfiske/J-meldinger'},
            {'name': 'Fiskeridirektoratet', 'ref': 'Fartøyregisteret API', 'url': 'https://www.fiskeridir.no/registre/fartoyregisteret/api-for-fartoyregisteret'},
            {'name': 'Lovdata', 'ref': 'Høstingsforskriften', 'url': 'https://lovdata.no/dokument/SF/forskrift/2021-12-23-3910'},
            {'name': 'Fiskeridirektoratet kartportal', 'ref': 'Frednings- og forbudsområder', 'url': 'https://portal.fiskeridir.no/portal/apps/webappviewer/index.html?id=ea6c536f760548fe9f56e6edcc4825d8'},
        ],
    },
}


COMMERCIAL_FIELDS = [
    {'name': 'suspect_name', 'label': 'Ansvarlig / reder / eier'},
    {'name': 'vessel_name', 'label': 'Fartøysnavn'},
    {'name': 'vessel_reg', 'label': 'Fiskerimerke'},
    {'name': 'radio_call_sign', 'label': 'Radiokallesignal'},
]

LEISURE_FIELDS = [
    {'name': 'suspect_name', 'label': 'Navn'},
    {'name': 'suspect_address', 'label': 'Adresse'},
    {'name': 'suspect_phone', 'label': 'Mobilnummer'},
    {'name': 'suspect_birthdate', 'label': 'Fødselsdato'},
    {'name': 'hummer_participant_no', 'label': 'Hummerdeltakernummer'},
]


def _key(control_type: str) -> str:
    text = (control_type or '').strip().lower()
    if text.startswith('kom'):
        return 'kommersiell'
    return 'fritidsfiske'


def control_labels() -> list[str]:
    return ['Fritidsfiske', 'Kommersiell']


def regulated_species(control_type: str) -> list[str]:
    return list(LAW_CATALOG[_key(control_type)]['species'])


def regulated_gears(control_type: str) -> list[str]:
    return list(LAW_CATALOG[_key(control_type)]['gear'])


def species_suggestions() -> list[str]:
    seen: list[str] = []
    for group in LAW_CATALOG.values():
        for item in group['species']:
            if item not in seen:
                seen.append(item)
    return seen


def law_browser_data() -> list[dict[str, Any]]:
    return [
        {
            'key': key,
            'label': value['label'],
            'intro': value['intro'],
            'species': list(value['species']),
            'gear': list(value['gear']),
            'sources': list(value['sources']),
        }
        for key, value in LAW_CATALOG.items()
    ]


def person_fields(control_type: str) -> list[dict[str, str]]:
    return COMMERCIAL_FIELDS if _key(control_type) == 'kommersiell' else LEISURE_FIELDS
