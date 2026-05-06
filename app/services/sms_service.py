"""SMS OTP service for phone-based two-factor authentication.

Supports Twilio in production and logs OTP codes to console in dev mode.
Configure via environment variables (see .env.example).
"""
from __future__ import annotations

import hashlib
import hmac
import os
import secrets
import threading
import time
from collections import defaultdict, deque
from typing import Any

from ..logging_setup import get_logger

logger = get_logger(__name__)

# ---------------------------------------------------------------------------
# Configuration (read at import time, kept in module-level constants)
# ---------------------------------------------------------------------------

SMS_PROVIDER = os.getenv("KV_SMS_PROVIDER", "").strip().lower()  # "twilio" or ""
TWILIO_ACCOUNT_SID = os.getenv("KV_TWILIO_ACCOUNT_SID", "").strip()
TWILIO_AUTH_TOKEN = os.getenv("KV_TWILIO_AUTH_TOKEN", "").strip()
TWILIO_FROM_NUMBER = os.getenv("KV_TWILIO_FROM_NUMBER", "").strip()

OTP_LENGTH = 6
OTP_EXPIRE_SECONDS = 300          # 5 minutes
OTP_MAX_ATTEMPTS = 5              # per OTP session
OTP_RATE_WINDOW_SECONDS = 900     # 15 minutes
OTP_RATE_MAX_REQUESTS = 3         # per phone number per window

# ---------------------------------------------------------------------------
# Rate limiting (in-process, backed by a deque per phone)
# ---------------------------------------------------------------------------

_rate_lock = threading.Lock()
_otp_requests: dict[str, deque[float]] = defaultdict(deque)


def _prune(queue: deque[float]) -> None:
    cutoff = time.time() - OTP_RATE_WINDOW_SECONDS
    while queue and queue[0] < cutoff:
        queue.popleft()


def check_otp_rate_limit(phone: str) -> bool:
    """Return True if request is allowed, False if rate-limited."""
    key = _normalize_phone(phone)
    with _rate_lock:
        q = _otp_requests[key]
        _prune(q)
        return len(q) < OTP_RATE_MAX_REQUESTS


def record_otp_request(phone: str) -> None:
    key = _normalize_phone(phone)
    with _rate_lock:
        _otp_requests[key].append(time.time())


# ---------------------------------------------------------------------------
# Phone normalisation
# ---------------------------------------------------------------------------

def _normalize_phone(phone: str) -> str:
    """Return a clean E.164-style string, e.g. '+4799887766'.

    Accepts:
      - 8-digit local numbers (assumed Norway)
      - +47XXXXXXXX
      - 004XXXXXXXX
      - Numbers with spaces/dashes
    """
    raw = "".join(ch for ch in str(phone or "") if ch.isdigit() or ch == "+")
    raw = raw.strip()
    if raw.startswith("+"):
        return raw
    if raw.startswith("00"):
        return "+" + raw[2:]
    if len(raw) == 8:
        return "+47" + raw
    if raw.startswith("47") and len(raw) == 10:
        return "+" + raw
    return raw


def normalize_norwegian_phone(phone: str) -> str | None:
    """Validate and normalise a Norwegian mobile number.

    Returns the normalised E.164 string or None if invalid.
    """
    normalized = _normalize_phone(phone)
    # Norwegian mobile numbers: +47 followed by 4/9-starting 8-digit number
    if not normalized.startswith("+47"):
        return None
    digits = normalized[3:]
    if len(digits) != 8:
        return None
    if digits[0] not in "49":
        # Norwegian mobiles start with 4 or 9; landlines etc. excluded
        # Allow 4xx and 9xx only
        return None
    return normalized


# ---------------------------------------------------------------------------
# OTP generation and verification
# ---------------------------------------------------------------------------

def generate_otp() -> str:
    """Generate a cryptographically random 6-digit code."""
    return str(secrets.randbelow(10 ** OTP_LENGTH)).zfill(OTP_LENGTH)


def hash_otp(code: str) -> str:
    """One-way hash for storage (HMAC-SHA256 with a fixed server key)."""
    # Use a deterministic key derived from session secret for portability;
    # since OTPs expire quickly, this is acceptable.
    _secret = os.getenv("SESSION_SECRET", "dev-otp-secret").encode()
    return hmac.new(_secret, code.encode(), hashlib.sha256).hexdigest()


def verify_otp(code: str, stored_hash: str) -> bool:
    return hmac.compare_digest(hash_otp(code), stored_hash)


# ---------------------------------------------------------------------------
# SMS sending
# ---------------------------------------------------------------------------

def send_otp_sms(phone: str, code: str) -> bool:
    """Send the OTP code to *phone*.  Returns True on success."""
    normalized = normalize_norwegian_phone(phone) or phone
    message = f"Din engangskode for Fiskerikontroll er: {code}\nKoden er gyldig i {OTP_EXPIRE_SECONDS // 60} minutter."

    if SMS_PROVIDER == "twilio":
        return _send_twilio(normalized, message)

    # Dev / fallback mode: print to stdout so it's easy to test locally
    logger.warning(
        "SMS_PROVIDER ikke konfigurert. OTP-kode for %s: %s  (IKKE send i produksjon)",
        normalized,
        code,
    )
    # In dev mode we also print plainly so it's trivial to find:
    print(f"\n{'='*60}\nOTP DEV MODE — kode til {normalized}: {code}\n{'='*60}\n")
    return True


def _send_twilio(to: str, body: str) -> bool:
    try:
        from twilio.rest import Client  # type: ignore[import]
    except ImportError:
        logger.error("Twilio-pakken er ikke installert. Kjør: pip install twilio")
        return False

    if not (TWILIO_ACCOUNT_SID and TWILIO_AUTH_TOKEN and TWILIO_FROM_NUMBER):
        logger.error("Twilio er ikke konfigurert. Sett KV_TWILIO_ACCOUNT_SID, KV_TWILIO_AUTH_TOKEN og KV_TWILIO_FROM_NUMBER.")
        return False

    try:
        client = Client(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)
        msg = client.messages.create(body=body, from_=TWILIO_FROM_NUMBER, to=to)
        logger.info("OTP sendt via Twilio til %s (SID: %s)", to, msg.sid)
        return True
    except Exception as exc:
        logger.error("Twilio-sending feilet for %s: %s", to, exc)
        return False
