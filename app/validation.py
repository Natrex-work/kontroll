from __future__ import annotations

import re
from pathlib import Path

from fastapi import HTTPException, UploadFile

from .config import settings

EMAIL_RE = re.compile(r'^[^@\s]+@[^@\s]+\.[^@\s]+$')
CASE_PREFIX_RE = re.compile(r'^[A-Z0-9]{2,8}$')
ALLOWED_UPLOAD_SUFFIXES = {
    '.png', '.jpg', '.jpeg', '.webp', '.heic', '.heif',
    '.wav', '.mp3', '.m4a', '.ogg', '.webm',
    '.pdf',
}
ALLOWED_UPLOAD_MIME_PREFIXES = (
    'image/png', 'image/jpeg', 'image/webp', 'image/heic', 'image/heif',
    'audio/wav', 'audio/x-wav', 'audio/mpeg', 'audio/mp3', 'audio/mp4', 'audio/aac', 'audio/ogg', 'audio/webm',
    'application/pdf',
)


def normalize_email(value: str | None) -> str:
    return str(value or '').strip().lower()


def validate_email(value: str | None) -> str:
    email = normalize_email(value)
    if not email or not EMAIL_RE.match(email):
        raise HTTPException(status_code=400, detail='Ugyldig e-postadresse.')
    return email


def validate_password(value: str | None, minimum_length: int | None = None) -> str:
    password = str(value or '')
    required_length = max(settings.min_password_length, int(minimum_length or settings.min_password_length))
    if len(password) < required_length:
        raise HTTPException(status_code=400, detail=f'Passordet må være minst {required_length} tegn langt.')
    classes = 0
    classes += any(ch.islower() for ch in password)
    classes += any(ch.isupper() for ch in password)
    classes += any(ch.isdigit() for ch in password)
    classes += any(not ch.isalnum() for ch in password)
    if len(password) < 16 and classes < 3:
        raise HTTPException(status_code=400, detail='Passordet må inneholde en kombinasjon av bokstaver, tall og spesialtegn, eller være et langt passord.')
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


def sanitize_original_filename(filename: str | None) -> str:
    clean_name = Path(str(filename or '').strip()).name.strip().replace('\x00', '')
    if not clean_name:
        raise HTTPException(status_code=400, detail='Filen mangler filnavn.')
    if len(clean_name) > 180:
        raise HTTPException(status_code=400, detail='Filnavnet er for langt.')
    return clean_name


def validate_upload_file(file: UploadFile) -> str:
    filename = sanitize_original_filename(file.filename)
    suffix = Path(filename).suffix.lower()
    if suffix not in ALLOWED_UPLOAD_SUFFIXES:
        raise HTTPException(status_code=400, detail='Filtypen støttes ikke i denne løsningen.')
    content_type = str(file.content_type or '').strip().lower()
    if content_type and not any(content_type == prefix for prefix in ALLOWED_UPLOAD_MIME_PREFIXES):
        raise HTTPException(status_code=400, detail='MIME-type støttes ikke i denne løsningen.')
    return filename


def validate_saved_file_size(size_bytes: int) -> None:
    max_bytes = settings.max_upload_size_mb * 1024 * 1024
    if size_bytes > max_bytes:
        raise HTTPException(status_code=400, detail=f'Filen er for stor. Maks tillatt størrelse er {settings.max_upload_size_mb} MB.')


def validate_upload_signature(filename: str, first_bytes: bytes) -> str:
    suffix = Path(filename).suffix.lower()
    sample = bytes(first_bytes or b'')
    if len(sample) < 8:
        raise HTTPException(status_code=400, detail='Filen er tom eller ugyldig.')

    if suffix == '.png':
        if not sample.startswith(b'\x89PNG\r\n\x1a\n'):
            raise HTTPException(status_code=400, detail='PNG-filen er ugyldig.')
        return 'image/png'
    if suffix in {'.jpg', '.jpeg'}:
        if not sample.startswith(b'\xff\xd8\xff'):
            raise HTTPException(status_code=400, detail='JPEG-filen er ugyldig.')
        return 'image/jpeg'
    if suffix == '.webp':
        if not (sample.startswith(b'RIFF') and b'WEBP' in sample[:16]):
            raise HTTPException(status_code=400, detail='WEBP-filen er ugyldig.')
        return 'image/webp'

    if suffix in {'.heic', '.heif'}:
        head = sample[:64]
        if not (b'ftyp' in head and any(token in head for token in [b'heic', b'heix', b'hevc', b'hevx', b'mif1', b'msf1'])):
            raise HTTPException(status_code=400, detail='HEIC/HEIF-filen er ugyldig.')
        return 'image/heic'
    if suffix == '.pdf':
        if not sample.startswith(b'%PDF-'):
            raise HTTPException(status_code=400, detail='PDF-filen er ugyldig.')
        return 'application/pdf'
    if suffix == '.wav':
        if not (sample.startswith(b'RIFF') and sample[8:12] == b'WAVE'):
            raise HTTPException(status_code=400, detail='WAV-filen er ugyldig.')
        return 'audio/wav'
    if suffix == '.mp3':
        if not (sample.startswith(b'ID3') or (sample[0] == 0xFF and (sample[1] & 0xE0) == 0xE0)):
            raise HTTPException(status_code=400, detail='MP3-filen er ugyldig.')
        return 'audio/mpeg'
    if suffix == '.m4a':
        if b'ftyp' not in sample[:32]:
            raise HTTPException(status_code=400, detail='M4A-filen er ugyldig.')
        return 'audio/mp4'
    if suffix == '.ogg':
        if not sample.startswith(b'OggS'):
            raise HTTPException(status_code=400, detail='OGG-filen er ugyldig.')
        return 'audio/ogg'
    if suffix == '.webm':
        if not sample.startswith(b'\x1aE\xdf\xa3'):
            raise HTTPException(status_code=400, detail='WEBM-filen er ugyldig.')
        return 'audio/webm'
    raise HTTPException(status_code=400, detail='Filtypen støttes ikke i denne løsningen.')
