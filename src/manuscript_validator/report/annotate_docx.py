"""Inserts native Word comments, one per violation.

python-docx 1.2.0 has native comment support (`Document.add_comment`), which
wires comments.xml, the content-type override, the relationship, and the range
markers automatically -- so this does not hand-roll OOXML, despite what spec
section 11 implies.

Comments go on a clone of the *original*, so the author sees them against what
they submitted, never on the corrected document or the redline.
"""
