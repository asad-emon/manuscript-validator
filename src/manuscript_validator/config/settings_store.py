"""Settings store: SecretBox protocol and platform factory.

Abstraction sits at *encryption*, not at "settings": the file layout, JSON
schema, atomic write, and error contract are identical on every platform, and
only the cipher differs.

`get_api_key()` returns None and never raises -- for a missing file, an absent
key, a failed decrypt, a scheme mismatch, or unparseable JSON. Spec section 4.2
requires the caller treat that exactly like a network failure.

The stored file records which scheme encrypted it, so a config written by the
dev backend is detected and rejected on Windows rather than producing a garbage
decrypt that surfaces later as an unexplained "key rejected" from Gemini.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Protocol

import platformdirs

from manuscript_validator.errors import UnsupportedPlatformError

APP_NAME = "ManuscriptValidator"
CONFIG_FILENAME = "config.json"

#: Opt-in switch for the dev-only backend (`settings_store_dev.FernetSecretBox`).
#: Never checked on Windows -- DPAPI is always used there, opt-in or not.
DEV_SECRET_STORE_ENV_VAR = "MANUSCRIPT_VALIDATOR_DEV_SECRET_STORE"


class SecretBox(Protocol):
    """Encrypts and decrypts one secret string. Each scheme is a different
    box; the file format, atomicity, and error handling above this seam are
    identical regardless of which one is in use."""

    scheme: str

    def encrypt(self, plaintext: str) -> str: ...

    def decrypt(self, ciphertext: str) -> str: ...


class NullSecretBox:
    """No-op box: stores the value verbatim. For tests only -- refuses to
    construct inside a frozen (PyInstaller) build, so it can never end up as
    the real secret store by accident.
    """

    scheme = "null-test-only"

    def __init__(self) -> None:
        if getattr(sys, "frozen", False):
            raise UnsupportedPlatformError("NullSecretBox must never run in a packaged build")

    def encrypt(self, plaintext: str) -> str:
        return plaintext

    def decrypt(self, ciphertext: str) -> str:
        return ciphertext


def config_path() -> Path:
    return Path(platformdirs.user_config_dir(APP_NAME)) / CONFIG_FILENAME


def default_secret_box() -> SecretBox:
    """DPAPI on Windows, always -- the env var below is never consulted
    there. Elsewhere, the dev backend only if explicitly requested;
    otherwise a loud failure, never a silent downgrade to weaker storage.
    """
    if sys.platform == "win32":
        from manuscript_validator.config.settings_store_dpapi import DpapiSecretBox

        return DpapiSecretBox()
    if os.environ.get(DEV_SECRET_STORE_ENV_VAR) == "1":
        from manuscript_validator.config.settings_store_dev import FernetSecretBox

        return FernetSecretBox()
    raise UnsupportedPlatformError(
        "No secure secret store is available on this platform. Set "
        f"{DEV_SECRET_STORE_ENV_VAR}=1 to opt into the dev-only backend "
        "(never for production use)."
    )


def get_api_key(box: SecretBox | None = None, *, path: Path | None = None) -> str | None:
    """`None` for every failure mode -- missing file, absent key, unparseable
    JSON, a scheme mismatch, or a decrypt error -- never an exception. Spec
    section 4.2 treats a missing key exactly like a semantic-check network
    failure, and that only works if this function keeps its side of that
    contract.

    `path` defaults to the real per-user config location; tests pass a
    `tmp_path` instead so nothing here ever touches a developer's real
    settings file.
    """
    try:
        box = box or default_secret_box()
    except UnsupportedPlatformError:
        return None
    try:
        raw = (path or config_path()).read_text("utf-8")
    except OSError:
        return None
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return None
    if not isinstance(data, dict):
        return None
    if data.get("scheme") != box.scheme:
        return None
    ciphertext = data.get("api_key")
    if not isinstance(ciphertext, str):
        return None
    try:
        return box.decrypt(ciphertext)
    except Exception:
        return None


def set_api_key(api_key: str, box: SecretBox | None = None, *, path: Path | None = None) -> None:
    box = box or default_secret_box()
    path = path or config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    data = {"scheme": box.scheme, "api_key": box.encrypt(api_key)}

    tmp_path = path.with_name(f"{path.name}.tmp")
    tmp_path.write_text(json.dumps(data), encoding="utf-8")
    os.replace(tmp_path, path)  # atomic on every platform this project targets


__all__ = [
    "APP_NAME",
    "DEV_SECRET_STORE_ENV_VAR",
    "NullSecretBox",
    "SecretBox",
    "config_path",
    "default_secret_box",
    "get_api_key",
    "set_api_key",
]
