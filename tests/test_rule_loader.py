"""Task 2: rule configs load, and bad ones fail loudly enough to fix.

Spec section 2 promises a second journal template is a config addition rather
than a code change. That promise is only worth anything if a malformed config
fails at load time with a message naming the rule and the field -- these tests
assert the message quality, not just that an exception is raised.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from manuscript_validator.errors import RuleConfigError
from manuscript_validator.models import CheckType, FixAction, Section, Severity
from manuscript_validator.rules import (
    load_prompt,
    load_ruleset,
    load_ruleset_file,
    parse_ruleset,
)


def _valid_config(**overrides: Any) -> dict[str, Any]:
    config: dict[str, Any] = {
        "ruleset_id": "test",
        "ruleset_version": "1.0.0",
        "rules": [
            {
                "rule_id": "title-size",
                "check_type": "deterministic",
                "applies_to_section": ["title"],
                "condition": {"attribute": "font_size_pt", "operator": "==", "value": 14},
                "severity": "high",
                "auto_fixable": True,
                "fix_action": "set_font_size",
                "fix_params": {"font_size_pt": 14},
                "message": "Title must be font size 14 pt.",
            }
        ],
    }
    config.update(overrides)
    return config


def _parse(config: dict[str, Any]) -> Any:
    return parse_ruleset(json.dumps(config))


class TestBundledRuleset:
    def test_journal_v1_loads(self) -> None:
        ruleset = load_ruleset("journal_v1")
        assert ruleset.ruleset_id == "journal_v1"
        assert ruleset.rules

    def test_loads_via_importlib_resources_not_file_paths(self) -> None:
        """Guards C5: __file__-relative loading breaks under PyInstaller --onedir.

        Checks the parsed syntax tree rather than the text, so the prose
        explaining the rule in the module docstring does not trip its own test.
        """
        import ast as ast_module
        import inspect

        from manuscript_validator.rules import loader

        tree = ast_module.parse(inspect.getsource(loader))
        names = {n.id for n in ast_module.walk(tree) if isinstance(n, ast_module.Name)}
        assert "__file__" not in names
        assert "resources" in names

    def test_unknown_ruleset_names_what_was_asked_for(self) -> None:
        with pytest.raises(RuleConfigError, match="no ruleset named 'nope'"):
            load_ruleset("nope")

    def test_semantic_rule_prompt_file_resolves(self) -> None:
        ruleset = load_ruleset("journal_v1")
        for rule in ruleset.rules:
            if rule.check_type is CheckType.SEMANTIC and rule.prompt_file:
                assert load_prompt(rule.prompt_file).strip()

    def test_declared_sections_are_known(self) -> None:
        ruleset = load_ruleset("journal_v1")
        known = set(Section)
        assert set(ruleset.section_order) <= known
        assert set(ruleset.required_sections) <= known


class TestValidConfigs:
    def test_defaults_applied(self) -> None:
        ruleset = _parse(_valid_config())
        rule = ruleset.by_id("title-size")
        assert rule is not None
        assert rule.severity is Severity.HIGH
        assert rule.priority == 100
        assert rule.selector.node_type.value == "run"

    def test_semantic_rule_is_never_auto_fixable(self) -> None:
        ruleset = _parse(
            _valid_config(
                rules=[
                    {
                        "rule_id": "abstract-structure",
                        "check_type": "semantic",
                        "applies_to_section": ["abstract"],
                        "prompt_template": "check {abstract_text}",
                        "message": "Abstract structure is wrong.",
                    }
                ]
            )
        )
        rule = ruleset.by_id("abstract-structure")
        assert rule is not None
        assert rule.auto_fixable is False
        assert rule.fix_action is FixAction.SUGGEST_ONLY

    def test_by_id_returns_none_for_unknown(self) -> None:
        assert _parse(_valid_config()).by_id("nope") is None

    def test_load_from_arbitrary_path(self, tmp_path: Path) -> None:
        path = tmp_path / "custom.json"
        path.write_text(json.dumps(_valid_config()), encoding="utf-8")
        assert load_ruleset_file(path).ruleset_id == "test"

    def test_missing_file_is_reported_not_raised_as_oserror(self, tmp_path: Path) -> None:
        with pytest.raises(RuleConfigError, match="could not read rule config"):
            load_ruleset_file(tmp_path / "absent.json")


class TestBrokenConfigs:
    """Six malformed configs; each message must name the rule and the field."""

    def test_1_malformed_json(self) -> None:
        with pytest.raises(RuleConfigError, match="not valid JSON"):
            parse_ruleset("{not json")

    def test_2_unknown_operator(self) -> None:
        config = _valid_config()
        config["rules"][0]["condition"]["operator"] = "approximately"
        with pytest.raises(RuleConfigError) as exc:
            _parse(config)
        assert "rule 'title-size'" in str(exc.value)
        assert "condition.operator" in str(exc.value)

    def test_3_auto_fixable_without_fix_action(self) -> None:
        config = _valid_config()
        del config["rules"][0]["fix_action"]
        with pytest.raises(RuleConfigError) as exc:
            _parse(config)
        assert "rule 'title-size'" in str(exc.value)
        assert "no 'fix_action' is set" in str(exc.value)

    def test_4_misspelled_field_is_rejected_not_ignored(self) -> None:
        """A typo'd key must fail; silently defaulting would disable the rule."""
        config = _valid_config()
        config["rules"][0]["auto_fixible"] = True
        with pytest.raises(RuleConfigError) as exc:
            _parse(config)
        assert "rule 'title-size'" in str(exc.value)
        assert "auto_fixible" in str(exc.value)

    def test_5_unknown_section(self) -> None:
        config = _valid_config()
        config["rules"][0]["applies_to_section"] = ["metholodgy"]
        with pytest.raises(RuleConfigError) as exc:
            _parse(config)
        assert "rule 'title-size'" in str(exc.value)
        assert "applies_to_section" in str(exc.value)

    def test_6_duplicate_rule_ids(self) -> None:
        config = _valid_config()
        config["rules"].append(dict(config["rules"][0]))
        with pytest.raises(RuleConfigError, match="duplicate rule_id 'title-size'"):
            _parse(config)

    def test_semantic_rule_with_both_prompt_sources(self) -> None:
        config = _valid_config(
            rules=[
                {
                    "rule_id": "abstract-structure",
                    "check_type": "semantic",
                    "prompt_template": "x",
                    "prompt_file": "prompts/abstract_structure.txt",
                    "message": "m",
                }
            ]
        )
        with pytest.raises(RuleConfigError) as exc:
            _parse(config)
        assert "exactly one of 'prompt_template' or 'prompt_file'" in str(exc.value)

    def test_semantic_rule_with_no_prompt_source(self) -> None:
        config = _valid_config(
            rules=[{"rule_id": "r", "check_type": "semantic", "message": "m"}]
        )
        with pytest.raises(RuleConfigError, match="exactly one of"):
            _parse(config)

    def test_condition_operator_requiring_value_without_one(self) -> None:
        config = _valid_config()
        del config["rules"][0]["condition"]["value"]
        with pytest.raises(RuleConfigError) as exc:
            _parse(config)
        assert "requires a 'value'" in str(exc.value)

    def test_unary_operator_needs_no_value(self) -> None:
        config = _valid_config()
        config["rules"][0]["condition"] = {
            "attribute": "text",
            "operator": "is_uppercase_literal",
        }
        config["rules"][0]["auto_fixable"] = False
        del config["rules"][0]["fix_action"]
        del config["rules"][0]["fix_params"]
        assert _parse(config).by_id("title-size") is not None

    def test_error_message_omits_pydantic_class_names(self) -> None:
        """Someone editing JSON never sees a class name; it is noise."""
        config = _valid_config()
        config["rules"][0]["condition"]["operator"] = "approximately"
        with pytest.raises(RuleConfigError) as exc:
            _parse(config)
        assert "DeterministicRule" not in str(exc.value)

    def test_rule_without_id_is_located_by_index(self) -> None:
        config = _valid_config()
        del config["rules"][0]["rule_id"]
        with pytest.raises(RuleConfigError) as exc:
            _parse(config)
        assert "index 0" in str(exc.value)
