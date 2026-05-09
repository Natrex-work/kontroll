from __future__ import annotations

from typing import Any

import requests

from ..config import settings
from ..logging_setup import get_logger

logger = get_logger(__name__)


def sms_configured() -> bool:
    provider = str(settings.sms_provider or '').strip().lower()
    if provider == 'twilio':
        return bool(
            settings.twilio_account_sid
            and settings.twilio_auth_token
            and (settings.twilio_from_number or settings.twilio_messaging_service_sid)
        )
    return False


def send_sms(to_number: str, body: str) -> dict[str, Any]:
    provider = str(settings.sms_provider or '').strip().lower()
    if provider != 'twilio':
        raise RuntimeError('SMS-leverandør er ikke konfigurert. Sett KV_SMS_PROVIDER=twilio og Twilio-variabler i Render.')
    if not sms_configured():
        raise RuntimeError('SMS/2-trinnskode er ikke konfigurert. Sett TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN og TWILIO_FROM_NUMBER eller TWILIO_MESSAGING_SERVICE_SID i Render.')

    url = f'https://api.twilio.com/2010-04-01/Accounts/{settings.twilio_account_sid}/Messages.json'
    data = {'To': to_number, 'Body': body}
    if settings.twilio_messaging_service_sid:
        data['MessagingServiceSid'] = settings.twilio_messaging_service_sid
    else:
        data['From'] = settings.twilio_from_number

    response = requests.post(
        url,
        data=data,
        auth=(settings.twilio_account_sid, settings.twilio_auth_token),
        timeout=15,
    )
    if response.status_code >= 400:
        try:
            error_payload = response.json()
            message = error_payload.get('message') or response.text
        except Exception:
            message = response.text
        raise RuntimeError(f'SMS kunne ikke sendes: {message}')
    try:
        payload = response.json()
    except Exception:
        payload = {}
    return {'provider': 'twilio', 'sid': payload.get('sid'), 'status': payload.get('status')}


def send_login_code(to_number: str, code: str) -> dict[str, Any]:
    message = f'Din innloggingskode til Minfiskerikontroll er {code}. Koden er gyldig i {max(1, settings.otp_ttl_seconds // 60)} minutter.'
    if sms_configured():
        return send_sms(to_number, message)
    if settings.otp_dev_log_codes:
        logger.warning('Utviklingsmodus uten SMS: innloggingskode til %s er %s', to_number, code)
        return {'provider': 'dev-log', 'status': 'logged'}
    raise RuntimeError('SMS/2-trinnskode er ikke konfigurert på serveren. Kontakt admin og sett Twilio-miljøvariabler i Render.')


def send_user_invitation(to_number: str, full_name: str, password: str, login_url: str = '') -> dict[str, Any]:
    """Send temporary password to a newly created user via SMS.

    The admin can opt to send the invitation directly so they don't need to
    relay credentials manually. The message is short by design — the user
    receives a separate OTP code on first login as well.
    """
    name_part = (full_name.split()[0] + ', ') if full_name else ''
    url_part = f' Logg inn: {login_url}' if login_url else ''
    message = (
        f'{name_part}du har fått tilgang til Minfiskerikontroll. '
        f'Foreløpig passord: {password}'
        f'{url_part} '
        f'Bytt passord etter første innlogging.'
    )
    if sms_configured():
        return send_sms(to_number, message)
    if settings.otp_dev_log_codes:
        logger.warning('Utviklingsmodus uten SMS: invitasjonsmelding til %s ville vært: %s', to_number, message)
        return {'provider': 'dev-log', 'status': 'logged'}
    raise RuntimeError('SMS er ikke konfigurert på serveren.')
