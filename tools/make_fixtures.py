"""Write factory-built manuscripts to disk for manual inspection in Word.

Not part of the installed package; run directly from a checkout:

    python tools/make_fixtures.py [output_dir]

Defaults to `tools/_out/`, which is gitignored.
"""

from __future__ import annotations

import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_REPO_ROOT / "tests"))

from fixtures.factory import RULE_IDS, build_compliant, violating  # noqa: E402


def main(argv: list[str]) -> int:
    out_dir = Path(argv[0]) if argv else _REPO_ROOT / "tools" / "_out"
    out_dir.mkdir(parents=True, exist_ok=True)

    doc, _ = build_compliant()
    doc.save(out_dir / "compliant.docx")

    for rule_id in RULE_IDS:
        doc, _ = violating(rule_id)
        doc.save(out_dir / f"violating_{rule_id}.docx")

    print(f"Wrote {1 + len(RULE_IDS)} fixtures to {out_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
