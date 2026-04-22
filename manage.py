from __future__ import annotations

import argparse
import getpass
import sys

from app import db
from app.auth import hash_password
from app.config import BASE_DIR, settings
from app.validation import validate_case_prefix, validate_email, validate_password


def validate_config(args: argparse.Namespace) -> int:
    problems: list[str] = []
    warnings: list[str] = []

    production_mode = settings.production_mode or bool(args.production)

    if production_mode and settings.session_secret == 'dev-session-secret-change-me':
        problems.append('SESSION_SECRET bruker fortsatt standard utviklingsverdi.')
    if production_mode and not settings.session_https_only:
        problems.append('KV_SESSION_HTTPS_ONLY er ikke aktivert.')
    if production_mode and (not settings.allowed_hosts or '*' in settings.allowed_hosts):
        problems.append('KV_ALLOWED_HOSTS er ikke satt eksplisitt.')

    if settings.bootstrap_admin_password:
        try:
            validate_password(settings.bootstrap_admin_password)
        except Exception as exc:
            detail = getattr(exc, 'detail', str(exc))
            problems.append(f'KV_BOOTSTRAP_ADMIN_PASSWORD er ugyldig: {detail}')
    elif settings.bootstrap_admin_email or settings.bootstrap_admin_name:
        warnings.append('Bootstrap-admin er bare delvis satt. Fyll ut alle KV_BOOTSTRAP_ADMIN_* feltene eller fjern dem.')
    elif not db.list_users():
        warnings.append('Ingen bootstrap-admin er satt og databasen ser tom ut.')

    if settings.render_runtime and not settings.render_external_hostname:
        warnings.append('RENDER=true men RENDER_EXTERNAL_HOSTNAME mangler.')
    if production_mode and str(settings.db_path).startswith(str(BASE_DIR)):
        warnings.append('KV_DB_PATH peker til appmappen. Bruk Render-disk eller database for varige data.')

    print('KV Kontroll konfigurasjonssjekk')
    print(f'- production_mode: {production_mode}')
    print(f'- render_runtime: {settings.render_runtime}')
    print(f'- server_url: {settings.server_url or "-"}')
    print(f'- render_external_hostname: {settings.render_external_hostname or "-"}')
    print(f'- allowed_hosts: {", ".join(settings.allowed_hosts) if settings.allowed_hosts else "(ingen)"}')
    print(f'- db_path: {settings.db_path}')
    print(f'- upload_dir: {settings.upload_dir}')
    print(f'- generated_dir: {settings.generated_dir}')

    if warnings:
        print('\nAdvarsler:')
        for item in warnings:
            print(f'- {item}')

    if problems:
        print('\nFeil:')
        for item in problems:
            print(f'- {item}')
        return 1

    print('\nOK: ingen blokkerende konfigurasjonsfeil funnet.')
    return 0


def create_admin(args: argparse.Namespace) -> int:
    db.init_db()
    email = validate_email(args.email)
    full_name = str(args.name or '').strip()
    if not full_name:
        raise SystemExit('Navn mangler.')
    password = args.password or getpass.getpass('Passord: ')
    password = validate_password(password)
    prefix = validate_case_prefix(args.prefix or 'LBHN')
    existing = db.get_user_by_email(email)
    if existing:
        print(f'Bruker finnes allerede: {email}')
        return 0
    user_id = db.create_user(
        email=email,
        full_name=full_name,
        password_hash=hash_password(password),
        role='admin',
        permissions=list(db.DEFAULT_ADMIN_PERMISSIONS),
        last_complainant_name=full_name,
        last_witness_name=full_name,
        case_prefix=prefix,
        active=True,
    )
    db.record_audit(user_id, 'manage_create_admin', 'user', user_id, {'email': email})
    print(f'Opprettet administrator: {email}')
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description='Administrasjon for KV Kontroll')
    sub = parser.add_subparsers(dest='command', required=True)

    create = sub.add_parser('create-admin', help='Opprett første administrator')
    create.add_argument('--email', required=True)
    create.add_argument('--name', required=True)
    create.add_argument('--password')
    create.add_argument('--prefix', default='LBHN')
    create.set_defaults(func=create_admin)

    validate = sub.add_parser('validate-config', help='Sjekk produksjonsklar konfigurasjon')
    validate.add_argument('--production', action='store_true', help='Tving produksjonsregler i valideringen')
    validate.set_defaults(func=validate_config)

    args = parser.parse_args(argv)
    return int(args.func(args))


if __name__ == '__main__':
    raise SystemExit(main(sys.argv[1:]))
