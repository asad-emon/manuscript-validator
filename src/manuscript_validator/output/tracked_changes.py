"""Word tracked-changes redline.

Formatting edits are recorded as `w:rPrChange`, not the `w:ins` spec section 9
calls for -- `w:ins` is for text edits, and using it for a font change shows the
author a deleted and retyped sentence. See docs/decisions.md (C3).

Three traps, each verified: inside `w:del`, `w:t` must be renamed `w:delText`;
`w:rPrChange` must be the last child of `w:rPr`, and python-docx will append
later property elements after it if it is attached too early; revision ids share
one namespace with any revisions already in the incoming document.
"""
