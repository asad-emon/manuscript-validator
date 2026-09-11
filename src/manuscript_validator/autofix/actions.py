"""Fix action registry.

Each action is a small isolated function over a single paragraph or run, with no
cross-paragraph side effects, so each is independently unit-testable against a
synthetic node (spec section 13).

`set_caption_position` and `set_title_case` are registered but disabled in v1:
a caption move is a structural edit spec section 8 forbids and the redline
cannot represent, and automatic title-casing mangles acronyms and Latin
binomials. Both are reported as flag-only violations instead.
"""
