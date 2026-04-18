from __future__ import annotations

import argparse
import sys

from app import db
from app.auth import hash_password
from app.services.bootstrap_service import initialize_application_data


def create_admin(args: argparse.Namespace) -> int:
    initialize_application_data()
    existing = db.get_user_by_email(args.email)
    if existing:
        print(f'Brukeren {args.email} finnes allerede.', file=sys.stderr)
        return 1
    user_id = db.create_user(
        email=args.email,
        full_name=args.name,
        password_hash=hash_password(args.password),
        role='admin',
        case_prefix=args.case_prefix,
    )
    db.record_audit(user_id, 'create_admin_cli', 'user', user_id, {'email': args.email})
    print(f'Opprettet administrator {args.email} med id {user_id}.')
    return 0


parser = argparse.ArgumentParser(description='Administrasjon for Fiskerikontroll')
sub = parser.add_subparsers(dest='command', required=True)

create_admin_parser = sub.add_parser('create-admin', help='Opprett første administrator')
create_admin_parser.add_argument('--email', required=True)
create_admin_parser.add_argument('--name', required=True)
create_admin_parser.add_argument('--password', required=True)
create_admin_parser.add_argument('--case-prefix', default='LBHN')
create_admin_parser.set_defaults(func=create_admin)


if __name__ == '__main__':
    args = parser.parse_args()
    raise SystemExit(args.func(args))
