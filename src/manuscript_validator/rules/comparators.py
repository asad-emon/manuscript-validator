"""Comparator registry keyed by `condition.operator`.

Every comparator takes `(actual, expected)` and returns `bool`. `actual` comes
straight from `getattr(node, condition.attribute)` and can legitimately be
`None` (an unresolved font, a paragraph with no runs) -- every comparator
treats that as "does not satisfy" rather than raising, since an unresolved
attribute is exactly the case a rule exists to catch.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from typing import Any

from manuscript_validator.models.enums import Operator
from manuscript_validator.parser.effective import is_uppercase_literal

#: Operators schema.py's `Condition` already requires a non-None `value` for
#: (everything except the three unary ones), so ordering comparisons only need
#: to guard against a `None` *actual*.
_ORDERING: dict[Operator, Callable[[Any, Any], bool]] = {
    Operator.LT: lambda a, b: a < b,
    Operator.LTE: lambda a, b: a <= b,
    Operator.GT: lambda a, b: a > b,
    Operator.GTE: lambda a, b: a >= b,
}


def _is_title_case(text: str) -> bool:
    return bool(text) and text.istitle()


def _matches_regex(text: Any, pattern: str) -> bool:
    return bool(re.search(pattern, text)) if isinstance(text, str) else False


_COMPARATORS: dict[Operator, Callable[[Any, Any], bool]] = {
    Operator.EQ: lambda a, b: a == b,
    Operator.NE: lambda a, b: a != b,
    Operator.IN: lambda a, b: a in b,
    Operator.NOT_IN: lambda a, b: a not in b,
    Operator.MATCHES_REGEX: _matches_regex,
    Operator.NOT_MATCHES_REGEX: lambda a, b: not _matches_regex(a, b),
    Operator.IS_TITLE_CASE: lambda a, _b: _is_title_case(a or ""),
    Operator.IS_UPPERCASE_LITERAL: lambda a, _b: is_uppercase_literal(a or ""),
    Operator.WORD_COUNT_LTE: lambda a, b: len((a or "").split()) <= b,
    Operator.IS_NON_EMPTY: lambda a, _b: bool(a),
}


def evaluate(operator: Operator, actual: Any, expected: Any) -> bool:
    """True if `actual` satisfies `operator` against `expected`.

    Ordering operators short-circuit to `False` on a `None` actual (an
    unresolved font size fails a `>=` check rather than raising `TypeError`)."""
    if operator in _ORDERING:
        if actual is None:
            return False
        return _ORDERING[operator](actual, expected)
    return _COMPARATORS[operator](actual, expected)


__all__ = ["evaluate"]
