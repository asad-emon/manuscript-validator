# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec for the Windows desktop build (Task 15).

Run via packaging/build.ps1, or directly:
    pyinstaller packaging\\build.spec --noconfirm --clean

Two things this spec exists to get right, both named in
DEVELOPMENT_CHECKLIST.md's Task 15 as the usual PyInstaller failure modes:

1. `journal_v1.json` and `rules/prompts/*.txt` are loaded via
   `importlib.resources` (docs/decisions.md, C5) rather than a `__file__`-
   relative path -- but that only works if PyInstaller's `datas` actually
   ships them at the same package-relative location, which is what the
   `datas` list below does.
2. `pywin32`'s `win32crypt` (config/settings_store_dpapi.py) is imported
   lazily inside a method, specifically so this module stays importable on
   Linux with no pywin32 installed -- but a lazy/conditional import is
   exactly what PyInstaller's static analysis misses, so it must be named
   explicitly in `hiddenimports`. `win32timezone` is pywin32's own runtime
   dependency for datetime conversions and has the same problem.
"""

from pathlib import Path

ROOT = Path(SPECPATH).parent
SRC = ROOT / "src"

datas = [
    (
        str(SRC / "manuscript_validator" / "rules" / "config"),
        "manuscript_validator/rules/config",
    ),
    (
        str(SRC / "manuscript_validator" / "rules" / "prompts"),
        "manuscript_validator/rules/prompts",
    ),
]

a = Analysis(
    [str(ROOT / "main.py")],
    pathex=[str(SRC)],
    binaries=[],
    datas=datas,
    hiddenimports=["win32crypt", "win32timezone"],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)
pyz = PYZ(a.pure, a.zipped_data)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="ManuscriptValidator",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,  # --windowed: no console window behind the Qt UI
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name="ManuscriptValidator",  # --onedir: dist/ManuscriptValidator/
)
