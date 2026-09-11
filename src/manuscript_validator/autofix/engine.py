"""Fix planning, conflict detection, and the audit log.

Conflict detection is not in the spec but FR-11 depends on it: global-font,
abstract-size, heading-style, and body-text-size all write the same runs, so a
mislabelled paragraph produces two fixes targeting one attribute with different
values. Last writer wins, re-validation reports the loser, and the audit log
records a change that did not survive. Fix ops are therefore grouped by
(element_id, attribute) and a group with differing targets is applied not at
all, with every member marked `conflict`.
"""
