"""Rule and Ruleset models (spec section 5.2, with additions).

Pydantic rather than dataclasses: rule configs are human-authored external JSON,
which is the one boundary where runtime validation earns its cost.

Additions beyond the spec: `selector` (section alone cannot express "the caption
paragraph of each table"), `prompt_file` (an 8-line prompt escaped into a JSON
string is unreviewable), `on_missing_section`, and `priority`.
"""
