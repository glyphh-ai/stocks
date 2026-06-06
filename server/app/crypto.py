"""Symmetric encryption for stored credentials.

Credentials entered in the config UI are encrypted at rest with Fernet
(AES-128-CBC + HMAC). The key lives in CREDENTIAL_KEY; if it is unset on first
use we generate one and append it to server/.env so it survives restarts.
Decrypted secrets are only ever used server-side (in the job runner) and are
never returned to the browser.
"""

from __future__ import annotations

from pathlib import Path

from cryptography.fernet import Fernet

from .config import settings

_ENV_PATH = Path(__file__).resolve().parent.parent / ".env"


def _load_or_create_key() -> bytes:
    if settings.credential_key:
        return settings.credential_key.encode()
    key = Fernet.generate_key()
    with _ENV_PATH.open("a") as f:
        f.write(f"CREDENTIAL_KEY={key.decode()}\n")
    settings.credential_key = key.decode()
    return key


_fernet = Fernet(_load_or_create_key())


def encrypt(plaintext: str) -> str:
    return _fernet.encrypt(plaintext.encode()).decode()


def decrypt(token: str) -> str:
    return _fernet.decrypt(token.encode()).decode()
