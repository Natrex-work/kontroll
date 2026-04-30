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
            {'name': 'Fiskeridirektoratet kartportal', 'ref': 'Frednings- og forbudsområder', 'url': 'https://portal.fiskeridir.no/portal/apps/experiencebuilder/experience/?id=346b009e963945e09e1dd23f1a40c762#widget_174=active_datasource_id:dataSource_16,center:219178.6907005629%2C6498779.5776808085%2C25833,scale:617585.2866455576,viewpoint:%7B%22rotation%22%3A356.18800630200445%2C%22scale%22%3A617585.2866455576%2C%22targetGeometry%22%3A%7B%22spatialReference%22%3A%7B%22latestWkid%22%3A25833%2C%22wkid%22%3A25833%7D%2C%22x%22%3A219178.6907005629%2C%22y%22%3A6498779.5776808085%7D%7D,layer_visibility:%7B%22widget_174-dataSource_16%22%3A%7B%22widget_174-dataSource_16-198f5e53031-layer-86%22%3Atrue%2C%22widget_174-dataSource_16-198f5e9e5f4-layer-91%22%3Atrue%2C%22widget_174-dataSource_16-198f5f0a60e-layer-94%22%3Atrue%2C%22widget_174-dataSource_16-198f5f4a9f8-layer-96%22%3Atrue%2C%22widget_174-dataSource_16-198f5e53031-layer-86-Fiskerireguleringer_1058%22%3Atrue%2C%22widget_174-dataSource_16-198f5e9e5f4-layer-91-Korallrev_8882%22%3Atrue%2C%22widget_174-dataSource_16-198f5e53031-layer-86-Fiskerireguleringer_1058-0%22%3Atrue%2C%22widget_174-dataSource_16-198f5e53031-layer-86-Fiskerireguleringer_1058-33%22%3Atrue%2C%22widget_174-dataSource_16-198f5e53031-layer-86-Fiskerireguleringer_1058-6%22%3Atrue%2C%22widget_174-dataSource_16-198f5e53031-layer-86-Fiskerireguleringer_1058-7%22%3Atrue%2C%22widget_174-dataSource_16-198f5e53031-layer-86-Fiskerireguleringer_1058-9%22%3Atrue%2C%22widget_174-dataSource_16-198f5e53031-layer-86-Fiskerireguleringer_1058-11%22%3Atrue%2C%22widget_174-dataSource_16-198f5e53031-layer-86-Fiskerireguleringer_1058-15%22%3Atrue%2C%22widget_174-dataSource_16-198f5e53031-layer-86-Fiskerireguleringer_1058-16%22%3Atrue%2C%22widget_174-dataSource_16-198f5e53031-layer-86-Fiskerireguleringer_1058-8%22%3Atrue%2C%22widget_174-dataSource_16-198f5e53031-layer-86-Fiskerireguleringer_1058-37%22%3Atrue%2C%22widget_174-dataSource_16-198f5e53031-layer-86-Fiskerireguleringer_1058-18%22%3Atrue%2C%22widget_174-dataSource_16-198f5e53031-layer-86-Fiskerireguleringer_1058-19%22%3Atrue%7D%7D'},
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
            {'name': 'Fiskeridirektoratet kartportal', 'ref': 'Frednings- og forbudsområder', 'url': 'https://portal.fiskeridir.no/portal/apps/experiencebuilder/experience/?id=346b009e963945e09e1dd23f1a40c762#widget_174=active_datasource_id:dataSource_16,center:219178.6907005629%2C6498779.5776808085%2C25833,scale:617585.2866455576,viewpoint:%7B%22rotation%22%3A356.18800630200445%2C%22scale%22%3A617585.2866455576%2C%22targetGeometry%22%3A%7B%22spatialReference%22%3A%7B%22latestWkid%22%3A25833%2C%22wkid%22%3A25833%7D%2C%22x%22%3A219178.6907005629%2C%22y%22%3A6498779.5776808085%7D%7D,layer_visibility:%7B%22widget_174-dataSource_16%22%3A%7B%22widget_174-dataSource_16-198f5e53031-layer-86%22%3Atrue%2C%22widget_174-dataSource_16-198f5e9e5f4-layer-91%22%3Atrue%2C%22widget_174-dataSource_16-198f5f0a60e-layer-94%22%3Atrue%2C%22widget_174-dataSource_16-198f5f4a9f8-layer-96%22%3Atrue%2C%22widget_174-dataSource_16-198f5e53031-layer-86-Fiskerireguleringer_1058%22%3Atrue%2C%22widget_174-dataSource_16-198f5e9e5f4-layer-91-Korallrev_8882%22%3Atrue%2C%22widget_174-dataSource_16-198f5e53031-layer-86-Fiskerireguleringer_1058-0%22%3Atrue%2C%22widget_174-dataSource_16-198f5e53031-layer-86-Fiskerireguleringer_1058-33%22%3Atrue%2C%22widget_174-dataSource_16-198f5e53031-layer-86-Fiskerireguleringer_1058-6%22%3Atrue%2C%22widget_174-dataSource_16-198f5e53031-layer-86-Fiskerireguleringer_1058-7%22%3Atrue%2C%22widget_174-dataSource_16-198f5e53031-layer-86-Fiskerireguleringer_1058-9%22%3Atrue%2C%22widget_174-dataSource_16-198f5e53031-layer-86-Fiskerireguleringer_1058-11%22%3Atrue%2C%22widget_174-dataSource_16-198f5e53031-layer-86-Fiskerireguleringer_1058-15%22%3Atrue%2C%22widget_174-dataSource_16-198f5e53031-layer-86-Fiskerireguleringer_1058-16%22%3Atrue%2C%22widget_174-dataSource_16-198f5e53031-layer-86-Fiskerireguleringer_1058-8%22%3Atrue%2C%22widget_174-dataSource_16-198f5e53031-layer-86-Fiskerireguleringer_1058-37%22%3Atrue%2C%22widget_174-dataSource_16-198f5e53031-layer-86-Fiskerireguleringer_1058-18%22%3Atrue%2C%22widget_174-dataSource_16-198f5e53031-layer-86-Fiskerireguleringer_1058-19%22%3Atrue%7D%7D'},
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
