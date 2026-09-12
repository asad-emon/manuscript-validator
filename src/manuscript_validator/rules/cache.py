"""Semantic result cache.

Keyed on normalised section *text* rather than document version (as spec
section 7.2 suggests). Formatting fixes do not change plain text, so the
post-autofix re-validation required by FR-7 becomes a complete cache hit and
costs no additional API calls.

The key includes the ruleset version, the rule id, the prompt template, the
model id, and the temperature alongside the text -- so a rule edit, a prompt
change, or a model upgrade invalidates automatically instead of silently
serving a verdict for a question that is no longer being asked.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field

from manuscript_validator.rules.schema import SemanticVerdict


def normalize_text(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip().casefold()


@dataclass
class SemanticCache:
    """An in-memory cache, one per pipeline run.

    Not persisted across runs -- v1's requirement is "the post-fix
    re-validation in *this* run costs nothing", not "never ask twice across
    the tool's lifetime", and a persistent cache would need its own
    invalidation-on-disk story this project doesn't need yet.
    """

    ruleset_version: str
    model_id: str
    temperature: float = 0.0
    _store: dict[str, SemanticVerdict] = field(default_factory=dict)

    def _key(self, rule_id: str, prompt_template: str, text: str) -> str:
        raw = "|".join(
            [
                self.ruleset_version,
                rule_id,
                prompt_template,
                self.model_id,
                repr(self.temperature),
                normalize_text(text),
            ]
        )
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()

    def get(self, rule_id: str, prompt_template: str, text: str) -> SemanticVerdict | None:
        return self._store.get(self._key(rule_id, prompt_template, text))

    def set(self, rule_id: str, prompt_template: str, text: str, verdict: SemanticVerdict) -> None:
        self._store[self._key(rule_id, prompt_template, text)] = verdict

    def __len__(self) -> int:
        return len(self._store)


__all__ = ["SemanticCache", "normalize_text"]
