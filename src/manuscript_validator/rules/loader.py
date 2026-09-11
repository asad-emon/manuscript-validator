"""Loads rule configs.

Resources are read through `importlib.resources`, never `__file__`-relative
paths: those work in a source checkout and break under PyInstaller --onedir,
where the failure surfaces during packaging -- the point in the schedule where
debugging is most expensive. See docs/decisions.md (C5).

Validation errors are re-raised as `RuleConfigError` naming the offending
`rule_id` and field. A journal template is edited by hand, often by someone who
is not reading this code, so "rule 'title-size': condition.operator -- input
should be one of ..." is the difference between a two-minute fix and a
bug report.
"""

from __future__ import annotations

import json
from importlib import resources
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from manuscript_validator.errors import RuleConfigError
from manuscript_validator.rules.schema import Ruleset

CONFIG_PACKAGE = "manuscript_validator.rules.config"
PROMPT_PACKAGE = "manuscript_validator.rules.prompts"


def load_ruleset(ruleset_id: str = "journal_v1") -> Ruleset:
    """Load a bundled ruleset by id."""
    try:
        text = resources.files(CONFIG_PACKAGE).joinpath(f"{ruleset_id}.json").read_text("utf-8")
    except (FileNotFoundError, ModuleNotFoundError) as exc:
        raise RuleConfigError(f"no ruleset named '{ruleset_id}' is bundled") from exc
    return parse_ruleset(text, source=f"{ruleset_id}.json")


def load_ruleset_file(path: Path) -> Ruleset:
    """Load a ruleset from an arbitrary path (tests, and user-supplied templates)."""
    try:
        text = path.read_text("utf-8")
    except OSError as exc:
        raise RuleConfigError(f"could not read rule config '{path}': {exc}") from exc
    return parse_ruleset(text, source=str(path))


def load_prompt(prompt_file: str) -> str:
    """Load a semantic rule's prompt template by its `prompt_file` value."""
    name = prompt_file.split("/")[-1]
    try:
        return resources.files(PROMPT_PACKAGE).joinpath(name).read_text("utf-8")
    except (FileNotFoundError, ModuleNotFoundError) as exc:
        raise RuleConfigError(f"prompt file '{prompt_file}' is not bundled") from exc


def parse_ruleset(text: str, *, source: str = "<string>") -> Ruleset:
    """Parse and validate ruleset JSON."""
    try:
        raw = json.loads(text)
    except json.JSONDecodeError as exc:
        raise RuleConfigError(f"{source} is not valid JSON: {exc}") from exc
    if not isinstance(raw, dict):
        raise RuleConfigError(f"{source}: top level must be a JSON object")

    try:
        return Ruleset.model_validate(raw)
    except ValidationError as exc:
        raise RuleConfigError(_format_errors(exc, raw, source)) from exc


def _format_errors(exc: ValidationError, raw: dict[str, Any], source: str) -> str:
    """Turn pydantic's error list into messages naming the rule and field."""
    rule_ids = _rule_ids(raw)
    lines = [f"{source}: {exc.error_count()} rule config error(s)"]
    for error in exc.errors():
        lines.append(f"  - {_describe(error['loc'], rule_ids)}: {error['msg']}")
    return "\n".join(lines)


def _rule_ids(raw: dict[str, Any]) -> dict[int, str]:
    """Map each rule's list index to its declared id, for error messages.

    Read from the raw JSON rather than the parsed model, because the whole
    point is that the model failed to parse.
    """
    rules = raw.get("rules")
    if not isinstance(rules, list):
        return {}
    ids: dict[int, str] = {}
    for index, rule in enumerate(rules):
        if isinstance(rule, dict):
            rule_id = rule.get("rule_id")
            if isinstance(rule_id, str):
                ids[index] = rule_id
    return ids


def _describe(loc: tuple[int | str, ...], rule_ids: dict[int, str]) -> str:
    """Render an error location as `rule 'x': field.subfield`."""
    if len(loc) >= 2 and loc[0] == "rules" and isinstance(loc[1], int):
        index = loc[1]
        name = rule_ids.get(index, f"index {index}")
        # Pydantic inserts the resolved union member's class name; it is noise
        # to someone editing JSON, who never sees a class.
        rest = [str(part) for part in loc[2:] if part not in ("DeterministicRule", "SemanticRule")]
        field = ".".join(rest) if rest else "<rule>"
        return f"rule '{name}': {field}"
    return ".".join(str(part) for part in loc) if loc else "<ruleset>"
