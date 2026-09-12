"""Development secret box for non-Windows machines.

Opt-in only, via an environment variable (`settings_store.DEV_SECRET_STORE_ENV_VAR`):
production must fail loudly on a platform with no secure store rather than
silently degrade to weaker storage.

The key is derived from a fixed local marker, not stored anywhere -- this
backend's threat model is "an accidental `cat config.json` doesn't hand over
the API key in plaintext on a dev machine", not real protection against a
determined local attacker. That is what DPAPI is for, and DPAPI is what
Windows always uses regardless of this environment variable.
"""

from __future__ import annotations

import base64
import getpass
import hashlib

from cryptography.fernet import Fernet, InvalidToken


def _derive_key() -> bytes:
    seed = f"manuscript-validator-dev:{getpass.getuser()}".encode()
    return base64.urlsafe_b64encode(hashlib.sha256(seed).digest())


class FernetSecretBox:
    scheme = "dev-fernet"

    def __init__(self) -> None:
        self._fernet = Fernet(_derive_key())

    def encrypt(self, plaintext: str) -> str:
        return self._fernet.encrypt(plaintext.encode("utf-8")).decode("ascii")

    def decrypt(self, ciphertext: str) -> str:
        try:
            return self._fernet.decrypt(ciphertext.encode("ascii")).decode("utf-8")
        except InvalidToken as exc:
            raise ValueError("dev secret box: invalid or corrupted ciphertext") from exc


__all__ = ["FernetSecretBox"]
