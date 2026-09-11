"""Figure detection.

Uses `//w:drawing | //w:pict` then `ancestor::w:p[1]`. `document.inline_shapes`
is insufficient: its xpath misses floating (`wp:anchor`) and VML images, and
`InlineShape` has no paragraph back-reference.
"""
