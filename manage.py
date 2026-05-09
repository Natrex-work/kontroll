from __future__ import annotations

import argparse
import getpass
import sys

from app import db
from app.auth import hash_password
from app.validation import validate_case_prefix, validate_email, validate_password


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

    args = parser.parse_args(argv)
    return int(args.func(args))


if __name__ == '__main__':
    raise SystemExit(main(sys.argv[1:]))
