"""Loads rule configs via importlib.resources.

Never `__file__`-relative: that breaks under PyInstaller --onedir, and finding
out at packaging time is far more expensive than getting it right now.
"""
