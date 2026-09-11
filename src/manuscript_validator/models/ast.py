"""Document AST (spec section 5.1).

A pure-data, deep-copyable snapshot -- it holds no references to python-docx or
lxml objects. Write-back is the job of `parser.binding.ElementIndex`; see
docs/decisions.md (C2).
"""
