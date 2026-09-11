"""`.docx` -> AST (Task 4)."""

from manuscript_validator.parser.ast_builder import build_ast
from manuscript_validator.parser.binding import ElementIndex, build_element_index

__all__ = ["ElementIndex", "build_ast", "build_element_index"]
