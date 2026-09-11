"""Replays a FixPlan against a fresh clone of the original bytes.

The corrected document is produced by patching a clone, not by serialising the
AST: the AST models roughly ten attributes per run, and regenerating a document
from it would discard images, section properties, headers, numbering,
hyperlinks, fields, footnotes, and equations. See docs/decisions.md (C2).
"""
