"""Headless command-line driver (Task 13).

Ships before the GUI: it makes the pipeline usable on a machine with no
display, lets real reports be reviewed early, and doubles as the acceptance-test
harness.
"""

from __future__ import annotations

import argparse
import os
import sys
from collections.abc import Sequence
from pathlib import Path

from manuscript_validator import __version__
from manuscript_validator.errors import ManuscriptValidatorError
from manuscript_validator.pipeline import PipelineOptions, PipelineResult, run

#: Environment variable the CLI reads the Gemini API key from -- the UI
#: (Task 14) instead reads `config.settings_store`, which needs the DPAPI
#: backend this headless shell has no business depending on.
API_KEY_ENV_VAR = "GEMINI_API_KEY"

EXIT_OK = 0
EXIT_NEEDS_REVIEW = 1
EXIT_HIGH_SEVERITY = 2
EXIT_ERROR = 3


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


def _print_progress(stage: str, fraction: float) -> None:
    print(f"[{fraction:4.0%}] {stage}", file=sys.stderr)


def _print_summary(result: PipelineResult) -> None:
    print(f"{result.source}: {result.violation_count} violation(s) found")
    print(f"  auto-fixed:   {result.fixed_count}")
    print(f"  needs review: {result.needs_review_count}")
    if result.check_failed_count:
        print(f"  check failed: {result.check_failed_count} (semantic checks not evaluated)")
    for name, path in sorted(result.outputs.items()):
        print(f"  wrote {name}: {path}")


def _exit_code_for(result: PipelineResult) -> int:
    if result.needs_review_count == 0:
        return EXIT_OK
    if result.max_open_severity == "high":
        return EXIT_HIGH_SEVERITY
    return EXIT_NEEDS_REVIEW


def _run_validate(args: argparse.Namespace) -> int:
    source: Path = args.source
    if not source.is_file():
        print(f"error: {source}: not a file", file=sys.stderr)
        return EXIT_ERROR

    api_key = None if args.no_semantic else os.environ.get(API_KEY_ENV_VAR)
    options = PipelineOptions(
        output_dir=args.output_dir,
        run_semantic=not args.no_semantic,
        apply_fixes=not args.no_fix,
        ruleset_id=args.ruleset,
        api_key=api_key,
    )

    try:
        result = run(source, options, progress=_print_progress)
    except ManuscriptValidatorError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return EXIT_ERROR

    _print_summary(result)
    return _exit_code_for(result)


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.command is None:
        parser.print_help()
        return 2
    if args.command == "validate":
        return _run_validate(args)
    parser.print_help()
    return 2


if __name__ == "__main__":
    sys.exit(main())
