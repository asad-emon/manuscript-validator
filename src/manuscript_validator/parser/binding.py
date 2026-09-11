"""ElementIndex: stable ids mapped to live XML elements.

Ids are positional at build time only; the index then holds element objects,
which survive reparenting. Because every clone is byte-identical to the
original at build time, ids resolve 1:1 across the read, fixed, redline, and
annotated clones.

Runs are indexed with `.//w:r[not(ancestor::w:rPr)]`, not `./w:r`: python-docx's
`Paragraph.runs` skips runs inside `w:ins` and `w:hyperlink`, so a manuscript
carrying co-author tracked changes would be partly invisible to the validator.
"""
