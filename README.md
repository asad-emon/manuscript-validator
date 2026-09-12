# Manuscript Formatting Validator & Auto-Corrector

Validates a medical-journal manuscript (`.docx`) against a fixed journal
formatting template, auto-fixes deterministic violations, and outputs a
corrected document, a tracked-changes redline, an annotated review copy, a
JSON report, and an audit log.

- Specification: [`technical_specification.md`](technical_specification.md)
- Task list and status: [`DEVELOPMENT_CHECKLIST.md`](DEVELOPMENT_CHECKLIST.md)
- Design decisions and spec deviations: [`docs/decisions.md`](docs/decisions.md)

## Layout

The pipeline (`parser`, `segmenter`, `rules`, `autofix`, `report`, `output`)
has **no dependency on Qt** and runs headlessly. The desktop UI (`ui/`,
`app.py`) is a thin shell over `pipeline.run()`; the CLI (`cli.py`) is a
second shell over the same call. Neither shell contains validation logic.

## Installation

```bash
pip install -e ".[dev]"        # CLI + full test suite, no GUI
pip install -e ".[dev,gui]"    # also installs PySide6, for the desktop UI
```

Windows-only extras (`pywin32`, for the DPAPI-backed settings store) are a
separate `windows` extra and are never required on Linux/macOS.

## Usage (CLI)

```bash
manuscript-validator validate paper.docx -o out/
```

Writes five files into `out/`, all named after the source file's stem:

| File | Contents |
|---|---|
| `<stem>.corrected.docx` | The manuscript with every auto-fixable violation applied directly |
| `<stem>.tracked.docx` | The same edits as Word tracked changes (`w:rPrChange` for formatting, `w:ins`/`w:del` for text), for a human reviewer to accept/reject |
| `<stem>.annotated.docx` | A copy of the **original** with a native Word comment on every violation that has somewhere to anchor to |
| `<stem>.report.json` | The full machine-readable `ValidationReport` (spec section 5.4) |
| `<stem>.audit.json` | One entry per applied fix: rule id, location, before/after values, timestamp (spec section 5.5) |

The original file is never modified; every output goes to `-o`/`--output-dir`,
never beside the source.

Useful flags:

- `--no-semantic` — skip Gemini-backed checks (section ordering, exact
  phrasing, content-completeness rules) and run fully offline. Every semantic
  rule still appears in the report, marked `check_failed`.
- `--no-fix` — report violations without writing any corrections; `corrected.docx`
  is still produced but is byte-for-byte the same document, unpatched.
- `--ruleset NAME` — validate against a different bundled rule config
  (default `journal_v1`).

Exit code reflects the worst violation still needing review after fixing:

| Code | Meaning |
|---|---|
| `0` | Nothing left to review |
| `1` | Open violations remain, none high-severity |
| `2` | At least one open **high**-severity violation remains |
| `3` | The run itself failed (bad path, unreadable file) |

### Semantic checks (Gemini)

Semantic rules (section ordering, exact phrasing, content-completeness) call
the Gemini API and need a key. The CLI reads one environment variable:

```bash
export GEMINI_API_KEY="your-key-here"
manuscript-validator validate paper.docx -o out/
```

With no key set and `--no-semantic` not passed, every semantic rule reports
`check_failed` with reason `api_key_missing` rather than failing the run —
deterministic checks and autofix still complete normally. The desktop UI
instead stores the key through its Settings screen (encrypted at rest via
Windows DPAPI; see [`docs/decisions.md`](docs/decisions.md)), and prompts for
one on first launch.

## Bumping the ruleset version

`src/manuscript_validator/rules/config/journal_v1.json`'s top-level
`ruleset_version` should change whenever a rule's *condition*, *severity*, or
*fix behaviour* changes — not for a purely cosmetic edit like a `message`
wording tweak. This matters for one specific reason: the semantic-check cache
(`rules/cache.py`) keys on `ruleset_version` alongside the rule id, prompt
template, model id, and section text, specifically so that editing a rule
invalidates every cached verdict for it automatically. Skipping the bump means
a stale verdict from the *old* rule definition can be served for the *new*
one.

Procedure:

1. Edit the rule(s) in `journal_v1.json`.
2. Bump `ruleset_version` (semver-ish; `"1.0.0"` -> `"1.1.0"` for a rule
   change, `"1.0.0"` -> `"2.0.0"` for a change to `section_order`,
   `required_sections`, or anything that would change which sections exist).
3. If you added or removed a rule, add or remove its `violating()` fixture in
   `tests/fixtures/factory.py` (`MUTATIONS`/`MUTATION_TARGETS`) — `pytest
   tests/test_rules_coverage.py` fails loudly if the two ever drift apart.
4. Run the full suite: `pytest -q`. `tests/test_rules_engine.py` re-validates
   every rule against its own `violating()` fixture and the compliant one, so
   a condition typo shows up immediately.

## Development

Requires Python 3.10+.

```bash
pip install -e ".[dev,gui]"
pytest -q && ruff check src/ tests/ && mypy --strict src/
```

The default test run excludes the `live` (real Gemini API calls) and
`windows` (DPAPI, PyInstaller) markers. `gui`-marked tests run by default
under `QT_QPA_PLATFORM=offscreen`, which `tests/conftest.py` sets
automatically if nothing else already has.

Five real, user-supplied manuscripts live in `tests/fixtures/real/`
(gitignored — they contain real author names/emails/ORCIDs) and are exercised
by every task's test suite when present; the repository itself ships with
none.
