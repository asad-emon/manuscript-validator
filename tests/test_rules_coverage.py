"""Task 6 exit criteria (coverage half): every rule in `journal_v1.json` has a
`violating()` builder in Task 3's fixture factory, and vice versa. Without
this, a rule could be added to config with no test ever exercising it -- the
most likely way this suite decays over time.
"""

from __future__ import annotations

from fixtures.factory import RULE_IDS
from manuscript_validator.rules.loader import load_ruleset

RULESET = load_ruleset("journal_v1")


def test_every_configured_rule_has_a_violating_fixture() -> None:
    configured = set(RULESET.rule_ids)
    missing = configured - set(RULE_IDS)
    assert not missing, f"rule(s) in journal_v1.json with no violating() builder: {missing}"


def test_every_fixture_rule_id_is_configured() -> None:
    fixture_only = set(RULE_IDS) - set(RULESET.rule_ids)
    msg = f"violating() builder(s) with no rule in journal_v1.json: {fixture_only}"
    assert not fixture_only, msg


def test_rule_ids_are_unique() -> None:
    assert len(RULESET.rule_ids) == len(set(RULESET.rule_ids))
