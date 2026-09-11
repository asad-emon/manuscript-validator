"""Gemini adapter -- the only module importing google.genai.

Every failure is classified and returned, never raised: a missing key, a dropped
connection, or a malformed response becomes a `check_failed` violation so the
deterministic pipeline still completes (spec sections 4.2 and 13).
"""
