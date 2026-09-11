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
has **no dependency on Qt** and runs headlessly. The desktop UI is a thin
shell over `pipeline.run()`; the CLI is a second shell over the same call.

## Development

Requires Python 3.10+.

```bash
pip install -e ".[dev]"
pytest -q && ruff check src/ tests/ && mypy src/
```

The default test run excludes `live` (real Gemini calls) and `windows`
(DPAPI, PyInstaller) markers.
