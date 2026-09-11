"""Rule and Ruleset models (spec section 5.2, with additions).

Pydantic rather than dataclasses here, and only here: rule configs are
human-authored external JSON, which is the one boundary in this system where
runtime validation earns its cost. Spec section 2 promises a second journal is
a config addition rather than a code change -- that promise only holds if a bad
config fails loudly and names what is wrong with it.

Additions beyond spec section 5.2:

- `selector` -- `applies_to_section` alone cannot express "the caption
  paragraph of each table" or "runs whose text is a bare affiliation numeral".
- `prompt_file` -- section 7.2's example prompt is eight lines; escaped into a
  JSON string it is unreviewable and undiffable.
- `on_missing_section` -- closes the gap where an absent section yields no
  nodes, hence no violations, and FR-11 passes on a manuscript missing half its
  structure.
- `priority` -- gives autofix a reproducible apply order.

One rule carries one condition and one fix action. Section 6's
`author-bold-superscript` bundles three checks into one `fix_action` slot,
which has no answer to "which fix?" when only one of them fails.
"""

from __future__ import annotations

from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from manuscript_validator.models.enums import (
    CheckType,
    FixAction,
    NodeType,
    OnMissingSection,
    Operator,
    Section,
    SelectorScope,
    Severity,
)


class StrictModel(BaseModel):
    """Rejects unknown keys.

    A misspelled field in a rule config must fail rather than be silently
    ignored -- a typo'd `auto_fixible` that quietly defaults to false would
    disable a rule with no visible symptom.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)


class Condition(StrictModel):
    """A deterministic attribute comparison."""

    attribute: str
    operator: Operator
    value: Any = None

    @model_validator(mode="after")
    def _value_required_unless_unary(self) -> Condition:
        unary = {Operator.IS_TITLE_CASE, Operator.IS_UPPERCASE_LITERAL, Operator.IS_NON_EMPTY}
        if self.operator not in unary and self.value is None:
            raise ValueError(f"operator '{self.operator.value}' requires a 'value'")
        return self


class Selector(StrictModel):
    """Which nodes within the matched sections a rule applies to."""

    node_type: NodeType = NodeType.RUN
    scope: SelectorScope = SelectorScope.EVERY
    #: Narrows the selection before the condition is evaluated, reusing the
    #: same grammar (e.g. runs whose text is a bare affiliation numeral).
    filter: Condition | None = None


class BaseRule(StrictModel):
    rule_id: str = Field(min_length=1)
    category: str = "style"
    message: str = Field(min_length=1)
    severity: Severity = Severity.MEDIUM
    applies_to_section: list[Section] = Field(default_factory=list)
    selector: Selector = Field(default_factory=Selector)
    on_missing_section: OnMissingSection = OnMissingSection.SKIP
    priority: int = 100
    #: Human-readable form of the expectation, used verbatim in the report's
    #: `expected` field when present.
    expected_repr: str = ""


class DeterministicRule(BaseRule):
    """A pure attribute comparison. No external calls."""

    check_type: Literal[CheckType.DETERMINISTIC] = CheckType.DETERMINISTIC
    condition: Condition
    auto_fixable: bool = False
    fix_action: FixAction | None = None
    fix_params: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _fix_action_matches_fixability(self) -> DeterministicRule:
        if self.auto_fixable and self.fix_action is None:
            raise ValueError("'auto_fixable' is true but no 'fix_action' is set")
        if not self.auto_fixable and self.fix_action not in (None, FixAction.SUGGEST_ONLY):
            raise ValueError(
                f"'fix_action' is '{self.fix_action.value if self.fix_action else ''}' "
                "but 'auto_fixable' is false"
            )
        return self


class SemanticRule(BaseRule):
    """Contextual judgement: ordering, exact phrasing, content presence.

    Never auto-fixable -- a semantic rule reports a suggestion for a human.
    """

    check_type: Literal[CheckType.SEMANTIC] = CheckType.SEMANTIC
    prompt_template: str | None = None
    prompt_file: str | None = None
    prompt_vars: list[str] = Field(default_factory=list)
    auto_fixable: Literal[False] = False
    fix_action: Literal[FixAction.SUGGEST_ONLY] | None = FixAction.SUGGEST_ONLY

    @model_validator(mode="after")
    def _exactly_one_prompt_source(self) -> SemanticRule:
        if bool(self.prompt_template) == bool(self.prompt_file):
            raise ValueError("set exactly one of 'prompt_template' or 'prompt_file'")
        return self


Rule = Annotated[DeterministicRule | SemanticRule, Field(discriminator="check_type")]


class RulesetDefaults(StrictModel):
    severity: Severity = Severity.MEDIUM


class Ruleset(StrictModel):
    """One journal template.

    `section_order` and `section_synonyms` live here rather than in the
    segmenter because heading vocabulary is the most journal-specific thing in
    the system; keeping them in code would make spec section 2's "a second
    template is a config addition" false.
    """

    ruleset_id: str = Field(min_length=1)
    ruleset_version: str = Field(min_length=1)
    journal_name: str = ""
    section_order: list[Section] = Field(default_factory=list)
    required_sections: list[Section] = Field(default_factory=list)
    optional_sections: list[Section] = Field(default_factory=list)
    section_synonyms: dict[Section, list[str]] = Field(default_factory=dict)
    defaults: RulesetDefaults = Field(default_factory=RulesetDefaults)
    rules: list[Rule] = Field(default_factory=list)

    @model_validator(mode="after")
    def _rule_ids_are_unique(self) -> Ruleset:
        seen: set[str] = set()
        for rule in self.rules:
            if rule.rule_id in seen:
                raise ValueError(f"duplicate rule_id '{rule.rule_id}'")
            seen.add(rule.rule_id)
        return self

    def by_id(self, rule_id: str) -> DeterministicRule | SemanticRule | None:
        for rule in self.rules:
            if rule.rule_id == rule_id:
                return rule
        return None

    @property
    def rule_ids(self) -> list[str]:
        return [rule.rule_id for rule in self.rules]


class SemanticVerdict(BaseModel):
    """The structured output a semantic check returns.

    One definition serving two jobs: it is handed to google-genai as
    `response_schema`, and it validates what comes back. Kept flat, with
    defaults instead of optionals, because nested and nullable schemas degrade
    structured-output reliability.
    """

    violation: bool
    explanation: str = ""
    location_hint: str = ""
    suggested_fix: str = ""
    confidence: float = 0.0
