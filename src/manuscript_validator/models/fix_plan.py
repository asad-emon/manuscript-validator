"""FixPlan and FixOp.

Fixes are planned as data and replayed twice -- once for `corrected.docx`, once
for the tracked-changes redline -- which is what guarantees the two outputs
cannot diverge. See docs/decisions.md (C2).
"""
