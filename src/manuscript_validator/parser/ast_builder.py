"""Builds the AST by walking the document body in true order.

Iterates `body.iterchildren()` rather than `document.paragraphs`, which loses
paragraph/table interleaving and so breaks caption-position detection. Table
cell paragraphs are emitted into the flat paragraph list tagged `in_table`, as
spec section 5.1 omits them entirely.
"""
