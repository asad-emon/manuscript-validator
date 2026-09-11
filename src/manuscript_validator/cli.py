"""Headless command-line driver (Task 13).

Ships before the GUI: it makes the pipeline usable on a machine with no
display, lets real reports be reviewed early, and doubles as the acceptance-test
harness.
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence
from pathlib import Path

from manuscript_validator import __version__


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="manuscript-validator",
        description=(
            "Validate a medical-journal manuscript against a journal formatting "
            "template, auto-fix deterministic violations, and write a corrected "
            "document, a tracked-changes redline, an annotated copy, a JSON "
            "report, and an audit log."
        ),
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    subcommands = parser.add_subparsers(dest="command", metavar="COMMAND")

    validate = subcommands.add_parser(
        "validate",
        help="validate and correct a manuscript",
        description="Validate and correct a .docx manuscript.",
    )
    validate.add_argument("source", type=Path, help="path to the .docx manuscript")
    validate.add_argument(
        "-o",
        "--output-dir",
        type=Path,
        required=True,
        help="directory to write outputs into (never beside the original)",
    )
    validate.add_argument(
        "--no-semantic",
        action="store_true",
        help="skip Gemini checks and run fully offline",
    )
    validate.add_argument(
        "--no-fix",
        action="store_true",
        help="report violations without applying any corrections",
    )
    validate.add_argument(
        "--ruleset",
        default="journal_v1",
        help="rule config to validate against (default: journal_v1)",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.command is None:
        parser.print_help()
        return 2
    raise NotImplementedError("Task 13")


if __name__ == "__main__":
    sys.exit(main())
