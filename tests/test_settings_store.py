"""Task 15 exit criteria (the Linux-testable half): `get_api_key()` never
raises for any failure mode, a config written by one scheme is rejected by
another, and the DPAPI call shape is verified against a fake `win32crypt`
module -- the real DPAPI round trip itself is the one gate this environment
cannot substitute for (no Windows VM), tracked as an open risk until Task 15
gets one.
"""

from __future__ import annotations

import json
import sys
import types
from pathlib import Path

import pytest

from manuscript_validator.config.settings_store import (
    NullSecretBox,
    SecretBox,
    config_path,
    default_secret_box,
    get_api_key,
    set_api_key,
)
from manuscript_validator.config.settings_store_dev import FernetSecretBox
from manuscript_validator.config.settings_store_dpapi import DpapiSecretBox
from manuscript_validator.errors import UnsupportedPlatformError


def _null_box() -> SecretBox:
    return NullSecretBox()


# --------------------------------------------------------------------------
# get_api_key: every failure mode returns None, never raises
# --------------------------------------------------------------------------


def test_get_api_key_returns_none_when_no_file_exists(tmp_path: Path) -> None:
    assert get_api_key(_null_box(), path=tmp_path / "config.json") is None


def test_get_api_key_returns_none_for_unparseable_json(tmp_path: Path) -> None:
    path = tmp_path / "config.json"
    path.write_text("not json at all {{{", encoding="utf-8")
    assert get_api_key(_null_box(), path=path) is None


def test_get_api_key_returns_none_when_json_is_not_an_object(tmp_path: Path) -> None:
    path = tmp_path / "config.json"
    path.write_text("[1, 2, 3]", encoding="utf-8")
    assert get_api_key(_null_box(), path=path) is None


def test_get_api_key_returns_none_for_a_scheme_mismatch(tmp_path: Path) -> None:
    """A config written by the dev backend must be rejected, not garbage-
    decrypted, when read back with a different scheme (e.g. on Windows)."""
    path = tmp_path / "config.json"
    path.write_text(json.dumps({"scheme": "some-other-scheme", "api_key": "x"}), encoding="utf-8")
    assert get_api_key(_null_box(), path=path) is None


def test_get_api_key_returns_none_when_api_key_field_is_missing_or_wrong_type(
    tmp_path: Path,
) -> None:
    path = tmp_path / "config.json"
    path.write_text(json.dumps({"scheme": "null-test-only", "api_key": 12345}), encoding="utf-8")
    assert get_api_key(_null_box(), path=path) is None


def test_get_api_key_returns_none_on_a_decrypt_failure(tmp_path: Path) -> None:
    path = tmp_path / "config.json"
    path.write_text(
        json.dumps({"scheme": "dev-fernet", "api_key": "not-a-real-fernet-token"}),
        encoding="utf-8",
    )
    assert get_api_key(FernetSecretBox(), path=path) is None


# --------------------------------------------------------------------------
# set_api_key / get_api_key round trip
# --------------------------------------------------------------------------


def test_set_then_get_round_trips_with_the_null_box(tmp_path: Path) -> None:
    path = tmp_path / "config.json"
    set_api_key("my-secret-key", _null_box(), path=path)
    assert get_api_key(_null_box(), path=path) == "my-secret-key"


def test_set_then_get_round_trips_with_the_fernet_box(tmp_path: Path) -> None:
    path = tmp_path / "config.json"
    set_api_key("AIzaFAKEFAKEFAKEFAKEFAKEFAKEFAKEFAKEFA", FernetSecretBox(), path=path)
    assert get_api_key(FernetSecretBox(), path=path) == "AIzaFAKEFAKEFAKEFAKEFAKEFAKEFAKEFAKEFA"


def test_set_api_key_writes_no_leftover_tmp_file(tmp_path: Path) -> None:
    path = tmp_path / "config.json"
    set_api_key("k", _null_box(), path=path)
    leftovers = [p for p in tmp_path.iterdir() if p.name != "config.json"]
    assert leftovers == []


def test_set_api_key_creates_parent_directories(tmp_path: Path) -> None:
    path = tmp_path / "nested" / "dir" / "config.json"
    set_api_key("k", _null_box(), path=path)
    assert path.exists()


def test_stored_file_records_the_scheme(tmp_path: Path) -> None:
    path = tmp_path / "config.json"
    set_api_key("k", _null_box(), path=path)
    data = json.loads(path.read_text("utf-8"))
    assert data["scheme"] == "null-test-only"


# --------------------------------------------------------------------------
# default_secret_box(): platform dispatch
# --------------------------------------------------------------------------


def test_default_secret_box_raises_without_the_dev_env_var_on_non_windows(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(sys, "platform", "linux")
    monkeypatch.delenv("MANUSCRIPT_VALIDATOR_DEV_SECRET_STORE", raising=False)
    with pytest.raises(UnsupportedPlatformError):
        default_secret_box()


def test_default_secret_box_uses_fernet_when_dev_env_var_is_set(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(sys, "platform", "linux")
    monkeypatch.setenv("MANUSCRIPT_VALIDATOR_DEV_SECRET_STORE", "1")
    box = default_secret_box()
    assert box.scheme == "dev-fernet"


def test_default_secret_box_uses_dpapi_on_windows_regardless_of_the_env_var(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(sys, "platform", "win32")
    monkeypatch.delenv("MANUSCRIPT_VALIDATOR_DEV_SECRET_STORE", raising=False)
    box = default_secret_box()
    assert box.scheme == "dpapi"


def test_get_api_key_degrades_to_none_rather_than_raising_when_platform_unsupported(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(sys, "platform", "linux")
    monkeypatch.delenv("MANUSCRIPT_VALIDATOR_DEV_SECRET_STORE", raising=False)
    assert get_api_key(path=tmp_path / "config.json") is None


# --------------------------------------------------------------------------
# NullSecretBox: refuses to construct in a frozen build
# --------------------------------------------------------------------------


def test_null_secret_box_refuses_to_construct_when_frozen(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    with pytest.raises(UnsupportedPlatformError):
        NullSecretBox()


# --------------------------------------------------------------------------
# FernetSecretBox
# --------------------------------------------------------------------------


def test_fernet_box_round_trips() -> None:
    box = FernetSecretBox()
    assert box.decrypt(box.encrypt("hello")) == "hello"


def test_fernet_box_raises_value_error_on_invalid_ciphertext() -> None:
    box = FernetSecretBox()
    with pytest.raises(ValueError, match="invalid or corrupted"):
        box.decrypt("not-a-fernet-token")


# --------------------------------------------------------------------------
# DpapiSecretBox: call shape against a fake win32crypt, no Windows needed
# --------------------------------------------------------------------------


def _install_fake_win32crypt(monkeypatch: pytest.MonkeyPatch, calls: list) -> None:
    def fake_protect(data, description, entropy, reserved, prompt_struct, flags):
        calls.append(("protect", data, description, entropy, flags))
        return b"OPAQUE-DPAPI-BLOB:" + data

    def fake_unprotect(blob, entropy, reserved, prompt_struct, flags):
        calls.append(("unprotect", blob, entropy, flags))
        prefix = b"OPAQUE-DPAPI-BLOB:"
        if not blob.startswith(prefix):
            raise ValueError("bad blob")
        return None, blob[len(prefix) :]

    fake_module = types.SimpleNamespace(
        CryptProtectData=fake_protect, CryptUnprotectData=fake_unprotect
    )
    monkeypatch.setitem(sys.modules, "win32crypt", fake_module)


def test_dpapi_box_round_trips_against_a_fake_win32crypt(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list = []
    _install_fake_win32crypt(monkeypatch, calls)

    box = DpapiSecretBox()
    ciphertext = box.encrypt("my-api-key")
    plaintext = box.decrypt(ciphertext)

    assert plaintext == "my-api-key"


def test_dpapi_box_never_uses_local_machine_scope(monkeypatch: pytest.MonkeyPatch) -> None:
    """`flags=0` -- never `CRYPTPROTECT_LOCAL_MACHINE` (0x4), which would let
    any user on the machine decrypt this key, not just the one who set it."""
    calls: list = []
    _install_fake_win32crypt(monkeypatch, calls)

    box = DpapiSecretBox()
    box.decrypt(box.encrypt("k"))

    protect_call = next(c for c in calls if c[0] == "protect")
    unprotect_call = next(c for c in calls if c[0] == "unprotect")
    assert protect_call[4] == 0
    assert unprotect_call[3] == 0


def test_dpapi_box_passes_app_specific_entropy(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list = []
    _install_fake_win32crypt(monkeypatch, calls)

    box = DpapiSecretBox()
    box.decrypt(box.encrypt("k"))

    protect_call = next(c for c in calls if c[0] == "protect")
    assert protect_call[3] == b"manuscript-validator-v1"


def test_dpapi_box_raises_settings_error_on_a_decrypt_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from manuscript_validator.errors import SettingsError

    _install_fake_win32crypt(monkeypatch, [])
    box = DpapiSecretBox()
    with pytest.raises(SettingsError):
        box.decrypt("aW52YWxpZC1ibG9i")  # base64 of "invalid-blob", not a real DPAPI blob


# --------------------------------------------------------------------------
# config_path()
# --------------------------------------------------------------------------


def test_config_path_is_under_a_per_user_app_directory() -> None:
    path = config_path()
    assert path.name == "config.json"
    assert "ManuscriptValidator" in str(path)
