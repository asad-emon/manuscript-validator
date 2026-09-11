"""Positional fallback for front matter.

Title, author, affiliation, and corresponding-author blocks usually carry no
heading, so they are resolved by a scored state machine over the paragraphs
preceding the first recognised heading -- not by fixed indices.
"""
