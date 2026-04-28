from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List

HUMMER_LAW = 'Forskrift om høsting av hummer'
HUMMER_LAW_REF = 'FOR-2021-12-23-3890'
HOSTING_LAW = 'Forskrift om gjennomføring av fiske, fangst og høsting av viltlevende marine ressurser (høstingsforskriften)'
HOSTING_LAW_REF = 'FOR-2021-12-23-3910'
HUMMER_FREDNING_LAW = 'Forskrift om fredningsområder for hummer'
HUMMER_FREDNING_REF = 'FOR-2006-07-06-883'
HAVRESSURSLOVA = 'Havressurslova'
AREA_LAW = 'Fiskeridirektoratets kartportal og områderegulering'
GENERIC_ART_LAW = 'Relevant særforskrift for valgt art'

ALLOWED_GEARS_HUMMER_FREDNING = {'håndsnøre', 'fiskestang', 'jukse', 'dorg', 'snurpenot'}
AREA_SEVERITY = {'stengt område': 3, 'nullfiskeområde': 3, 'fredningsområde': 2, 'maksimalmål område': 1, 'regulert område': 1}


FRITID_SPECIES = [
    'Hummer', 'Taskekrabbe', 'Torsk', 'Kveite', 'Laks i sjø', 'Sjøørret', 'Makrell', 'Hyse', 'Sei',
    'Leppefisk', 'Sjøkreps', 'Kongekrabbe', 'Snøkrabbe', 'Makrellstørje', 'Sild', 'Reke', 'Breiflabb'
]

KOMM_SPECIES = [
    'Hummer', 'Taskekrabbe', 'Kongekrabbe', 'Snøkrabbe', 'Torsk', 'Hyse', 'Sei',
    'Kveite', 'Breiflabb', 'Sjøkreps', 'Reke', 'Laks i sjø', 'Makrell', 'NVG-sild', 'Makrellstørje', 'Blåkveite',
    'Lange', 'Brosme', 'Kolmule', 'Øyepål', 'Hestmakrell'
]

FRITID_GEARS = ['Teine', 'Samleteine / sanketeine', 'Garn', 'Line', 'Ruse', 'Håndsnøre', 'Dorg', 'Jukse', 'Fiskestang']
KOMM_GEARS = ['Teine', 'Samleteine / sanketeine', 'Garn', 'Line', 'Ruse', 'Trål', 'Pelagisk trål', 'Snurrevad', 'Not', 'Ringnot', 'Jukse', 'Krokredskap']


SPECIES_GUIDANCE: dict[str, str] = {
    'torsk': 'Kontroller områderegler, eventuelle nullfiske- og stengingssoner, samt artsspesifikke særregler for valgt område.',
    'kveite': 'Kontroller minstemål, periodebestemmelser, områdekrav og eventuelle særregler for fritids- eller yrkesfiske.',
    'laks i sjø': 'Kontroller at fiskeformen er lovlig i området og at særlige regler for anadrome arter er fulgt.',
    'sjøørret': 'Kontroller at fiskeformen er lovlig i området og at særlige regler for anadrome arter er fulgt.',
    'leppefisk': 'Kontroller område, redskap og eventuelle sesong- eller rapporteringskrav.',
    'sjøkreps': 'Kontroller teiner/redskap, rømningshull og eventuelle område- eller rapporteringskrav.',
    'kongekrabbe': 'Kontroller område, redskap, registrering og eventuelle kvote- eller rapporteringskrav.',
    'snøkrabbe': 'Kontroller merking på teine, fartøyopplysninger og spesielle tekniske krav til redskap.',
    'makrellstørje': 'Kontroller at fisket skjer med gyldig hjemmel/tillatelse og at artsspesifikke krav er oppfylt.',
    'nvg-sild': 'Kontroller område, tillatelse og rapportering for pelagisk fiske.',
    'reke': 'Kontroller område og rapportering for valgt redskap og fartøy.',
    'breiflabb': 'Kontroller område, redskap og merkekrav for kommersielt fiske.',
    'makrell': 'Kontroller redskap, område og eventuelle sesongbegrensninger.',
    'hyse': 'Kontroller redskap, område og artsspesifikke begrensninger der dette gjelder.',
    'sei': 'Kontroller redskap, område og artsspesifikke begrensninger der dette gjelder.',
    'blåkveite': 'Kontroller område og særlige merkekrav ved garnfiske, inkludert § 66.',
    'taskekrabbe': 'Kontroller fluktåpning, rømningshull og merkekrav for teinefiske.',
    'krabbe': 'Kontroller fluktåpninger, rømningshull, merking og eventuelle geografiske unntak.',
    'hummer': 'Kontroller påmelding, merking, fluktåpninger, rømmingshull, antall teiner, sesong, minstemål og eventuell fredning.',
}


def _norm(text: str | None) -> str:
    return ' '.join(str(text or '').strip().lower().split())



def _parse_date(value: str | None) -> datetime | None:
    raw = str(value or '').strip()
    if not raw:
        return None
    for fmt in ('%Y-%m-%dT%H:%M:%S', '%Y-%m-%dT%H:%M', '%Y-%m-%d', '%d.%m.%Y'):
        try:
            return datetime.strptime(raw, fmt)
        except ValueError:
            continue
    return None


HUMMER_MAX_FALLBACK_BOUNDS = {
    'min_lat': 57.7,
    'max_lat': 60.1,
    'min_lng': 6.0,
    'max_lng': 11.5,
}


def _float_or_none(value: Any) -> float | None:
    try:
        if value is None or str(value).strip() == '':
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _has_maximalmal_context(area_status: str = '', area_name: str = '', area_notes: str = '') -> bool:
    blob = ' '.join(part for part in [_norm(area_status), _norm(area_name), _norm(area_notes)] if part)
    return 'maksimalmål' in blob or 'maksimalmal' in blob


def hummer_max_size_applies(*, area_status: str = '', area_name: str = '', area_notes: str = '', lat: float | None = None, lng: float | None = None) -> bool:
    if _has_maximalmal_context(area_status=area_status, area_name=area_name, area_notes=area_notes):
        return True
    lat_f = _float_or_none(lat)
    lng_f = _float_or_none(lng)
    if lat_f is None or lng_f is None:
        return False
    return (
        HUMMER_MAX_FALLBACK_BOUNDS['min_lat'] <= lat_f <= HUMMER_MAX_FALLBACK_BOUNDS['max_lat']
        and HUMMER_MAX_FALLBACK_BOUNDS['min_lng'] <= lng_f <= HUMMER_MAX_FALLBACK_BOUNDS['max_lng']
    )


def _item(
    key: str,
    label: str,
    law_name: str,
    section: str,
    law_text: str,
    summary_text: str | None = None,
    help_text: str | None = None,
    *,
    status: str = 'ikke kontrollert',
    notes: str = '',
    supports_measurements: bool = False,
    measurement_type: str = '',
    min_size_cm: str = '',
    max_size_cm: str = '',
    applied_min_size_cm: str = '',
    applied_max_size_cm: str = '',
    supports_marker_positions: bool = False,
) -> dict[str, Any]:
    return {
        'key': key,
        'label': label,
        'status': status,
        'notes': notes,
        'source_name': law_name,
        'source_ref': section,
        'law_name': law_name,
        'section': section,
        'law_text': law_text,
        'summary_text': summary_text or label,
        'help_text': help_text or law_text,
        'supports_measurements': supports_measurements,
        'measurement_type': measurement_type,
        'min_size_cm': min_size_cm,
        'max_size_cm': max_size_cm,
        'applied_min_size_cm': applied_min_size_cm or min_size_cm,
        'applied_max_size_cm': applied_max_size_cm or max_size_cm,
        'supports_marker_positions': supports_marker_positions,
    }


# --- Core legal items with explicit paragraftekst ---
HUMMER_DELTAGERNR = _item(
    'hummerdeltakernummer',
    'Påmelding og hummerdeltakernummer',
    HUMMER_LAW,
    '§ 2. Påmelding og tildeling av deltakernummer',
    'Ingen kan høste hummer uten først å være påmeldt til Fiskeridirektoratet på fastsatt måte. Påmeldingen gjelder for én sesong, og må inneholde navn, adresse, telefonnummer og eventuell annen informasjon som er nødvendig for å identifisere og komme i kontakt med den som skal høste. Den som skal høste hummer tildeles et deltakernummer.',
    'Kontroller at personen er registrert for inneværende sesong, og at deltakernummeret stemmer med hummerregisteret og merkingen på vak/redskap.',
)

HUMMER_MERKING = _item(
    'hummer_merking',
    'Merking av vak, blåse og sanketeine',
    HUMMER_LAW,
    '§ 3. Merking',
    'Teiner som står i sjøen til høsting av hummer skal ha minst ett vak (blåse, flyt eller dobbe) som er tydelig merket med fiskerens deltakernummer. I tillegg skal vaket være tydelig merket med fartøyets registreringsmerke. Dersom det ikke benyttes registreringspliktig fartøy, skal redskapet være merket med eierens navn og adresse. Det er ikke tillatt å benytte redskap som ikke har vak. Vaket skal være godt synlig. Sanketeiner og samleposer som er satt for å oppbevare hummer i sjøen skal være merket på tilsvarende måte.',
    'Kontroller at vak/blåse er godt synlig og merket med riktig deltakernummer, og enten registreringsmerke eller navn og adresse når fartøyet ikke er registreringspliktig.',
    supports_marker_positions=True,
)

HUMMER_FLUKT = _item(
    'hummer_fluktapning',
    'Fluktåpning i hummerteine (minst 60 mm)',
    HUMMER_LAW,
    '§ 4. Fangstredskap og fluktåpninger',
    'Hummer kan bare høstes med teiner. Teinene skal ha fluktåpninger slik som beskrevet nedenfor. I teiner som er satt ut til høsting av hummer skal det være minst en sirkelformet fluktåpning på hver side av redskapet. Åpningens diameter skal være minst 60 mm. Fluktåpningene skal være plassert på en slik måte at hummeren lett kan ta seg ut av redskapet. I teiner med plan bunn skal åpningene plasseres helt nede ved redskapsbunnen. I teiner med sylinderform (tønneform) skal åpningene være helt nede ved redskapets bunn, men ikke lenger nede enn at det blir fri passasje gjennom åpningene når redskapene står ute for høsting.',
    'Kontroller at hummerteinen har minst én sirkelformet fluktåpning på hver side, og at hver åpning måler minst 60 mm og er plassert riktig.',
)

HUMMER_RATENTRAD = _item(
    'hummer_ratentrad',
    'Rømmingshull med biologisk nedbrytbar tråd',
    HUMMER_LAW,
    '§ 5. Rømmingshull med biologisk nedbrytbar tråd',
    'Teiner som settes ut til høsting av hummer skal ha rømmingshull i samsvar med anvisningen i vedlegg til forskrift 23. desember 2021 nr. 3910 om gjennomføring av fiske, fangst og høsting av viltlevende marine ressurser (høstingsforskriften).',
    'Kontroller at teinen har rømmingshull med biologisk nedbrytbar tråd i samsvar med vedlegg 3 og monteringskravene i høstingsforskriften.',
)

HUMMER_ANTALL_FRITID = _item(
    'hummer_antall_teiner_fritid',
    'Antall hummerteiner (fritidsfiske)',
    HUMMER_LAW,
    '§ 6. Redskapsbegrensning',
    'Personer som høster med fartøy som ikke er merkeregistrert eller fra land kan høste med inntil 10 teiner. Innenfor grunnlinjen fra og med Telemark til svenskegrensen kan det høstes med inntil 5 teiner. Begrensningene i antall teiner gjelder både per person og per fartøy.',
    'Kontroller at antallet hummerteiner ikke overstiger 10 generelt, og ikke overstiger 5 innenfor grunnlinjen fra Telemark til svenskegrensen.',
)

HUMMER_ANTALL_KOMM = _item(
    'hummer_antall_teiner_komm',
    'Antall hummerteiner (kommersiell)',
    HUMMER_LAW,
    '§ 6. Redskapsbegrensning',
    'Manntallsførte fiskere som høster med merkeregistrert fartøy kan høste hummer med inntil 100 teiner.',
    'Kontroller at manntallsført fisker med merkeregistrert fartøy ikke bruker mer enn 100 hummerteiner.',
)

HUMMER_ROKTING = _item(
    'hummer_rokting',
    'Røkting minst en gang per uke',
    HUMMER_LAW,
    '§ 7. Krav til røkting',
    'Teiner som benyttes til høsting av hummer skal røktes minst en gang per uke.',
    'Kontroller at hummerteinene er røktet minst én gang per uke.',
)

HUMMER_PERIODE = _item(
    'hummer_periode',
    'Fredningstid og tillatt periode for hummerfiske',
    HUMMER_LAW,
    '§ 8. Fredningstid for hummer',
    'Det er kun tillatt å sette ut teiner til høsting av hummer i følgende områder og tidsrom: a) Fra grensen mot Sverige til og med Vestland fylke fra 1. oktober kl. 08.00 til og med 30. november. b) I resten av landet fra 1. oktober kl. 08.00 til og med 31. desember.',
    'Kontroller at redskapet står ute innenfor tillatt sesong for aktuell landsdel og dato.',
)

HUMMER_MINSTEMAL = _item(
    'hummer_minstemal',
    'Minstemål hummer (25 cm)',
    HUMMER_LAW,
    '§ 9. Minstemål',
    'Det er forbudt å høste hummer mindre enn 25 cm målt fra spissen av pannehornet til den bakre kant av midterste svømmelapp.',
    'Kontroller måling av hummer fra spissen av pannehornet til bakre kant av midterste svømmelapp. Hummer under 25 cm er ulovlig fangst.',
    supports_measurements=True,
    measurement_type='length',
    min_size_cm='25',
    applied_min_size_cm='25',
)

HUMMER_MAKSIMALMAL = _item(
    'hummer_maksimalmal',
    'Maksimalmål hummer (32 cm i sør)',
    HUMMER_LAW,
    '§ 10. Maksimalmål',
    'Det er på strekningen fra grensen mot Sverige til og med Agder fylke forbudt å høste hummer som har en lengde på 32 cm eller mer målt fra spissen av pannehornet til den bakre kant av midterste svømmelapp.',
    'Kontroller maksimalmål i sørlandsområdet. Hummer på 32 cm eller mer skal ikke høstes på strekningen fra Sverige til og med Agder.',
    supports_measurements=True,
    measurement_type='length',
    max_size_cm='32',
    applied_max_size_cm='32',
)

HUMMER_LENGDEKRAV = _item(
    'hummer_lengdekrav',
    'Lengdekrav hummer (min. 25 cm / maks. 32 cm i sør)',
    HUMMER_LAW,
    '§ 9 og § 10. Minstemål og maksimalmål',
    'Det er forbudt å høste hummer mindre enn 25 cm målt fra spissen av pannehornet til den bakre kant av midterste svømmelapp. På strekningen fra grensen mot Sverige til og med Agder fylke er det i tillegg forbudt å høste hummer som har en lengde på 32 cm eller mer målt på samme måte.',
    'Kontroller måling av hummer fra spissen av pannehornet til bakre kant av midterste svømmelapp. I områder med maksimalmål skal hummeren være minst 25 cm og under 32 cm. Appen viser automatisk om målingen er under minstemålet eller på/over maksimalmålet, inkludert avvik i cm og mm.',
    supports_measurements=True,
    measurement_type='length',
    min_size_cm='25',
    max_size_cm='32',
    applied_min_size_cm='25',
    applied_max_size_cm='32',
)

HUMMER_ROGN = _item(
    'hummer_rogn',
    'Forbud mot høsting og oppbevaring av rognhummer',
    HUMMER_LAW,
    '§ 11. Forbud mot høsting og oppbevaring av rognhummer',
    'Det er forbudt å høste eller oppbevare hummer med utvendig rogn.',
    'Kontroller om hummeren har utvendig rogn. Rognhummer skal ikke høstes eller oppbevares.',
)

HUMMER_UTSETTING = _item(
    'hummer_gjenutsetting',
    'Utsettingsplikt for hummer',
    HUMMER_LAW,
    '§ 12. Utsettingsplikt',
    'Hummer høstet eller oppbevart i strid med bestemmelsene skal straks slippes tilbake i sjøen på en slik måte at hummeren finner tilbake til sitt naturlige miljø og unngår å bli skadet.',
    'Kontroller om hummer som er tatt i strid med reglene er gjenutsatt korrekt og uten unødig skade.',
)

HUMMER_OPPBEVARING_DESEMBER = _item(
    'hummer_oppbevaring_desember',
    'Oppbevaring av hummer i desember / innrapportering',
    HUMMER_LAW,
    '§ 13. Oppbevaring av hummer i fredningstiden',
    'Fra og med 1. januar til 1. oktober kl.08.00 er det forbudt å oppbevare hummer i sjøen. I desember fra og med Vestland og østover til grensa mot Sverige må oppbevaring i sjøen meldes til Fiskeridirektoratet.',
    'Kontroller om oppbevaring i sjøen skjer i tillatt periode, og om oppbevaring i desember fra Vestland og østover til grensa mot Sverige er innrapportert.',
)

SAMLETEINE_MERKING = _item(
    'samleteine_merking',
    'Merking av sanketeine / samleteine',
    HUMMER_LAW,
    '§ 3. Merking',
    'Sanketeiner og samleposer som er satt for å oppbevare hummer i sjøen skal være merket på tilsvarende måte som hummerteiner med synlig vak, deltakernummer og enten registreringsmerke eller navn og adresse når fartøyet ikke er registreringspliktig.',
    'Kontroller at vak/blåse og oppbevaringsredskap er korrekt merket med deltakernummer og korrekt identifikasjon av eier eller fartøy.',
    supports_marker_positions=False,
)

MIN_SIZE_RULES: dict[str, dict[str, str]] = {
    'hummer': {'label': 'Minstemål hummer', 'min': '25', 'source_name': HUMMER_LAW, 'section': '§ 9. Minstemål', 'law_text': 'Det er forbudt å høste hummer mindre enn 25 cm målt fra spissen av pannehornet til den bakre kant av midterste svømmelapp.', 'summary': 'Hummer under 25 cm er under minstemål og skal settes tilbake i sjøen.'},
    'krabbe': {'label': 'Minstemål krabbe', 'min': '11 / 13', 'source_name': 'Fiskeridirektoratet', 'section': 'Minstemål i fritidsfiske', 'law_text': 'Minstemålet for krabbe er 11 cm frå svenskegrensa til og med Rogaland, og 13 cm i resten av landet.', 'summary': 'Mål skjoldbredden og bruk riktig minstemål for området.'},
    'taskekrabbe': {'label': 'Minstemål taskekrabbe', 'min': '11 / 13', 'source_name': 'Fiskeridirektoratet', 'section': 'Minstemål i fritidsfiske', 'law_text': 'Minstemålet for krabbe er 11 cm frå svenskegrensa til og med Rogaland, og 13 cm i resten av landet.', 'summary': 'Mål skjoldbredden og bruk riktig minstemål for området.'},
    'torsk': {'label': 'Minstemål torsk', 'min': '40 / 44 / 55', 'source_name': 'Fiskeridirektoratet', 'section': 'Minstemål i fritidsfiske', 'law_text': 'For torsk sør for 62°N er minstemålet 40 cm. Nord for 62°N er minstemålet 44 cm utanfor 4 nautiske mil av grunnlinjene og 55 cm innanfor 4 nautiske mil av grunnlinjene.', 'summary': 'Bruk riktig minstemål for område og avstand frå grunnlinjene.'},
    'hyse': {'label': 'Minstemål hyse', 'min': '32 / 40', 'source_name': 'Fiskeridirektoratet', 'section': 'Minstemål i fritidsfiske', 'law_text': 'Minstemålet for hyse er 32 cm sør for 62°N og 40 cm nord for 62°N.', 'summary': 'Bruk riktig minstemål for aktuell landsdel.'},
    'kveite': {'label': 'Minstemål kveite', 'min': '84', 'source_name': 'Fiskeridirektoratet', 'section': 'Kveite for fritidsfiskarar / minstemål', 'law_text': 'Minstemålet for kveite er 84 cm. Ved omsetning gjelder også minstevekt 7,2 kg.', 'summary': 'Kontroller at kveite er minst 84 cm. Ved omsetning gjelder også minstevekt.'},
    'sjøørret': {'label': 'Minstemål sjøørret', 'min': '30 / 35', 'source_name': 'Fiskeridirektoratet', 'section': 'Minstemål i fritidsfiske', 'law_text': 'Minstemålet for sjøørret er 30 cm i Nordland, Troms og Finnmark og 35 cm i resten av landet.', 'summary': 'Bruk riktig minstemål for aktuell landsdel.'},
    'sjøaure': {'label': 'Minstemål sjøørret', 'min': '30 / 35', 'source_name': 'Fiskeridirektoratet', 'section': 'Minstemål i fritidsfiske', 'law_text': 'Minstemålet for sjøørret er 30 cm i Nordland, Troms og Finnmark og 35 cm i resten av landet.', 'summary': 'Bruk riktig minstemål for aktuell landsdel.'},
    'sjøkreps': {'label': 'Minstemål sjøkreps', 'min': '13', 'source_name': 'Fiskeridirektoratet', 'section': 'Minstemål i fritidsfiske', 'law_text': 'Minstemålet for sjøkreps er 13 cm.', 'summary': 'Mål fra spissen av pannehorn til bakre kant av midterste svømmelapp eller bruk gjeldende metode for arten.'},
    'blåkveite': {'label': 'Minstemål blåkveite', 'min': '45', 'source_name': 'Fiskeridirektoratet', 'section': 'Minstemål i fritidsfiske', 'law_text': 'Minstemålet for blåkveite er 45 cm.', 'summary': 'Kontroller at blåkveite er minst 45 cm.'},
    'breiflabb': {'label': 'Minstemål breiflabb i garnfiske', 'min': '60', 'source_name': 'Fiskeridirektoratet', 'section': 'Minstemål i fritidsfiske', 'law_text': 'Minstemålet for breiflabb i garnfiske er 60 cm.', 'summary': 'Kontroller at breiflabb i garnfiske er minst 60 cm.'},
    'kviting': {'label': 'Minstemål kviting', 'min': '32', 'source_name': 'Fiskeridirektoratet', 'section': 'Minstemål i fritidsfiske', 'law_text': 'Minstemålet for kviting er 32 cm.', 'summary': 'Kontroller at kviting er minst 32 cm.'},
    'lysing': {'label': 'Minstemål lysing', 'min': '30', 'source_name': 'Fiskeridirektoratet', 'section': 'Minstemål i fritidsfiske', 'law_text': 'Minstemålet for lysing er 30 cm.', 'summary': 'Kontroller at lysing er minst 30 cm.'},
    'raudspette': {'label': 'Minstemål raudspette', 'min': '29', 'source_name': 'Fiskeridirektoratet', 'section': 'Minstemål i fritidsfiske', 'law_text': 'Minstemålet for raudspette er 29 cm.', 'summary': 'Kontroller at raudspette er minst 29 cm.'},
}

def minimum_size_item(species: str) -> dict[str, Any] | None:
    spec = MIN_SIZE_RULES.get(_norm(species))
    if not spec:
        return None
    return _item(
        f"minstemal_{_norm(species).replace(' ', '_')}",
        spec['label'],
        spec['source_name'],
        spec['section'],
        spec['law_text'],
        spec['summary'],
        supports_measurements=True,
        measurement_type='length',
        min_size_cm=spec['min'],
    )

KRABBE_FLUKT_FRITID = _item(
    'krabbe_fluktapning_fritid',
    'Fluktåpning i krabbeteine (minst 80 mm)',
    HOSTING_LAW,
    '§ 29. Påbud om fluktåpninger og rømningshull i teiner',
    'I teiner som er satt ut til fangst av krabbe på kyststrekningen fra grensen mot Sverige til og med statistikkområde 00-38, skal det være minst én sirkelformet fluktåpning med diameter på minst 80 mm på hver side av redskapet. Fluktåpningene skal være plassert i fangstkammeret på en slik måte at hummeren lett kan ta seg ut av redskapet. I teiner med plan bunn skal åpningene plasseres helt nede ved redskapsbunnen. I teiner med sylinderform (tønneform) skal åpningene være helt nede ved redskapets bunn, men ikke lenger nede enn at det blir fri passasje gjennom åpningene når redskapet står ute for fangst.',
    'Kontroller at krabbeteinen har minst én sirkelformet fluktåpning på hver side med diameter minst 80 mm, og at åpningene er plassert riktig i fangstkammeret.',
)

KRABBE_FLUKT_KOMM = _item(
    'krabbe_fluktapning_komm',
    'Fluktåpning i krabbeteine (80 mm / 70 mm-unntak)',
    HOSTING_LAW,
    '§ 29. Påbud om fluktåpninger og rømningshull i teiner',
    'I teiner som er satt ut til fangst av krabbe på kyststrekningen fra grensen mot Sverige til og med statistikkområde 00-38, skal det være minst én sirkelformet fluktåpning med diameter på minst 80 mm på hver side av redskapet. På kyststrekningen fra grensen mot Sverige til og med Rogaland fylke kan manntallsførte fiskere som fangster krabbe for omsetning med merkeregistrert fartøy likevel bruke teiner der fluktåpningene er minst 70 mm. I Trøndelag og Nordland fylker med unntak av statistikkområde 00-38 gjelder kravet nevnt i første punktum ikke for manntallsførte fiskere som fangster krabbe for omsetning med merkeregistrert fartøy. Fluktåpningene skal være plassert i fangstkammeret på en slik måte at hummeren lett kan ta seg ut av redskapet. I teiner med plan bunn skal åpningene plasseres helt nede ved redskapsbunnen. I teiner med sylinderform (tønneform) skal åpningene være helt nede ved redskapets bunn, men ikke lenger nede enn at det blir fri passasje gjennom åpningene når redskapet står ute for fangst.',
    'Kontroller om kommersielt krabbefiske omfattes av 80 mm-hovedregelen eller 70 mm-unntaket, og mål fluktåpningene i lys av riktig geografisk område og fartøystype.',
)

KRABBE_RATENTRAD = _item(
    'krabbe_ratentrad',
    'Rømningshull i krabbe- og annen krabbeteine',
    HOSTING_LAW,
    '§ 29. Påbud om fluktåpninger og rømningshull i teiner',
    'Teiner som er satt ut til fangst av sjøkreps, kongekrabbe, taskekrabbe, snøkrabbe og annen krabbe skal ha rømningshull innmontert i samsvar med anvisningene i vedlegg 3.',
    'Kontroller at teinen har rømningshull montert i samsvar med vedlegg 3 til høstingsforskriften.',
)

RUSE_FORBUD = _item(
    'ruse_forbud_periode',
    'Forbud mot bruk av ruser i perioden 1. mai-30. september',
    HOSTING_LAW,
    '§ 30. Forbud mot bruk av ruser',
    'Det er forbudt å bruke ruser i tidsrommet fra og med 1. mai til og med 30. september. Forbudet gjelder ikke manntallsførte fiskere som fisker med ruser etter torsk med merkeregistrert fartøy for omsetning. Fiskeridirektoratet kan dispensere fra forbudet i første ledd for personer som deltar i ungdomsfiskeordningen og for undervisningsinstitusjoner, herunder leirskoler og naturskoler.',
    'Kontroller datoen. Ruser er som hovedregel forbudt fra 1. mai til og med 30. september, med bare de unntakene som følger av § 30.',
)

MARKING_COMMON = _item(
    'vak_merking',
    'Merking av vak / blåse / flyt / dobbe',
    HOSTING_LAW,
    '§ 66. Krav til merking',
    'Redskap som står i sjøen skal ha minst ett vak (blåse, flyt eller dobbe) som er tydelig merket med fartøyets registreringsmerke. Dersom det ikke brukes registreringspliktig fartøy, skal vaket være merket med eierens navn og adresse. Dersom det brukes flere vak, skal samtlige vak være merket som beskrevet. Det er ikke tillatt å bruke redskap som ikke har vak. Vaket og merket på vaket skal være godt synlig. Sanketeiner og samleposer som er satt for å oppbevare viltlevende marine ressurser i sjø skal være merket på tilsvarende måte.',
    'Kontroller at redskap som står i sjøen har vak, at vaket er godt synlig, og at merket er lesbart og korrekt.',
    supports_marker_positions=True,
)

MARKING_RECREATIONAL_TEINE_RUSE = _item(
    'teiner_ruser_merking_rekreasjon',
    'Merking av teiner og ruser i rekreasjonsfiske',
    HOSTING_LAW,
    '§ 67. Krav til merking av teiner og ruser i rekreasjonsfiske',
    'Teiner og ruser som er satt i sjøen fra fartøy som ikke er merkeregistrert eller fra land, skal være tydelig merket med eierens navn og adresse. Merket skal være lett synlig på redskapen. Dersom flere redskaper er satt i lenke, gjelder kravet om merking hvert enkelt redskap i lenken. Sanke- og samleteiner som står i sjøen for oppbevaring av skalldyr fanget i rekreasjonsfiske skal være merket på samme måte. Merking skal ikke foretas på de deler av en teine som er beregnet for å flyte opp til overflaten etter en tid i sjøen (flyteelement). Kravet til merking av teiner og ruser i bestemmelsen her gjelder i tillegg til kravet til merking av vak i § 66.',
    'Kontroller at hver teine eller ruse i rekreasjonsfiske er merket med navn og adresse på selve redskapet i tillegg til vaket.',
)

MARKING_OUTSIDE_BASELINE = _item(
    'garn_line_merke_utenfor_grunnlinjene',
    'Spesiell merking utenfor grunnlinjene',
    HOSTING_LAW,
    '§ 68. Spesielle merkebestemmelser utenfor grunnlinjene',
    'Garn- og lineredskap som står i sjøen utenfor grunnlinjene i Norges sjøterritorium og økonomiske sone skal være merket slik: Om dagen skal redskapet i hver ende ha bøyestang forsynt med radarreflektor eller flagg. Etter solnedgang skal det i hver ende av redskapet være bøye med refleksmidler og stang forsynt med lys slik at endebøyene angir redskapets posisjon og utstrekning.',
    'Kontroller merkingen dersom garn eller line står utenfor grunnlinjene. Endene skal være merket i samsvar med § 68.',
)

HUMMER_FREDNING_AREA = _item(
    'hummer_fredningsomrade_redskap',
    'Redskapsbruk i hummerfredningsområde',
    HUMMER_FREDNING_LAW,
    '§ 1 / § 1a / § 3',
    'Det er forbudt å fiske med andre redskaper enn håndsnøre, fiskestang, juksa, dorg eller snurpenot i fredningsområdene for hummer. Enkelte områder kan ha tidsavgrensede unntak eller særskilte grenser som fremgår av forskriften og kartvedleggene.',
    'Kontroller om posisjonen ligger i fredningsområde for hummer, og om valgt redskap er blant de redskapene som er tillatt i området.',
)

GENERIC_DOKUMENTASJON = _item(
    'dokumentasjon',
    'Dokumentasjon, identifikasjon og ansvarlig person/fartøy',
    'Fiskeridirektoratet / relevant særforskrift',
    'Registrering, tillatelse og identifikasjon',
    'Kontrollen skal avklare identitet, ansvarlig person eller fartøy, og om nødvendige registreringer, tillatelser og identifikasjonsopplysninger foreligger.',
    'Kontroller identitet og at påkrevde opplysninger og registreringer foreligger for det valgte fiskeriet.',
)

GENERIC_REPORTING = _item(
    'rapportering',
    'Rapportering og sporbarhet',
    'Fiskeridirektoratet / relevant særforskrift',
    'Rapporteringskrav',
    'Kontrollen skal avklare om rapportering, dokumentasjon og eventuell sporbarhet er i orden for valgt kommersielt fiskeri.',
    'Kontroller at kommersielt fiskeri oppfyller krav til rapportering og sporbarhet.',
)

GENERIC_AREA = _item(
    'omradekrav',
    'Områdekrav og områdestatus',
    AREA_LAW,
    'Fredningsområder, forbudsområder og stengte felt',
    'Kontroller om redskapet eller fisket skjer i fredningsområde, forbudsområde, stengt felt, nullfiskeområde eller annet område med særregler. Områdetreff skal alltid vurderes opp mot valgt art, valgt redskap og dato.',
    'Kontroller om området har fredning, forbud eller særregler som gjør fisket ulovlig eller stiller tilleggskrav.',
)

GENERIC_TEINE = _item(
    'teine_kontroll',
    'Generell kontroll av teine',
    HOSTING_LAW,
    '§ 66 og relevante særbestemmelser',
    'Teinefiske skal vurderes opp mot generelle merkekrav, områdestatus, antall redskap og eventuelle tekniske krav til rømningshull, fluktåpninger eller særskilt oppmerking.',
    'Kontroller vak, merking, oppsett, områdestatus og tekniske krav til teinen.',
)

GENERIC_GARN = _item(
    'garn_kontroll',
    'Generell kontroll av garn',
    HOSTING_LAW,
    '§ 66 og § 68 samt relevante særbestemmelser',
    'Garnfiske skal vurderes opp mot merkekrav, endemerking, områdestatus og eventuelle artsspesifikke særregler.',
    'Kontroller vak, endemerking, identifikasjon, oppsett og områdestatus for garnlenken.',
)

GENERIC_LINE = _item(
    'line_kontroll',
    'Generell kontroll av line',
    HOSTING_LAW,
    '§ 66 og § 68 samt relevante særbestemmelser',
    'Linefiske skal vurderes opp mot merkekrav, endemerking, områdestatus og eventuelle artsspesifikke særregler.',
    'Kontroller vak, endemerking, identifikasjon, oppsett og områdestatus for lineredskapet.',
)

GENERIC_RUSE = _item(
    'ruse_kontroll',
    'Generell kontroll av ruse',
    HOSTING_LAW,
    '§ 66, § 67 og § 30',
    'Rusefiske skal vurderes opp mot vakmerking, redskapsmerking i rekreasjonsfiske, områdestatus og eventuelle periodeforbud.',
    'Kontroller vak, merking på selve rusen, områdestatus og om datoen ligger i forbudsperioden for ruser.',
)

GENERIC_HANDHELD = _item(
    'handredskap_omrade',
    'Område- og artskontroll for håndredskap',
    AREA_LAW,
    'Områderegulering og artsspesifikke regler',
    'Håndsnøre, dorg og jukse er ofte tillatt i områder der faststående redskap er forbudt, men må likevel kontrolleres opp mot områderegler, fredningstid og artsspesifikke bestemmelser.',
    'Kontroller om området tillater valgt håndredskap, og om arten kan fiskes på aktuell dato og i aktuelt område.',
)

GENERIC_TRAWL = _item(
    'tral_kontroll',
    'Generell kontroll av trål / snurrevad / not',
    GENERIC_ART_LAW,
    'Relevant deltakeradgang, område- og rapporteringsregel',
    'Kommersielt fiske med trål, snurrevad, not eller ringnot skal kontrolleres opp mot tillatelse, rapportering, områdestatus og artsspesifikke reguleringer.',
    'Kontroller tillatelse, rapportering, sporbarhet og områdestatus for valgt redskap.',
)

TORSK_OSLOFJORD = _item(
    'torsk_oslofjord',
    'Særregler for torsk i Oslofjorden',
    AREA_LAW,
    'Oslofjorden – fritidsfiskeregler / nullfiskeområder',
    'I Oslofjorden gjelder særregler. Kartlagene for Oslofjorden angir blant annet forbud og særskilte begrensninger for torsk og for enkelte redskap i fritidsfiske.',
    'Kontroller om posisjonen ligger i Oslofjorden og om særreglene for torsk eller redskap gjør fisket ulovlig.',
)


def _species_item(species: str) -> dict[str, str]:
    guidance = SPECIES_GUIDANCE.get(_norm(species), 'Kontroller eventuelle artsspesifikke bestemmelser om minstemål, område, periode, rapportering og omsetning.')
    return _item(
        f'art_{_norm(species).replace(" ", "_") or "generisk"}',
        f'Artsspesifikke regler for {species or "valgt art"}',
        GENERIC_ART_LAW,
        'Artsspesifikke bestemmelser',
        guidance,
        guidance,
    )


AREA_GENERIC_STATUS_ITEMS = {
    'fredningsområde': _item(
        'fredningsomrade_status',
        'Posisjon i fredningsområde / verneområde',
        AREA_LAW,
        'Fredningsområde / verneområde',
        'Posisjonen ligger i et frednings- eller verneområde. Kontroller om valgt art, valgt redskap og dato er tillatt i området.',
        'Posisjonen ligger i et frednings- eller verneområde. Vurder art, redskap og dato opp mot områdets regler.',
    ),
    'stengt område': _item(
        'stengt_omrade_status',
        'Posisjon i stengt område / nullfiskeområde',
        AREA_LAW,
        'Stengt område / nullfiskeområde',
        'Posisjonen ligger i et område der fisket er helt eller delvis stengt. Kontroller om fisket er forbudt eller bare tillatt med bestemte redskap og arter.',
        'Posisjonen ligger i et stengt område eller nullfiskeområde. Kontroller om fisket er helt forbudt eller bare tillatt på bestemte vilkår.',
    ),
    'maksimalmål område': _item(
        'maksimalmal_omrade',
        'Posisjon i maksimalmålområde for hummer',
        AREA_LAW,
        'Maksimalmålområde for hummer',
        'Posisjonen ligger i område med maksimalmål for hummer. Kontroller om fangst over maksimalmål skal gjenutsettes i tillegg til øvrige hummerregler.',
        'Posisjonen er i maksimalmålområde for hummer. Kontroller både minstemål og maksimalmål.',
    ),
    'regulert område': _item(
        'regulert_omrade',
        'Posisjon i område med særregler',
        AREA_LAW,
        'Regulert område',
        'Posisjonen ligger i område med særlige reguleringer. Kontroller hvilke redskap og arter som er tillatt i området.',
        'Posisjonen ligger i område med særregler. Kontroller hvilket redskap og hvilken art som er tillatt.',
    ),
}


def _clone(item: dict[str, str]) -> dict[str, str]:
    return dict(item)



def _unique(items: List[dict[str, str]]) -> List[dict[str, str]]:
    seen = set()
    out: List[dict[str, str]] = []
    for item in items:
        key = item.get('key')
        if key in seen:
            continue
        seen.add(key)
        out.append(item)
    return out



def _date_note(control_date: str | None, item: dict[str, str], latitude: float | None = None) -> dict[str, str]:
    dt = _parse_date(control_date)
    if not dt:
        return item
    clone = dict(item)
    if clone['key'] == 'hummer_periode':
        season_start = datetime(dt.year, 10, 1, 8, 0)
        south_vestland = latitude is None or float(latitude) <= 61.5
        season_end = datetime(dt.year, 11, 30, 23, 59) if south_vestland else datetime(dt.year, 12, 31, 23, 59)
        in_window = season_start <= dt <= season_end
        clone['status'] = 'godkjent' if in_window else 'avvik'
        if in_window:
            clone['notes'] = 'Kontrolldato ligger innenfor tillatt hummerperiode for valgt område/landsdel.'
        else:
            clone['notes'] = 'Kontrolldato ligger utenfor tillatt hummerperiode etter § 8 og skal vurderes som avvik.'
    elif clone['key'] == 'ruse_forbud_periode':
        in_ban = (dt.month > 5 and dt.month < 9) or (dt.month == 5 and dt.day >= 1) or (dt.month == 9 and dt.day <= 30)
        clone['status'] = 'avvik' if in_ban else 'godkjent'
        clone['notes'] = 'Kontrolldato ligger i forbudsperioden 1. mai-30. september.' if in_ban else 'Kontrolldato ligger utenfor den ordinære forbudsperioden i § 30.'
    return clone



def _gear_items(control_type: str, species: str, gear: str) -> List[dict[str, str]]:
    ct = 'kommersiell' if _norm(control_type).startswith('kom') else 'fritidsfiske'
    gear_n = _norm(gear)
    species_n = _norm(species)
    items: List[dict[str, str]] = []

    is_storage_gear = gear_n in {'samleteine / sanketeine', 'samleteine/sanketeine', 'sanketeine', 'samleteine'}

    if gear_n in {'teine', 'samleteine / sanketeine', 'samleteine/sanketeine', 'sanketeine', 'samleteine'}:
        if species_n == 'hummer' and is_storage_gear:
            items.append(HUMMER_MERKING)
        else:
            items.append(MARKING_COMMON)
            if ct == 'fritidsfiske':
                items.append(MARKING_RECREATIONAL_TEINE_RUSE)
            if ct == 'kommersiell':
                items.append(GENERIC_TEINE)
        if is_storage_gear and species_n == 'hummer':
            items.append(HUMMER_OPPBEVARING_DESEMBER)
        elif species_n in {'krabbe', 'taskekrabbe'}:
            items.append(KRABBE_FLUKT_KOMM if ct == 'kommersiell' else KRABBE_FLUKT_FRITID)
            items.append(KRABBE_RATENTRAD)
        elif species_n in {'kongekrabbe', 'snøkrabbe', 'sjøkreps'}:
            items.append(KRABBE_RATENTRAD)
        elif species_n != 'hummer' and not is_storage_gear:
            items.append(KRABBE_RATENTRAD)
    elif gear_n == 'garn':
        items.extend([MARKING_COMMON, GENERIC_GARN])
        if species_n == 'blåkveite':
            items.append(MARKING_OUTSIDE_BASELINE)
    elif gear_n == 'line':
        items.extend([MARKING_COMMON, GENERIC_LINE])
        items.append(MARKING_OUTSIDE_BASELINE)
    elif gear_n == 'ruse':
        items.extend([MARKING_COMMON, GENERIC_RUSE, RUSE_FORBUD])
        if ct == 'fritidsfiske':
            items.append(MARKING_RECREATIONAL_TEINE_RUSE)
    elif gear_n in {'håndsnøre', 'dorg', 'jukse'}:
        items.append(GENERIC_HANDHELD)
    elif gear_n in {'trål', 'pelagisk trål', 'snurrevad', 'not', 'ringnot'}:
        items.append(GENERIC_TRAWL)
        if gear_n in {'not', 'ringnot'}:
            items.append(MARKING_COMMON)
    else:
        items.append(GENERIC_DOKUMENTASJON)

    return items



def _species_items(
    control_type: str,
    species: str,
    gear: str,
    *,
    area_status: str = '',
    area_name: str = '',
    area_notes: str = '',
    lat: float | None = None,
    lng: float | None = None,
) -> List[dict[str, str]]:
    ct = 'kommersiell' if _norm(control_type).startswith('kom') else 'fritidsfiske'
    species_n = _norm(species)
    gear_n = _norm(gear)
    items: List[dict[str, Any]] = [_species_item(species)] if species and ct == 'kommersiell' else []
    is_storage_gear = gear_n in {'samleteine / sanketeine', 'samleteine/sanketeine', 'sanketeine', 'samleteine'}

    if species_n == 'hummer':
        items.extend([
            HUMMER_DELTAGERNR,
            HUMMER_PERIODE,
            HUMMER_ROGN,
            HUMMER_UTSETTING,
        ])
        if hummer_max_size_applies(area_status=area_status, area_name=area_name, area_notes=area_notes, lat=lat, lng=lng):
            length_item = _clone(HUMMER_LENGDEKRAV)
            length_item['notes'] = 'Lengdekravet er samlet i ett kontrollpunkt fordi kontrollstedet ligger på strekningen fra grensen mot Sverige til og med Agder, eller fordi kartgrunnlaget viser maksimalmålområde. Registrerte målinger vurderes automatisk mot både minstemål og maksimalmål.'
            items.append(length_item)
        else:
            items.append(_clone(HUMMER_MINSTEMAL))
        if is_storage_gear:
            items.extend([HUMMER_MERKING, HUMMER_OPPBEVARING_DESEMBER])
        else:
            items.extend([
                HUMMER_FLUKT,
                HUMMER_RATENTRAD,
                HUMMER_ANTALL_KOMM if ct == 'kommersiell' else HUMMER_ANTALL_FRITID,
                HUMMER_ROKTING,
            ])
    elif species_n in {'krabbe', 'taskekrabbe'} and gear_n in {'teine', 'samleteine / sanketeine', 'samleteine/sanketeine', 'sanketeine', 'samleteine'}:
        items.extend([KRABBE_FLUKT_KOMM if ct == 'kommersiell' else KRABBE_FLUKT_FRITID, KRABBE_RATENTRAD])
    elif species_n in {'kongekrabbe', 'snøkrabbe', 'sjøkreps'} and gear_n == 'teine':
        items.append(KRABBE_RATENTRAD)
    elif species_n == 'torsk':
        items.append(TORSK_OSLOFJORD)
        if gear_n == 'ruse':
            items.append(RUSE_FORBUD)

    min_item = minimum_size_item(species)
    if species_n != 'hummer' and min_item and min_item.get('key') not in {str(row.get('key') or '') for row in items}:
        items.append(min_item)
    return items



def recommend_area_violation(area_status: str = '', area_name: str = '', species: str = '', gear_type: str = '', notes: str = '') -> dict[str, Any] | None:
    status_n = _norm(area_status)
    area_name = str(area_name or '').strip()
    notes = str(notes or '').strip()
    species_n = _norm(species)
    gear_n = _norm(gear_type)
    area_blob = ' '.join(part for part in [_norm(area_name), _norm(notes), status_n] if part)

    if not status_n or status_n == 'normalt område':
        return None

    if 'fredningsområde' in status_n and ('hummer' in _norm(area_name) or species_n == 'hummer'):
        item = _clone(HUMMER_FREDNING_AREA)
        zone_name = area_name or 'hummerfredningsområde'
        if gear_n and gear_n not in ALLOWED_GEARS_HUMMER_FREDNING:
            item['status'] = 'avvik'
            item['summary_text'] = f'Ved kontrollstedet ble {gear_type or "redskap"} observert og kontrollert i {zone_name}. Dette redskapet er ikke tillatt i hummerfredningsområdet.'
            item['notes'] = f'Ved kontrollstedet står redskapet i {zone_name}, registrert som hummerfredningsområde. Valgt redskap ({gear_type or "redskap"}) er ikke tillatt i dette området.'
            message = f'Mulig lovbrudd: {gear_type or "redskap"} i hummerfredningsområde.'
        else:
            item['status'] = 'ikke kontrollert'
            item['summary_text'] = f'Ved kontrollstedet ble redskap kontrollert i {zone_name}. Det må kontrolleres om valgt redskap er tillatt i hummerfredningsområdet.'
            item['notes'] = f'Ved kontrollstedet ligger redskapet i {zone_name}, registrert som hummerfredningsområde. Det må kontrolleres om valgt redskap er tillatt i området.'
            message = 'Posisjonen ligger i hummerfredningsområde. Kontroller om valgt redskap er tillatt.'
        if notes:
            item['notes'] += f' Kartgrunnlag: {notes}'
        return {'item': item, 'message': message}

    if 'stengt område' in status_n or 'nullfiske' in status_n:
        item = _clone(AREA_GENERIC_STATUS_ITEMS['stengt område'])
        item['status'] = 'avvik'
        item['label'] = f'Valgt redskap i {area_name or "stengt område"}'
        item['summary_text'] = f'Ved kontrollstedet ble {gear_type or "redskap"} observert og kontrollert i {area_name or area_status}. Området er registrert som stengt område/nullfiskeområde.'
        item['notes'] = f'Ved kontrollstedet står redskapet i {area_name or area_status}, registrert som stengt område eller nullfiskeområde. Valgt redskap ({gear_type or "ukjent redskap"}) er forbudt eller særskilt regulert i dette området.'
        if notes:
            item['notes'] += f' Kartgrunnlag: {notes}'
        return {'item': item, 'message': f'Mulig lovbrudd: {gear_type or "redskap"} i stengt område/nullfiskeområde.'}

    if 'maksimalmål område' in status_n and species_n == 'hummer':
        item = _clone(AREA_GENERIC_STATUS_ITEMS['maksimalmål område'])
        item['summary_text'] = f'Ved kontrollstedet ble hummerredskap kontrollert i {area_name or area_status}. Området er registrert som maksimalmålområde.'
        item['notes'] = f'Ved kontrollstedet ligger redskapet i {area_name or area_status}, registrert som maksimalmålområde for hummer. Maksimalmål må kontrolleres i tillegg til øvrige hummerregler.'
        return {'item': item, 'message': 'Maksimalmålområde for hummer truffet.'}

    if 'regulert område' in status_n:
        item = _clone(AREA_GENERIC_STATUS_ITEMS['regulert område'])
        item['summary_text'] = f'Ved kontrollstedet ble {gear_type or "redskap"} observert og kontrollert i {area_name or area_status}. Området er registrert som regulert område.'
        item['notes'] = f'Ved kontrollstedet ligger redskapet i {area_name or area_status}, registrert som regulert område. For valgt art og redskap gjelder særskilte regler eller begrensninger i området.'
        return {'item': item, 'message': 'Posisjonen ligger i område med særregler.'}

    if 'fredningsområde' in status_n:
        item = _clone(AREA_GENERIC_STATUS_ITEMS['fredningsområde'])
        item['summary_text'] = f'Ved kontrollstedet ble {gear_type or "redskap"} observert og kontrollert i {area_name or area_status}. Området er registrert som fredningsområde.'
        item['notes'] = f'Ved kontrollstedet ligger redskapet i {area_name or area_status}, registrert som fredningsområde. Det må kontrolleres om valgt art og redskap er tillatt i området.'
        return {'item': item, 'message': 'Posisjonen ligger i fredningsområde.'}

    return None



def get_rule_bundle(
    control_type: str,
    species: str,
    gear_type: str,
    area_status: str = '',
    control_date: str = '',
    area_name: str = '',
    area_notes: str = '',
    lat: float | None = None,
    lng: float | None = None,
) -> Dict[str, Any]:
    is_commercial = _norm(control_type).startswith('kom')
    control_label = 'Kommersiell' if is_commercial else 'Fritidsfiske'
    items: List[dict[str, str]] = []

    if is_commercial:
        items.append(GENERIC_DOKUMENTASJON)

    items.extend(_gear_items(control_type, species, gear_type))
    items.extend(_species_items(
        control_type,
        species,
        gear_type,
        area_status=area_status,
        area_name=area_name,
        area_notes=area_notes,
        lat=lat,
        lng=lng,
    ))

    rec = recommend_area_violation(area_status=area_status, area_name=area_name, species=species, gear_type=gear_type, notes=area_notes)
    if rec and rec.get('item'):
        items.append(rec['item'])
    else:
        status_n = _norm(area_status)
        if status_n and status_n not in {'ingen treff', 'normalt område'}:
            for key, item in AREA_GENERIC_STATUS_ITEMS.items():
                if key in status_n:
                    items.append(item)
                    break

    items = [_date_note(control_date, _clone(item), latitude=lat) for item in _unique(items)]

    description = 'Appen viser bare kontrollpunkter som er relevante for valgt kontrolltype, art, redskap, dato, registrert områdestatus og tilgjengelig posisjon.'
    if rec and rec.get('message'):
        description += f' Områdevarsel: {rec["message"]}'

    title = f'Kontrollpunkter for {control_label.lower()} - {species or "art ikke valgt"} / {gear_type or "redskap ikke valgt"}'
    sources = [
        {'name': HUMMER_LAW, 'ref': HUMMER_LAW_REF, 'url': 'https://lovdata.no/forskrift/2021-12-23-3890'},
        {'name': HOSTING_LAW, 'ref': HOSTING_LAW_REF, 'url': 'https://lovdata.no/forskrift/2021-12-23-3910'},
        {'name': HUMMER_FREDNING_LAW, 'ref': HUMMER_FREDNING_REF, 'url': 'https://lovdata.no/forskrift/2006-07-06-883'},
        {'name': 'Fiskeridirektoratet kartportal', 'ref': 'Frednings- og forbudsområder', 'url': 'https://portal.fiskeridir.no/portal/apps/webappviewer/index.html?id=ea6c536f760548fe9f56e6edcc4825d8'},
    ]
    if _norm(species) == 'hummer':
        sources.append({'name': 'Fiskeridirektoratet', 'ref': 'Registrerte hummarfiskarar', 'url': 'https://www.fiskeridir.no/statistikk-tall-og-analyse/data-og-statistikk-om-turist--og-fritidsfiske/registrerte-hummarfiskarar'})
    return {'title': title, 'description': description, 'items': items, 'sources': sources}
