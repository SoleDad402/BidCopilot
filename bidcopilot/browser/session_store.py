"""Encrypted cookie/localStorage persistence."""
from __future__ import annotations
import json
from pathlib import Path
from cryptography.fernet import Fernet
from bidcopilot.utils.logging import get_logger

logger = get_logger(__name__)

class SessionStore:
    def __init__(self, db_path: str = "data/sessions.json"):
        self.path = Path(db_path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._key_path = Path("data/.session_key")
        self.fernet = Fernet(self._get_or_create_key())
        self._sessions: dict = self._load_all()

    def _get_or_create_key(self) -> bytes:
        if self._key_path.exists():
            return self._key_path.read_bytes()
        key = Fernet.generate_key()
        self._key_path.parent.mkdir(parents=True, exist_ok=True)
        self._key_path.write_bytes(key)
        return key

    def _load_all(self) -> dict:
        if self.path.exists():
            try:
                return json.loads(self.path.read_text())
            except Exception:
                return {}
        return {}

    def _save_all(self):
        self.path.write_text(json.dumps(self._sessions))

    async def save(self, site_name: str, storage_state: dict):
        data = json.dumps(storage_state).encode()
        encrypted = self.fernet.encrypt(data).decode()
        self._sessions[site_name] = encrypted
        self._save_all()
        logger.info("session_saved", site=site_name)

    async def load(self, site_name: str) -> dict | None:
        encrypted = self._sessions.get(site_name)
        if not encrypted:
            return None
        try:
            decrypted = self.fernet.decrypt(encrypted.encode())
            return json.loads(decrypted)
        except Exception:
            logger.warning("session_decrypt_failed", site=site_name)
            return None
