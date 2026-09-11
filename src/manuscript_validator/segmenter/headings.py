"""Heading detection and vocabulary matching.

Detection is a weighted score, not a branch chain: style name and outline level,
bold runs, literal uppercase, word count, terminal punctuation, and vocabulary
hits each contribute. Matching normalises (NFKC, casefold, strip enumeration and
trailing colon) then escalates exact -> token-set -> fuzzy. Token-set matching is
what makes "materials and methods" equivalent to "methods and materials" without
a special case.

The synonym table and section order live in the rule config JSON, not here:
heading vocabulary is the most journal-specific thing in the system, and spec
section 2's "a second template is a config addition" is false otherwise.
"""
