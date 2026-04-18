from __future__ import annotations

import re
from pathlib import Path

from fastapi import HTTPException, UploadFile

from .config import settings

EMAIL_RE = re.compile(r'^[^@\s]+@[^@\s]+\.[^@\s]+$')
CASE_PREFIX_RE = re.compile(r'^[A-Z0-9]{2,8}$')
ALLOWED_UPLOAD_SUFFIXES = {
    '.png', '.jpg', '.jpeg', '.gif', '.webp', '.bmp',
    '.wav', '.mp3', '.m4a', '.ogg', '.webm', '.mp4',
    '.pdf', '.txt', '.csv',
}
ALLOWED_UPLOAD_MIME_PREFIXES = ('image/', 'audio/', 'video/', 'application/pdf', 'text/')


def normalize_email(value: str | None) -> str:
    return str(value or '').strip().lower()


def validate_email(value: str | None) -> str:
    email = normalize_email(value)
    if not email or not EMAIL_RE.match(email):
        raise HTTPException(status_code=400, detail='Ugyldig e-postadresse.')
    return email


def validate_password(value: str | None, minimum_length: int = 8) -> str:
    password = str(value or '').strip()
    if len(password) < minimum_length:
        raise HTTPException(status_code=400, detail=f'Passordet må være minst {minimum_length} tegn langt.')
    return password


def validate_role(value: str | None, allowed_roles: list[str] | tuple[str, ...]) -> str:
    role = str(value or '').strip()
    if role not in allowed_roles:
        raise HTTPException(status_code=400, detail='Ugyldig rolle.')
    return role


def validate_case_prefix(value: str | None, fallback: str = 'LBHN') -> str:
    prefix = str(value or fallback).strip().upper() or fallback
    if not CASE_PREFIX_RE.match(prefix):
        raise HTTPException(status_code=400, detail='Saksnummer-prefix må være 2-8 tegn og kun bestå av bokstaver/tall.')
    return prefix


def validate_upload_file(file: UploadFile) -> None:
    filename = str(file.filename or '').strip()
    if not filename:
        raise HTTPException(status_code=400, detail='Filen mangler filnavn.')
    suffix = Path(filename).suffix.lower()
    if suffix and suffix not in ALLOWED_UPLOAD_SUFFIXES:
        raise HTTPException(status_code=400, detail='Filtypen støttes ikke i denne demoen.')
    content_type = str(file.content_type or '')
    if content_type and not any(content_type.startswith(prefix) for prefix in ALLOWED_UPLOAD_MIME_PREFIXES):
        raise HTTPException(status_code=400, detail='MIME-type støttes ikke i denne demoen.')


def validate_saved_file_size(size_bytes: int) -> None:
    max_bytes = settings.max_upload_size_mb * 1024 * 1024
    if size_bytes > max_bytes:
        raise HTTPException(status_code=400, detail=f'Filen er for stor. Maks tillatt størrelse er {settings.max_upload_size_mb} MB.')
