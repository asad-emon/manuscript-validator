"""Section -> ordered paragraph ids, with confidence and provenance.

Also owns the missing-section contract. A section that is absent makes
`select_nodes` return an empty list, which would let FR-11 pass on a manuscript
with no title at all; rules therefore declare `on_missing_section` and required
sections generate their own `section-present-*` violations.
"""
