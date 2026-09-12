"""Windows DPAPI secret box -- production (Task 15).

`import win32crypt` is deliberately lazy, inside the methods: that is what lets
this module be imported and its non-DPAPI logic tested on the Linux dev box
(inject a fake `sys.modules["win32crypt"]` and assert the call shape).

Uses app-specific entropy and per-user protection (`flags=0`); never
CRYPTPROTECT_LOCAL_MACHINE, which would let any user on the machine decrypt.
"""

from __future__ import annotations

import base64

from manuscript_validator.errors import SettingsError

#: Mixed into every encrypt/decrypt call so a DPAPI-protected blob from a
#: different application can't be silently accepted here even if it somehow
#: landed in this app's config file.
_ENTROPY = b"manuscript-validator-v1"

_DESCRIPTION = "ManuscriptValidator Gemini API key"


class DpapiSecretBox:
    scheme = "dpapi"

    def encrypt(self, plaintext: str) -> str:
        import win32crypt

        blob = win32crypt.CryptProtectData(
            plaintext.encode("utf-8"), _DESCRIPTION, _ENTROPY, None, None, 0
        )
        return base64.b64encode(blob).decode("ascii")

    def decrypt(self, ciphertext: str) -> str:
        import win32crypt

        blob = base64.b64decode(ciphertext.encode("ascii"))
        try:
            _description, plaintext = win32crypt.CryptUnprotectData(
                blob, _ENTROPY, None, None, 0
            )
        except Exception as exc:
            raise SettingsError(f"DPAPI decrypt failed: {exc}") from exc
        result: str = plaintext.decode("utf-8")
        return result


__all__ = ["DpapiSecretBox"]
