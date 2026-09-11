# Technical Specification: Manuscript Formatting Validator & Auto-Corrector

## 1. Purpose

Build a system that ingests a medical-journal manuscript as a `.docx` file, validates it against a fixed journal formatting template, produces a structured violation report, and automatically applies safe corrections — outputting a corrected `.docx` plus a tracked-changes redline and an audit log.

This spec targets a single implementation agent. It is intentionally explicit about data shapes, module boundaries, and the rule set so the agent can implement without needing design decisions re-litigated.

## 2. Scope

**In scope**
- Parsing a `.docx` manuscript into a structured, queryable representation.
- Detecting manuscript sections (Title, Author, Abstract, Affiliation, body sections, References, etc.).
- Validating font, size, style (bold/italic/superscript/uppercase), word counts, section order, and structural rules defined in Section 6.
- Producing a machine-readable violation report (JSON) and a human-readable report (annotated `.docx` with comments).
- Auto-fixing deterministic formatting violations directly in a copy of the document.
- Flagging non-deterministic (semantic/structural) violations for human review with a suggested fix, not an automatic one.
- Exporting: corrected `.docx`, tracked-changes `.docx`, JSON report, audit log.

**Out of scope (v1)**
- Multi-format input (PDF, LaTeX) — `.docx` only.
- Multi-journal template support — this version hardcodes one rule set (Section 6), but the rule engine must be designed so a second template is a config addition, not a code change.
- Real-time collaborative editing.

## 3. Functional Requirements

| ID | Requirement |
|---|---|
| FR-1 | System accepts a single `.docx` file upload. |
| FR-2 | System parses the document into an internal AST (Section 5.1). |
| FR-3 | System segments the AST into named manuscript sections (Section 5.3). |
| FR-4 | System runs all applicable rules from the rule config against the segmented AST. |
| FR-5 | System classifies each rule as `deterministic` or `semantic` and routes accordingly (Section 7). |
| FR-6 | System produces a `ValidationReport` (Section 5.4) listing every violation with location, severity, and fixability. |
| FR-7 | System applies all `auto_fixable: true` violations to a cloned document and re-validates to confirm resolution. |
| FR-8 | System generates a tracked-changes version of the `.docx` showing every automatic edit. |
| FR-9 | System never mutates the original uploaded file. |
| FR-10 | System writes an audit log entry for every applied fix (rule ID, location, before value, after value, timestamp). |
| FR-11 | Running validation on an already-corrected document produces zero deterministic violations (idempotency). |

## 4. System Architecture

This is a **Windows desktop application** (PyQt/PySide), not a service. There is no upload/API boundary — the UI calls the pipeline modules in-process, in the same Python runtime, and everything runs locally on the user's machine.

```
┌─────────────────────────── Desktop App (single process) ───────────────────────────┐
│  Main Window  →  Parser → Segmenter → Rule Validator → ┬→ Report View               │
│  Settings Screen (API key)                              └→ Auto-Fix Engine → Output  │
└───────────────────────────────────────────────────────────────────────────────────────┘
                          │ (only outbound network calls: semantic checks)
                          ▼
                    Gemini API (cloud)
```

| Module | Responsibility | Depends on |
|---|---|---|
| `ui.main_window` | File picker, triggers pipeline, displays progress and results | `parser`, `validator`, `autofix`, `report` |
| `ui.settings_window` | Collects and persists the Gemini API key (Section 4.1) | `config.settings_store` |
| `parser` | `.docx` → AST | none |
| `segmenter` | AST → AST with `section` labels attached to each block | `parser` |
| `validator` | Segmented AST + rule config → list of `Violation` | `segmenter`, `config.settings_store` (for API key) |
| `report_generator` | Violations → JSON report + annotated `.docx` with comments, rendered in `ui.report_view` | `validator` |
| `autofix_engine` | Violations (auto_fixable subset) + AST → corrected AST + audit log | `validator` |
| `output_generator` | Corrected AST → `.docx` (+ tracked-changes variant), written to a user-chosen folder via a native Save dialog | `autofix_engine` |

Each module remains a pure function/class with typed input and output, called directly by the UI layer — no module reaches into another's internals, and none of them import Qt. This keeps the pipeline logic unit-testable headlessly (no GUI needed to run `tests/`) and means the UI could later be swapped (e.g. for a web frontend) without touching pipeline code.

### 4.1 Settings Screen

A dedicated `QDialog` (or equivalent) reachable from the main window's menu (`File → Settings` or a gear icon), responsible for:
- A single input field for the Gemini API key, masked like a password field, with a "Show" toggle.
- "Test connection" button that makes one lightweight validation call to the Gemini API and shows success/failure inline — this is required so users aren't left guessing why semantic checks silently fail later.
- "Save" persists the key via `config.settings_store` (Section 4.2); "Cancel" discards changes.
- On first launch, if no key is stored, the main window opens directly to this Settings screen (modal) before any file operations are enabled, with a short explanatory message: semantic checks (section ordering, exact phrasing, content presence) require a Gemini API key.

### 4.2 Settings Storage

- Store the key in a per-user config file, e.g. `%APPDATA%/ManuscriptValidator/config.json` (standard Windows convention — not the install directory, which may not be writable and shouldn't hold user data).
- **Do not store the key in plaintext.** Encrypt it at rest using Windows DPAPI (`win32crypt.CryptProtectData` via `pywin32`), which ties decryption to the logged-in Windows user account — this avoids bundling any custom secret/keyring management.
- `config.settings_store` exposes `get_api_key() -> str | None` and `set_api_key(key: str) -> None`; the `validator` module calls `get_api_key()` at the point a semantic check runs, never caching it long-term in memory beyond the current session.
- If `get_api_key()` returns `None` when a semantic check is attempted, treat it the same as a semantic-check network failure (Section 13): record `status: "check_failed"`, surface "API key not configured" in the report, and prompt the user to open Settings — never crash the pipeline.

## 5. Data Models

### 5.1 Document AST

```json
{
  "paragraphs": [
    {
      "id": "p0042",
      "text": "INTRODUCTION",
      "style_name": "Heading1",
      "section": null,
      "runs": [
        {
          "text": "INTRODUCTION",
          "font_name": "Times New Roman",
          "font_size_pt": 9,
          "bold": true,
          "italic": false,
          "superscript": false,
          "uppercase_literal": true
        }
      ],
      "alignment": "left",
      "is_table_caption": false,
      "line_break_after": true
    }
  ],
  "tables": [
    {
      "id": "t01",
      "caption_paragraph_id": "p0055",
      "caption_position": "above",
      "numbering_style": "roman",
      "cell_font_size_pt": 8,
      "referenced_in_paragraph_ids": ["p0053"]
    }
  ],
  "figures": [
    {
      "id": "f01",
      "caption_paragraph_id": "p0061",
      "caption_position": "below",
      "numbering_style": "arabic",
      "referenced_in_paragraph_ids": ["p0059"]
    }
  ]
}
```

Notes for implementation:
- `uppercase_literal` = true if the text is actually typed in caps (vs. rendered via a CSS/style-level all-caps transform) — journal rule requires literal uppercase, this distinction matters for the check.
- Build this via `python-docx`: iterate `document.paragraphs`, for each paragraph iterate `paragraph.runs` reading `run.font.name`, `run.font.size.pt`, `run.font.bold`, `run.font.italic`, `run.font.superscript`.
- Tables via `document.tables`; figures via inline shapes — figure/table caption detection uses proximity (nearest preceding/following paragraph matching a caption pattern, e.g. starts with `"Table"`/`"Fig."`).

### 5.2 Rule Config Schema

Rules are external JSON config, not hardcoded logic. One file per journal template.

```json
{
  "rule_id": "title-font-size",
  "category": "style",
  "applies_to_section": "title",
  "check_type": "deterministic",
  "condition": { "attribute": "font_size_pt", "operator": "==", "value": 14 },
  "severity": "high",
  "auto_fixable": true,
  "fix_action": "set_font_size",
  "fix_params": { "font_size_pt": 14 },
  "message": "Title must be font size 14."
}
```

For `check_type: "semantic"`, `condition` is replaced with a `prompt_template` string used to query the LLM validator (Section 7.2), and `fix_action` is omitted or set to `"suggest_only"`.

### 5.3 Section Labels

Fixed enum for this template, assigned during segmentation:

```
title, author, abstract, affiliation, introduction, methods_and_materials,
result, discussion, conclusion, conflict_of_interest, funding,
acknowledgement, references, corresponding_author_address
```

### 5.4 Violation & Report Schema

```json
{
  "rule_id": "title-font-size",
  "severity": "high",
  "section": "title",
  "paragraph_id": "p0001",
  "expected": "font_size_pt == 14",
  "found": "font_size_pt == 12",
  "auto_fixable": true,
  "status": "fixed"
}
```

```json
{
  "document_id": "uuid",
  "ruleset_version": "1.0.0",
  "validated_at": "2026-09-03T10:00:00Z",
  "summary": { "total": 14, "auto_fixed": 9, "needs_review": 5 },
  "violations": ["<Violation objects>"]
}
```

### 5.5 Audit Log Entry

```json
{
  "rule_id": "title-font-size",
  "paragraph_id": "p0001",
  "action": "set_font_size",
  "before": { "font_size_pt": 12 },
  "after": { "font_size_pt": 14 },
  "timestamp": "2026-09-03T10:00:02Z"
}
```

## 6. Rule Set (v1 — this journal template)

Encode each row below as a `Rule Config` object per Section 5.2. `check_type` column tells the agent which validator path to implement it under.

| Rule ID | Section | Check | check_type | auto_fixable |
|---|---|---|---|---|
| `global-font` | all | font = Times New Roman | deterministic | yes |
| `doc-order` | document | Title→Author→Abstract→Affiliation→Introduction→Methods and Materials→Result→Discussion→Conclusion→Conflict of Interest→Funding→Acknowledgement(optional)→References | semantic | no |
| `title-size` | title | font size 14 | deterministic | yes |
| `title-bold` | title | bold = true | deterministic | yes |
| `title-caps` | title | each word capitalized (title case) | deterministic | yes |
| `title-wordlimit` | title | word count ≤ 25 | deterministic | no (flag only) |
| `author-bold-superscript` | author | bold = true, affiliation numeral superscript, size 10 | deterministic | yes |
| `abstract-italic` | abstract | italic = true including heading | deterministic | yes |
| `abstract-size` | abstract | font size 9 | deterministic | yes |
| `abstract-wordlimit` | abstract | word count ≤ 250 | deterministic | no (flag only) |
| `abstract-structure` | abstract | sequence Introduction/Background → Objectives → "methods and materials" (exact phrase, not "materials and methods") → Results → Conclusion → line break → Keywords | semantic | no |
| `abstract-keywords-count` | abstract | keywords count between 3–5 | semantic | no |
| `affiliation-style` | affiliation | italic = true, size 7 | deterministic | yes |
| `affiliation-content` | affiliation | contains designation, place, email, ORCID | semantic | no |
| `heading-style` | body headings | uppercase (literal), bold, size 9, no colon, line break after | deterministic | yes |
| `body-text-size` | introduction, methods_and_materials, result, discussion | font size 9 | deterministic | yes |
| `citation-format` | body text | reference citations superscript + square brackets | deterministic | yes |
| `result-text-before-figure` | result | narrative text precedes each table/figure and cites it | semantic | no |
| `table-caption-position` | result | caption above table | deterministic | yes |
| `table-numbering` | result | Roman numerals | deterministic | yes |
| `table-text-size` | result | cell font size 8 | deterministic | yes |
| `figure-caption-position` | result | caption below figure | deterministic | yes |
| `figure-numbering` | result | Arabic numerals | deterministic | yes |
| `reference-style` | references | Vancouver system, italic, size 8, in-text superscript brackets | semantic (style check deterministic; citation format cross-check semantic) | partial |
| `corresponding-author-content` | corresponding_author_address | name, designation, place, mobile, email, ORCID all present | semantic | no |

Implementation note: several rows split into a deterministic sub-check (font/size/style — cheap, exact) and a semantic sub-check (content presence, exact phrasing, ordering). Split these into **two separate rule config entries** sharing a prefix (e.g. `reference-style-font`, `reference-style-vancouver-format`) rather than one mixed rule — keeps the router in Section 7 simple.

## 7. Validation Routing

```python
def validate(ast, rules):
    violations = []
    for rule in rules:
        nodes = select_nodes(ast, rule.applies_to_section)
        if rule.check_type == "deterministic":
            violations += run_deterministic(rule, nodes)
        elif rule.check_type == "semantic":
            violations += run_semantic(rule, nodes)
    return violations
```

### 7.1 Deterministic checks
Pure attribute comparisons against the AST (Section 5.1 fields). No external calls. Implement as a small registry of comparator functions keyed by `condition.operator` (`==`, `!=`, `<=`, `in`, `matches_regex`, `is_title_case`, `is_uppercase_literal`).

### 7.2 Semantic checks
For rules needing contextual judgment (ordering, exact phrasing, content presence, structural relationships), call an LLM with:
- The rule's `prompt_template`
- The relevant section's plain text (extracted from the AST, not the raw docx)
- A required structured JSON output format (violation: bool, explanation, suggested_fix)

Example prompt template for `abstract-structure`:
```
Given this abstract text, verify it follows this exact sequence:
Introduction/Background → Objectives → "methods and materials" (this exact phrase,
not "materials and methods") → Results → Conclusion → [line break] → Keywords.
Respond with JSON: {"violation": bool, "explanation": str, "location_hint": str}.

Abstract text:
"""
{abstract_text}
"""
```
Cache semantic results per section per document version to avoid redundant calls on re-validation.

## 8. Auto-Fix Engine

```python
def apply_fixes(ast, violations, rules_by_id):
    fixed_ast = deep_copy(ast)
    audit_log = []
    for v in violations:
        if not v.auto_fixable:
            continue
        rule = rules_by_id[v.rule_id]
        before = get_attribute(fixed_ast, v.paragraph_id, rule.fix_params)
        apply_fix_action(fixed_ast, v.paragraph_id, rule.fix_action, rule.fix_params)
        after = get_attribute(fixed_ast, v.paragraph_id, rule.fix_params)
        audit_log.append(build_audit_entry(rule, v, before, after))
        v.status = "fixed"
    return fixed_ast, audit_log
```

`fix_action` registry to implement: `set_font`, `set_font_size`, `set_bold`, `set_italic`, `set_superscript`, `set_uppercase_literal`, `set_caption_position`, `set_numbering_style`, `insert_line_break`. Each is a small, isolated function operating on one paragraph/run — no cross-paragraph side effects, to keep fixes independently testable.

After applying fixes, **re-run the deterministic validator on the fixed AST** and assert zero remaining deterministic violations for the rules that were marked fixed (regression guard — required by FR-11).

## 9. Output Generation

- Write `fixed_ast` back to OOXML via `python-docx`, save as `corrected.docx`.
- Generate a second copy with Word's native tracked-changes (`w:ins`/`w:del` elements) reflecting every audit log entry, so the author sees exactly what changed — this requires direct XML manipulation since `python-docx` doesn't support tracked changes natively; write a thin helper that wraps modified runs in `<w:ins>` nodes with author/date metadata.
- Round-trip validation: reopen `corrected.docx` programmatically before returning it, to confirm the file isn't corrupted.

## 10. Tech Stack

| Layer | Choice | Reason |
|---|---|---|
| UI framework | PyQt or PySide (Qt for Python) | Native-feeling Windows desktop UI; runs the pipeline in-process, no client/server split needed |
| Parsing/writing | Python + `python-docx` | Mature docx read/write; drop to raw XML via `docx.oxml` for tracked changes |
| Rule config | JSON files bundled with the app, loaded at startup | Human-editable, versionable, no redeploy for rule tweaks |
| Semantic validation | Gemini API with structured JSON output | Needed for ordering/phrasing/content-presence checks that regex can't handle reliably |
| Settings/config storage | Local `%APPDATA%` JSON file, API key encrypted via Windows DPAPI (`pywin32`) | Per-user, no server-side secrets store needed for a single-user desktop app (Section 4.2) |
| Storage | Local filesystem only — files the user explicitly opens/saves via native dialogs | No blob store or database; this is a single-user local tool, not a hosted service |
| Packaging | PyInstaller (`--onedir` recommended over `--onefile` — faster startup, easier to inspect if something's missing) | Bundles the Python interpreter and all dependencies (PyQt/PySide, python-docx, requests) so end users need no Python install |
| Installer | Inno Setup or NSIS | Wraps the PyInstaller output into a `Setup.exe` with Start Menu shortcut and a proper Windows uninstall entry |

The Gemini API key is never read from an environment variable or hardcoded — it comes exclusively from the Settings screen and encrypted local store described in Section 4.2, since this app has no deployment environment to set env vars in.

### 10.1 Packaging & Distribution Steps

Since compilation happens on an actual Windows machine, this is a straightforward native build, not a cross-compile:

1. `pip install pyinstaller` in the same Windows Python environment used for development.
2. Build with `pyinstaller --name ManuscriptValidator --windowed --onedir main.py` — `--windowed` suppresses the console window for a GUI app; add `--icon=app.ico` for a custom taskbar/exe icon.
3. Test the raw `dist/ManuscriptValidator/` output directly on a clean Windows machine (or VM) before wrapping it in an installer — confirms no missing DLLs/dependencies before adding installer complexity on top.
4. Write an Inno Setup `.iss` script (or NSIS `.nsi` script) that: installs `dist/ManuscriptValidator/` to `Program Files`, creates a Start Menu shortcut, registers an uninstaller entry in Windows "Apps & features", and optionally sets the app to request the API key on first run (Section 4.1) rather than during install.
5. (Optional, recommended before wide distribution) Sign the resulting `Setup.exe` with a code-signing certificate to avoid recurring Windows SmartScreen warnings for users.
6. Distribute the single signed `Setup.exe` — this is the only artifact end users need.

## 11. Project Structure

```
manuscript_validator/
  ui/
    main_window.py    # file picker, pipeline trigger, results display
    settings_window.py # API key entry, test-connection button (Section 4.1)
    report_view.py     # renders ValidationReport in-app
  config/
    settings_store.py  # get_api_key/set_api_key, DPAPI encryption (Section 4.2)
  parser/          # docx -> AST
  segmenter/        # AST -> section-labeled AST
  rules/
    config/         # journal_v1.json rule definitions
    engine.py        # rule routing (Section 7)
    deterministic.py
    semantic.py       # Gemini API calls
  autofix/
    engine.py
    actions.py       # fix_action registry
  report/
    generator.py
    annotate_docx.py # inserts native Word comments
  output/
    writer.py
    tracked_changes.py
  main.py             # app entry point, launches ui.main_window
  packaging/
    build.spec        # PyInstaller spec file
    installer.iss      # Inno Setup script (or installer.nsi for NSIS)
    app.ico
  tests/
    fixtures/          # sample docx files, valid + violating each rule
    test_parser.py
    test_deterministic.py
    test_semantic.py
    test_autofix.py
    test_idempotency.py
    test_settings_store.py
```

## 12. Testing Strategy

- **Fixture-driven**: one minimal `.docx` fixture per rule, each deliberately violating exactly that rule and no other, plus one fully-compliant fixture.
- **Deterministic rules**: assert exact violation detection and exact post-fix attribute values.
- **Semantic rules**: assert on the LLM's structured output shape and mock the LLM call in unit tests; run a small set of real-call integration tests separately.
- **Idempotency test**: run validate → autofix → validate again; second pass must report zero deterministic violations for fixed rules (FR-11).
- **Round-trip test**: every output `.docx` must reopen without corruption.

## 13. Non-Functional Requirements

- Original file is never mutated (FR-9) — enforce by working only on in-memory copies until final write.
- Rule config is swappable without code changes (new journal = new JSON file).
- All fix actions and audit entries must be independently unit-testable (no hidden coupling between fixes).
- Semantic (LLM) calls must have caching and timeout/retry handling; a semantic-check failure must not crash the pipeline — it should be recorded as `status: "check_failed"` and surfaced in the report.
- The Gemini API key is encrypted at rest via Windows DPAPI (Section 4.2) and never logged, written to the audit log, or included in exported reports.
- The app must run fully offline for all deterministic checks and auto-fixes; only semantic checks require network access, and their absence (no connection, missing key) degrades gracefully rather than blocking the rest of the pipeline.
- Pipeline modules (`parser`, `segmenter`, `validator`, `autofix`, `report`, `output`) must have no dependency on Qt, so they run and test headlessly in CI without a display.

## 14. Open Assumptions (flag if incorrect)

- "Conflict of interest," "Funding," and "Acknowledgement" sections are detected by exact heading text match (case-insensitive), consistent with the `heading-style` rule's uppercase requirement.
- Reference style validation (Vancouver) checks formatting/ordering conventions, not bibliographic accuracy (i.e., does not verify that cited works actually exist).
- Word/character counts use standard whitespace-delimited word counting.
