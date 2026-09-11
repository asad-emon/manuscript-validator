"""Effective formatting resolution and canonical text extraction.

The highest-risk module in the project. `run.font.name` returns None whenever
formatting is inherited from a style, which is the normal case in a real
manuscript, so every font check would report `found: None` without this.

Resolution order, highest priority first:
    run w:rPr -> character style -> paragraph style + w:basedOn chain
    -> w:docDefaults -> theme fonts in word/theme/theme1.xml

`paragraph_text` is the single canonical text extractor. Every caller -- word
counts, segmentation, caption matching, the Gemini payload -- must use it;
divergent extraction across modules produces inconsistent results that are
miserable to debug.
"""
