from __future__ import annotations

import smtplib
from email.message import EmailMessage
from pathlib import Path
from typing import Any

from ..config import settings
from .pdf_service import export_case_bundle


def smtp_configured() -> bool:
    return bool(settings.smtp_host and settings.smtp_from)


def send_case_package_email(case_id: int, case_row: dict[str, Any], user: dict[str, Any], *, to_address: str, subject: str = '', body: str = '') -> dict[str, Any]:
    recipient = str(to_address or '').strip()
    if '@' not in recipient or recipient.startswith('@') or recipient.endswith('@'):
        raise ValueError('Ugyldig e-postadresse.')
    if not smtp_configured():
        raise RuntimeError('E-post er ikke konfigurert på serveren. Sett KV_SMTP_HOST, KV_SMTP_FROM og eventuelt KV_SMTP_USERNAME/KV_SMTP_PASSWORD.')

    bundle_path = export_case_bundle(case_id, case_row, user)
    case_number = str(case_row.get('case_number') or f'Sak {case_id}').strip()
    msg = EmailMessage()
    msg['From'] = settings.smtp_from
    msg['To'] = recipient
    msg['Subject'] = subject.strip() or f'Anmeldelse med vedlegg - {case_number}'
    sender_name = str(user.get('full_name') or case_row.get('investigator_name') or '').strip()
    default_body = (
        f'Vedlagt følger anmeldelsespakke med dokumenter og vedlegg for {case_number}.\n\n'
        'Dette er sendt fra Minfiskerikontroll. Kontroller mottaker, innhold og eventuell journalføring i henhold til lokal rutine.\n'
    )
    if sender_name:
        default_body += f'\nAvsender: {sender_name}\n'
    msg.set_content(body.strip() or default_body)

    path = Path(bundle_path)
    with path.open('rb') as fh:
        msg.add_attachment(fh.read(), maintype='application', subtype='zip', filename=path.name)

    if settings.smtp_use_tls:
        client = smtplib.SMTP_SSL(settings.smtp_host, settings.smtp_port, timeout=30)
    else:
        client = smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=30)
    try:
        if settings.smtp_use_starttls and not settings.smtp_use_tls:
            client.starttls()
        if settings.smtp_username:
            client.login(settings.smtp_username, settings.smtp_password)
        client.send_message(msg)
    finally:
        try:
            client.quit()
        except Exception:
            pass
    return {'ok': True, 'recipient': recipient, 'bundle': path.name}
