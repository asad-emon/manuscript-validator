"""Semantic result cache.

Keyed on normalised section *text* rather than document version (as spec
section 7.2 suggests). Formatting fixes do not change plain text, so the
post-autofix re-validation required by FR-7 becomes a complete cache hit and
costs no additional API calls.
"""
