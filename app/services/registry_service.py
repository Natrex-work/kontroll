from __future__ import annotations

from typing import Any

from .. import db, live_sources, registry


def _dedupe_candidates(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    deduped: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str, str]] = set()
    for row in rows or []:
        item = dict(row or {})
        key = (
            registry._norm(item.get('name')),
            ''.join(ch for ch in str(item.get('phone') or '') if ch.isdigit())[-8:],
            registry._compact(item.get('participant_no') or item.get('hummer_participant_no')),
            registry._compact(item.get('vessel_reg')),
        )
        if key in seen:
            continue
        seen.add(key)
        deduped.append(item)
    return deduped


def _merge_directory_contact(person: dict[str, Any], *, phone_lookup: str = '', name_lookup: str = '', address_lookup: str = '') -> tuple[dict[str, Any], dict[str, Any]]:
    item = dict(person or {})
    phone_value = ''.join(ch for ch in str(item.get('phone') or phone_lookup or '') if ch.isdigit())[-8:]
    if not phone_value:
        return item, {'found': False, 'message': '', 'candidates': []}
    try:
        # 1881/Gulesider er sekund\u00e6rkilde og brukes bare ved mobilnummer.
        # Navn/adresse fra OCR eller offisielle registre skal ikke overstyres av katalogtekst.
        directory_result = live_sources.lookup_directory_candidates(phone=phone_value, name='', address='')
    except Exception as exc:
        return item, {'found': False, 'message': f'Katalogs\u00f8k utilgjengelig: {exc}', 'candidates': []}

    if not directory_result.get('found'):
        return item, directory_result

    directory_person = dict(directory_result.get('person') or {})
    source_name = str(item.get('source') or '').strip().lower()
    prefer_directory = source_name in {
        'hummerliste',
        'lokal hummerliste',
        'lokal person-/fart\u00f8yliste',
        'fiskeridirektoratet - registrerte hummarfiskarar',
    }
    if directory_person.get('address'):
        address, post_place = registry._split_address_post_place(directory_person.get('address'))
        if address and (prefer_directory or not item.get('address')):
            item['address'] = address
        if post_place and (prefer_directory or not item.get('post_place')):
            item['post_place'] = post_place
    if directory_person.get('phone') and (prefer_directory or not item.get('phone')):
        item['phone'] = directory_person.get('phone')
    if not item.get('source_url') and directory_person.get('source_url'):
        item['source_url'] = directory_person.get('source_url')
    return item, directory_result


def _resolve_lookup_address(address: str = '', post_place: str = '', hints: dict[str, str] | None = None) -> tuple[str, str, str]:
    hints = hints or {}
    base_address = str(address or hints.get('address') or '').strip()
    base_post_place = str(post_place or hints.get('post_place') or '').strip()
    if base_address:
        split_address, split_post_place = registry._split_address_post_place(base_address)
        if split_address:
            base_address = split_address
        if split_post_place and not base_post_place:
            base_post_place = split_post_place
    combined = ', '.join(part for part in [base_address, base_post_place] if str(part or '').strip()).strip()
    return base_address, base_post_place, combined


def _merge_hummer_fields(person: dict[str, Any], hummer_person: dict[str, Any]) -> tuple[dict[str, Any], str]:
    item = dict(person or {})
    hummer_item = dict(hummer_person or {})
    participant_no = hummer_item.get('participant_no') or hummer_item.get('hummer_participant_no') or ''
    if participant_no and not item.get('hummer_participant_no'):
        item['hummer_participant_no'] = participant_no
    last_registered = hummer_item.get('last_registered_display') or hummer_item.get('last_registered_year') or hummer_item.get('registered_date_display') or ''
    if last_registered:
        item['hummer_last_registered'] = last_registered
    if hummer_item.get('name') and not item.get('name'):
        item['name'] = hummer_item.get('name')
    if hummer_item.get('fisher_type') and not item.get('fisher_type'):
        item['fisher_type'] = hummer_item.get('fisher_type')
    if hummer_item.get('source_url') and not item.get('source_url'):
        item['source_url'] = hummer_item.get('source_url')
    return item, last_registered


def _follow_up_hummer_lookup(person: dict[str, Any], initial_result: dict[str, Any], *, participant_lookup: str = '', live_hummer_error: str = '') -> tuple[dict[str, Any], list[dict[str, Any]], str]:
    person_name = str((person or {}).get('name') or '').strip()
    person_participant = str((person or {}).get('hummer_participant_no') or (person or {}).get('participant_no') or participant_lookup or '').strip()
    if not person_name and not person_participant:
        return initial_result or {'found': False, 'message': '', 'candidates': []}, [], live_hummer_error

    result = dict(initial_result or {'found': False, 'message': '', 'candidates': []})
    extra_candidates: list[dict[str, Any]] = []

    if not result.get('found'):
        follow_up_local = registry.lookup_hummer_participant(person_participant, person_name)
        if follow_up_local.get('found') or follow_up_local.get('candidates'):
            result = follow_up_local
            extra_candidates.extend(follow_up_local.get('candidates') or [])

    try:
        follow_up_live = live_sources.lookup_hummer_participant_live(person_participant, person_name)
    except Exception as exc:
        if not live_hummer_error:
            live_hummer_error = str(exc)
        follow_up_live = {'found': False, 'message': f'Live hummeroppslag utilgjengelig: {exc}', 'candidates': []}
    if follow_up_live.get('found') and not result.get('found'):
        result = follow_up_live
    extra_candidates.extend(follow_up_live.get('candidates') or [])
    return result, extra_candidates, live_hummer_error


def lookup_registry(*, phone: str = '', vessel_reg: str = '', radio_call_sign: str = '', name: str = '', address: str = '', post_place: str = '', tag_text: str = '', hummer_participant_no: str = '', lookup_mode: str = '') -> dict[str, Any]:
    combined_tag_text = ' '.join([tag_text or '', radio_call_sign or '']).strip()
    hints = registry.extract_tag_hints(combined_tag_text)

    phone_lookup = phone or hints.get('phone') or ''
    vessel_lookup = vessel_reg or hints.get('vessel_reg') or ''
    radio_lookup = radio_call_sign or hints.get('radio_call_sign') or ''
    name_lookup = name or hints.get('name') or ''
    address_lookup, post_place_lookup, combined_address_lookup = _resolve_lookup_address(address=address, post_place=post_place, hints=hints)
    participant_lookup = hummer_participant_no or hints.get('hummer_participant_no') or ''
    lookup_mode = str(lookup_mode or '').strip().lower()
    participant_only = lookup_mode in {'participant', 'deltaker', 'hummer_participant'} and bool(participant_lookup)
    phone_only = lookup_mode in {'phone', 'mobile', 'mobil'} and bool(phone_lookup)

    local_candidates = registry.search_people(
        phone=phone_lookup,
        vessel_reg=vessel_lookup,
        radio_call_sign=radio_lookup,
        name=name_lookup,
        tag_text=combined_tag_text,
        hummer_participant_no=participant_lookup,
    )
    case_candidates = db.lookup_people_from_cases(
        phone=phone_lookup,
        name=name_lookup,
        address=combined_address_lookup,
        vessel_reg=vessel_lookup,
        radio_call_sign=radio_lookup,
        hummer_participant_no=participant_lookup,
        exclude_case_id=None,
    )

    if participant_lookup or name_lookup:
        try:
            live_sources.refresh_hummer_registry_cache(force=False)
        except Exception:
            pass

    hummer_result = registry.lookup_hummer_participant(participant_lookup, name_lookup)
    hummer_candidates = list((hummer_result or {}).get('candidates') or [])
    live_hummer_error = ''
    live_hummer = {'found': False, 'message': '', 'candidates': []}
    if participant_lookup or name_lookup:
        try:
            live_hummer = live_sources.lookup_hummer_participant_live(participant_lookup, name_lookup)
        except Exception as exc:
            live_hummer_error = str(exc)
            live_hummer = {'found': False, 'message': f'Live hummeroppslag utilgjengelig: {exc}', 'candidates': []}
        if live_hummer.get('found') and not hummer_result.get('found'):
            hummer_result = live_hummer
        hummer_candidates.extend(live_hummer.get('candidates') or [])

    directory_result: dict[str, Any] = {'found': False, 'message': '', 'candidates': []}
    live_result: dict[str, Any] = {'found': False, 'message': '', 'candidates': []}

    person: dict[str, Any] | None = None
    source = 'local'
    candidates: list[dict[str, Any]] = []

    if participant_only and hummer_result and hummer_result.get('found'):
        hummer_person = dict(hummer_result.get('person') or {})
        split_address, split_post = registry._split_address_post_place(combined_address_lookup or address_lookup or '')
        person = {
            'name': hummer_person.get('name') or name_lookup or '',
            'address': split_address or combined_address_lookup or address_lookup or '',
            'post_place': hummer_person.get('post_place') or post_place_lookup or split_post or '',
            'phone': hummer_person.get('phone') or phone_lookup,
            'vessel_name': '',
            'vessel_reg': vessel_lookup,
            'hummer_participant_no': hummer_person.get('participant_no') or participant_lookup,
            'hummer_last_registered': hummer_person.get('last_registered_display') or hummer_person.get('last_registered_year') or '',
            'fisher_type': hummer_person.get('fisher_type') or '',
            'source': hummer_person.get('source') or 'Hummerliste',
            'match_reason': 'direkte deltakernummer',
            'source_url': hummer_person.get('source_url') or '',
        }
        source = 'hummer'
        candidates.extend(hummer_candidates)
        candidates.extend(case_candidates)
        candidates.extend(local_candidates)
    elif local_candidates:
        person = dict(local_candidates[0])
        source = 'local'
        candidates.extend(local_candidates)
        candidates.extend(case_candidates)
    elif case_candidates:
        person = dict(case_candidates[0])
        source = 'cases'
        candidates.extend(case_candidates)
    elif hummer_result and hummer_result.get('found'):
        hummer_person = dict(hummer_result.get('person') or {})
        hummer_address_lookup = combined_address_lookup or address_lookup or ''
        split_address, split_post = registry._split_address_post_place(hummer_address_lookup)
        person = {
            'name': hummer_person.get('name') or name_lookup or '',
            'address': split_address or hummer_address_lookup,
            'post_place': hummer_person.get('post_place') or post_place_lookup or split_post or '',
            'phone': hummer_person.get('phone') or phone_lookup,
            'vessel_name': '',
            'vessel_reg': vessel_lookup,
            'hummer_participant_no': hummer_person.get('participant_no') or participant_lookup,
            'hummer_last_registered': hummer_person.get('last_registered_display') or hummer_person.get('last_registered_year') or '',
            'fisher_type': hummer_person.get('fisher_type') or '',
            'source': hummer_person.get('source') or 'Hummerliste',
            'match_reason': 'hummerdeltakernummer / hummerliste',
            'source_url': hummer_person.get('source_url') or '',
        }
        source = 'hummer'
        candidates.extend(hummer_candidates)
        candidates.extend(local_candidates)
        candidates.extend(case_candidates)
    else:
        if phone_lookup and not participant_only:
            try:
                # 1881/Gulesider brukes bare sekundært ved mobilnummer.
                # OCR-tekst på bildet er primærkilde for navn/adresse.
                directory_result = live_sources.lookup_directory_candidates(phone=phone_lookup, name='', address='')
            except Exception as exc:
                directory_result = {'found': False, 'message': f'Katalogsøk utilgjengelig: {exc}', 'candidates': []}
        if directory_result and directory_result.get('found'):
            person = dict(directory_result.get('person') or {})
            source = 'directory'
            candidates.extend(directory_result.get('candidates') or [])
            candidates.extend(case_candidates)
            candidates.extend(local_candidates)
        elif (not phone_only and not participant_only) and (vessel_lookup or radio_lookup or (name_lookup and not participant_lookup)):
            try:
                live_result = live_sources.lookup_registry_live(
                    phone=phone_lookup,
                    vessel_reg=vessel_lookup,
                    name=name_lookup,
                    tag_text=' '.join([combined_tag_text, radio_lookup]).strip(),
                )
            except Exception as exc:
                live_result = {'found': False, 'message': f'Live oppslag utilgjengelig: {exc}', 'candidates': []}
            if live_result.get('found'):
                person = dict(live_result.get('person') or {})
                source = 'live'
                candidates.extend(live_result.get('candidates') or [])
                candidates.extend(case_candidates)
                candidates.extend(local_candidates)

    if person:
        person, directory_result = _merge_directory_contact(
            person,
            phone_lookup=phone_lookup,
            name_lookup=name_lookup,
            address_lookup=combined_address_lookup,
        )
        if (person.get('name') or person.get('hummer_participant_no') or person.get('participant_no')) and not hummer_result.get('found'):
            follow_up_result, follow_up_candidates, live_hummer_error = _follow_up_hummer_lookup(
                person,
                hummer_result,
                participant_lookup=participant_lookup,
                live_hummer_error=live_hummer_error,
            )
            if follow_up_result.get('found'):
                hummer_result = follow_up_result
            hummer_candidates.extend(follow_up_candidates)
        if hummer_result and hummer_result.get('found'):
            person, _ = _merge_hummer_fields(person, hummer_result.get('person') or {})
        candidates.extend(directory_result.get('candidates') or [])
        candidates.extend(hummer_candidates)
        return {
            'found': True,
            'person': person,
            'source': source,
            'hints': hints,
            'hummer_check': hummer_result,
            'directory_result': directory_result,
            'vipps_lookup_supported': False,
            'vipps_message': '',
            'candidates': _dedupe_candidates(candidates),
        }

    combined_candidates = []
    combined_candidates.extend((directory_result or {}).get('candidates') or [])
    combined_candidates.extend(local_candidates)
    combined_candidates.extend(case_candidates)
    combined_candidates.extend(hummer_candidates)
    combined_candidates.extend((live_result or {}).get('candidates') or [])

    message_parts = ['Ingen treff i tilgjengelige registre eller hummerliste.']
    if hummer_result and hummer_result.get('message'):
        message_parts.insert(0, str(hummer_result.get('message')).strip())
    if live_hummer_error:
        message_parts.append(f'Live hummeroppslag utilgjengelig: {live_hummer_error}')
    if directory_result and directory_result.get('message'):
        message_parts.append(str(directory_result.get('message')).strip())
    if live_result and live_result.get('message'):
        message_parts.append(str(live_result.get('message')).strip())
    message = ' '.join(part for part in message_parts if part).strip()
    return {
        'found': False,
        'message': message,
        'hints': hints,
        'hummer_check': hummer_result,
        'directory_result': directory_result,
        'vipps_lookup_supported': False,
        'vipps_message': '',
        'candidates': _dedupe_candidates(combined_candidates),
    }


def gear_summary(*, phone: str = '', name: str = '', address: str = '', species: str = '', gear_type: str = '', area_name: str = '', control_type: str = '', area_status: str = '', vessel_reg: str = '', radio_call_sign: str = '', hummer_participant_no: str = '', case_id: int | None = None) -> dict[str, Any]:
    return {
        'limit': None,
        'warning': '',
        'count_total': 0,
        'matches': [],
        'message': 'Tidligere registrerte teiner/redskap brukes ikke i oppsummering eller anmeldelsestekst.'
    }
