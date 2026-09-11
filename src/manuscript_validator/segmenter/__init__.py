"""AST -> section-labelled AST (Task 5)."""

from manuscript_validator.segmenter.section_index import (
    SegmentationResult,
    generate_section_present_rules,
    segment,
)

__all__ = ["SegmentationResult", "generate_section_present_rules", "segment"]
