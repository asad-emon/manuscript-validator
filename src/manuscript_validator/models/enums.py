"""Enumerations.

All subclass `str` so `json.dumps` needs no custom encoder and comparisons stay
readable at call sites.
"""

from __future__ import annotations

from enum import Enum


class Section(str, Enum):
    """The fixed section vocabulary for this template (spec section 5.3)."""

    TITLE = "title"
    AUTHOR = "author"
    ABSTRACT = "abstract"
    AFFILIATION = "affiliation"
    INTRODUCTION = "introduction"
    METHODS_AND_MATERIALS = "methods_and_materials"
    RESULT = "result"
    DISCUSSION = "discussion"
    CONCLUSION = "conclusion"
    CONFLICT_OF_INTEREST = "conflict_of_interest"
    FUNDING = "funding"
    ACKNOWLEDGEMENT = "acknowledgement"
    REFERENCES = "references"
    CORRESPONDING_AUTHOR_ADDRESS = "corresponding_author_address"

    #: Not a manuscript section. Assigned to paragraphs segmentation could not
    #: place, and serialised as null so the AST matches spec section 5.1.
    UNKNOWN = "unknown"


class Severity(str, Enum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class CheckType(str, Enum):
    DETERMINISTIC = "deterministic"
    SEMANTIC = "semantic"


class ViolationStatus(str, Enum):
    """Spec section 5.4 shows only `fixed`; section 4.2 adds `check_failed`."""

    OPEN = "open"
    FIXED = "fixed"
    FIX_FAILED = "fix_failed"
    NEEDS_REVIEW = "needs_review"
    CHECK_FAILED = "check_failed"
    #: Two rules targeted one attribute with different values, so neither was
    #: applied. See docs/decisions.md and `autofix.engine`.
    CONFLICT = "conflict"
    SUPPRESSED = "suppressed"


class Operator(str, Enum):
    """Condition operators, keyed to the comparator registry (Task 6)."""

    EQ = "=="
    NE = "!="
    LT = "<"
    LTE = "<="
    GT = ">"
    GTE = ">="
    IN = "in"
    NOT_IN = "not_in"
    MATCHES_REGEX = "matches_regex"
    NOT_MATCHES_REGEX = "not_matches_regex"
    IS_TITLE_CASE = "is_title_case"
    IS_UPPERCASE_LITERAL = "is_uppercase_literal"
    WORD_COUNT_LTE = "word_count_lte"
    IS_NON_EMPTY = "is_non_empty"


class FixAction(str, Enum):
    """The spec section 8 registry, plus three additions.

    `SET_CAPTION_POSITION` and `SET_TITLE_CASE` are defined but disabled in v1
    -- see docs/decisions.md. `SUGGEST_ONLY` marks a semantic rule that reports
    a suggestion rather than applying anything.
    """

    SET_FONT = "set_font"
    SET_FONT_SIZE = "set_font_size"
    SET_BOLD = "set_bold"
    SET_ITALIC = "set_italic"
    SET_SUPERSCRIPT = "set_superscript"
    SET_UPPERCASE_LITERAL = "set_uppercase_literal"
    SET_CAPTION_POSITION = "set_caption_position"
    SET_NUMBERING_STYLE = "set_numbering_style"
    INSERT_LINE_BREAK = "insert_line_break"
    STRIP_TRAILING_COLON = "strip_trailing_colon"
    SET_CITATION_BRACKETS = "set_citation_brackets"
    SET_TITLE_CASE = "set_title_case"
    SUGGEST_ONLY = "suggest_only"


class NodeType(str, Enum):
    """What a rule's selector resolves to."""

    RUN = "run"
    PARAGRAPH = "paragraph"
    TABLE = "table"
    FIGURE = "figure"
    DOCUMENT = "document"
    SECTION_TEXT = "section_text"


class SelectorScope(str, Enum):
    EVERY = "every"
    ANY = "any"
    FIRST = "first"


class OnMissingSection(str, Enum):
    """What a rule does when its section was not detected.

    Default `SKIP`: a missing Methods section should produce one
    `section-present-*` violation, not forty identical formatting ones.
    """

    SKIP = "skip"
    VIOLATION = "violation"
    CHECK_FAILED = "check_failed"


class FormattingSource(str, Enum):
    """Where an effective formatting value was resolved from (Task 4)."""

    RUN = "run"
    CHARACTER_STYLE = "character_style"
    PARAGRAPH_STYLE = "paragraph_style"
    DOC_DEFAULT = "doc_default"
    THEME = "theme"
    UNRESOLVED = "unresolved"


class SectionSource(str, Enum):
    """How a paragraph got its section label (Task 5)."""

    HEADING = "heading"
    POSITIONAL = "positional"
    INHERITED = "inherited"
    OVERRIDE = "override"
    UNKNOWN = "unknown"


class CaptionPosition(str, Enum):
    ABOVE = "above"
    BELOW = "below"
    #: Caption lives in a merged first row of the table itself; not auto-fixable.
    INSIDE = "inside"


class NumberingStyle(str, Enum):
    ROMAN = "roman"
    ARABIC = "arabic"
    OTHER = "other"
