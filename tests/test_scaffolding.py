"""Task 1 exit criteria: the package imports, and the CLI has a usable --help."""

from __future__ import annotations

import importlib
import pkgutil

import pytest

import manuscript_validator

PIPELINE_PACKAGES = [
    "manuscript_validator.models",
    "manuscript_validator.parser",
    "manuscript_validator.segmenter",
    "manuscript_validator.rules",
    "manuscript_validator.autofix",
    "manuscript_validator.report",
    "manuscript_validator.output",
    "manuscript_validator.config",
]


def _all_modules() -> list[str]:
    return [
        name
        for _, name, _ in pkgutil.walk_packages(
            manuscript_validator.__path__, prefix="manuscript_validator."
        )
    ]


@pytest.mark.parametrize("module_name", _all_modules())
def test_every_module_imports(module_name: str) -> None:
    importlib.import_module(module_name)


def test_cli_help_exits_cleanly(capsys: pytest.CaptureFixture[str]) -> None:
    from manuscript_validator.cli import build_parser

    parser = build_parser()
    with pytest.raises(SystemExit) as exc:
        parser.parse_args(["--help"])
    assert exc.value.code == 0
    assert "validate" in capsys.readouterr().out


def test_bare_invocation_prints_usage(capsys: pytest.CaptureFixture[str]) -> None:
    from manuscript_validator.cli import main

    assert main([]) == 2
    assert "usage:" in capsys.readouterr().out
