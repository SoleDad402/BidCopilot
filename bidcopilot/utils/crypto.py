"""Fernet encryption helpers for credential storage."""
from __future__ import annotations

from pathlib import Path

from cryptography.fernet import Fernet

_KEY_PATH = Path("data/.encryption_key")


def _get_or_create_key() -> bytes:
    if _KEY_PATH.exists():
        return _KEY_PATH.read_bytes()
    _KEY_PATH.parent.mkdir(parents=True, exist_ok=True)
    key = Fernet.generate_key()
    _KEY_PATH.write_bytes(key)
    return key


_fernet = Fernet(_get_or_create_key())


def encrypt(data: str) -> bytes:
    return _fernet.encrypt(data.encode())


def decrypt(data: bytes) -> str:
    return _fernet.decrypt(data).decode()
