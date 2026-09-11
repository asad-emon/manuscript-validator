"""Development secret box for non-Windows machines.

Opt-in only, via an environment variable: production must fail loudly on a
platform with no secure store rather than silently degrade to weaker storage.
"""
