# Development Checklist — Manuscript Formatting Validator & Auto-Corrector

Source spec: [`technical_specification.md`](technical_specification.md)
Full rationale and design detail: `~/.claude/plans/create-a-development-plan-eager-scroll.md`

Status key: `[ ]` not started · `[~]` partial · `[x]` done

---

## ⚠️ Spec alignment

Four items in the spec were verified against the installed libraries and are wrong or unworkable as written. Every one is a correction adopted before implementation, not an open question. Record all of them in `docs/decisions.md` (Task 1).

| ID | Spec says | Reality | Adopted correction |
|---|---|---|---|
| **C1** | §8 `fixed_ast = deep_copy(ast)` | `copy.deepcopy(Document)` copies `_part` and `_body` as two independent XML trees; `.runs` mutates one, `.save()` serializes the other. Mutations vanish with **no error** | Banned. Clone only via `Document(BytesIO(original_bytes))`. Enforced by a test that greps `autofix/` for `deepcopy` |
| **C2** | §9 "write `fixed_ast` back to OOXML" | The AST models ~10 attributes per run; regenerating from it destroys images, `sectPr`, headers/footers, numbering, hyperlinks, fields, footnotes, equations | AST is a **read-only projection**. Fixes are planned as data (`FixPlan` = ordered `FixOp`s) and replayed against fresh clones of the original bytes |
| **C3** | §9 "wrap modified runs in `<w:ins>`" | Correct for text edits only. Most fixes here are format-only, and Word represents those as `w:rPrChange`. Implementing §9 literally makes every font fix read to the author as *delete the sentence, retype it* | Three modes: `w:rPrChange` (format), `w:del`+`w:ins` (text), `w:ins` (insertion) |
| **C4** | §4 UI depends on `parser`/`validator`/`autofix`/`report` directly | Puts orchestration and error handling inside a Qt class — the exact code that can't be tested on Linux or reused by the CLI | Qt-free `pipeline.run(source, options, progress) -> PipelineResult` façade between UI and stages |

**Three unaddressed risks that decide whether results are trustworthy** (not in the spec):

1. **Effective formatting resolution.** Verified: on a stock document `run.font.name`, `paragraph.style.font.name`, and `styles['Normal'].font.name` all return `None`; `docDefaults/rPrDefault/rPr/rFonts` carries `w:asciiTheme="minorHAnsi"`. §5.1's "read `run.font.name`" reports `found: None` for **every run** of any manuscript that sets fonts at style level — most real ones. Needs a full resolver: run `rPr` → character style → paragraph style + `w:basedOn` chain → `docDefaults` → `theme1.xml`.
2. **The `global-font` fix silently no-ops.** `run.font.name = "Times New Roman"` leaves `w:asciiTheme` in place, and per ECMA-376 §17.3.2.26 it **wins**. Word renders the theme font while re-validation passes — a false-green FR-11. The fix must pop `asciiTheme`/`hAnsiTheme`/`cstheme`/`eastAsiaTheme` before setting `ascii`/`hAnsi`/`cs`.
3. **`Paragraph.runs` and `.text` skip `w:ins` and `w:hyperlink`.** `CT_P.r_lst` is `./w:r` only. A manuscript arriving with co-author tracked changes — common — has whole sentences invisible to the validator. Index with `.//w:r[not(ancestor::w:rPr)]`; extract text via one canonical `paragraph_text()` helper used everywhere.

**Locked decisions:** Windows VM available for Phase 7 · real `.docx` samples to be supplied by the user · CLI first, GUI last · caption repositioning and title-case are **flag-only** in v1 · PySide6 over PyQt (LGPL).

---

## Phase 0 — Partial implementation tracking

Greenfield. The repo contains only `technical_specification.md` and this checklist; nothing is partially built. This section stays empty until work lands and a later task is left at `[~]`.

---

## Phase 1 — Foundation

Nothing downstream can be tested without these. Fixtures come before the parser because a parser cannot be unit-tested without documents.

### 1. `[x]` Scaffolding & toolchain *(M0, ~0.5 d)*
Repo tree, typed module stubs, installable package.
- `[x]` `src/` layout so tests import the *installed* package — catches a missing `__init__.py` or an uncollected `journal_v1.json` on day one rather than during the PyInstaller build
- `[x]` `pyproject.toml` with `[project.optional-dependencies]` splitting `gui` (PySide6), `windows` (pywin32), `dev` (pytest, pytest-mock, pytest-cov, ruff, mypy, pyinstaller) so Linux never installs pywin32
- `[x]` `constraints.txt` so the Windows build resolves to the versions Linux tested
- `[x]` `parser/` and `segmenter/` as regular packages with explicit `__init__.py` — not single modules as §11 implies, not namespace packages (PyInstaller's module graph has blind spots with those)
- `[x]` pytest markers `live`, `windows`, `gui`, `slow`; `addopts = -m "not live and not windows"` so the default run is offline and platform-clean
- `[x]` `docs/decisions.md` recording C1–C4 and every §6 deviation
- `[x]` Beyond scope, because each was small and self-contained: `errors.py` exception hierarchy · `logging_setup.py` with the §13 API-key redaction filter and its tests · `test_no_qt_imports.py` (Task 14's gate, in place before there is any Qt to leak) · `test_decision_guards.py` enforcing C1's `deepcopy` ban in `autofix/`
- **Done when:** `pip install -e ".[dev]"` succeeds · `pytest` passes a smoke test importing every package · `ruff check` and `mypy --strict src/` clean · `python -m manuscript_validator.cli --help` prints usage
- **Verified 2026-09-11:** 104 tests pass · ruff clean · mypy strict clean across 54 source files · `--help` and the `manuscript-validator` console script both work

### 2. `[ ]` Domain models + rule-config loader *(M1, ~1.5 d)*
`models/{ast,violation,audit,report,fix_plan,enums}.py`, `rules/{schema,loader}.py`. Every module signature references these types, so settling them first removes the largest source of rework.
- `[ ]` `@dataclass(slots=True)` for `Ast`/`Paragraph`/`Run`/`Table`/`Figure` — thousands per document, mutable, cheap; pydantic would re-validate on every assignment for internally-produced data
- `[ ]` **pydantic** for `Rule`/`Ruleset` (external human-authored JSON — the one place runtime validation earns its keep; discriminated union on `check_type`, free schema export) and `SemanticVerdict` (one definition serving as both `response_schema` and response validator)
- `[ ]` `@dataclass` `Violation` (mutated in place), `@dataclass(frozen=True)` `AuditEntry`, `ValidationReport` with hand-written `to_dict()` — it's a published file format, keep §5.4's shape under test control
- `[ ]` Enums as `class Section(str, Enum)` so `json.dumps` works with no encoder
- `[ ]` `Violation.status` = `open | fixed | fix_failed | needs_review | check_failed | conflict | suppressed` (§5.4 shows only `fixed`; §4.2 adds `check_failed`)
- `[ ]` Config loads via `importlib.resources`, never `__file__`-relative paths — PyInstaller-onedir safety, far cheaper now than at Task 14
- **Done when:** `to_dict()` output matches §5.4/§5.5 key-for-key against committed golden files · six deliberately-broken configs each raise `RuleConfigError` naming the rule_id and offending field

### 3. `[ ]` Fixture factory + real-document intake *(M2, ~1.5 d)*
`tests/fixtures/factory.py` — a `ManuscriptBuilder` emitting a compliant manuscript in memory, plus `violating(rule_id)` perturbing exactly one attribute of that baseline. The only way to honour §12's "violates exactly that rule and no other", and it keeps fixtures as readable code diffs rather than opaque binary zips.
- `[ ]` Compliant fixture: all 14 sections, ≥2 tables (Roman, caption above), ≥2 figures (Arabic, caption below), ≥8 references, superscript bracket citations, author superscript numerals
- `[ ]` `violating()` implemented for every rule ID in Task 6's inventory
- `[ ]` Meta-test asserting each violating fixture differs from baseline in exactly the intended attribute
- `[ ]` **User-supplied real manuscripts** in `tests/fixtures/real/` — ideally one clean submission, one messy, one with images, merged cells, equations. These catch the shared-blind-spot failure: python-docx output is unrealistically clean and never exercises style inheritance, theme fonts, `sectPr`, rsid-fragmented runs, or anchored images, so if the builder and parser misunderstand Word the same way, generated fixtures agree and pass while real files break
- `[ ]` `tools/make_fixtures.py` writes fixtures to disk for human inspection in Word
- `[ ]` Copy `wml.xsd` into `tests/schemas/` for the Task 9 validation gate

---

## Phase 2 — Document understanding

### 4. `[ ]` Parser: effective formatting, AST, ElementIndex *(M3, ~4 d)*
`parser/{effective,ast_builder,binding,captions,shapes,ids}.py`. The highest-risk, highest-leverage work in the project — see spec-alignment risks 1–3.
- `[ ]` `effective.py`: resolve run `rPr` → character style → paragraph style + `w:basedOn` chain (depth-capped, cycle-guarded) → `docDefaults` → theme fonts in `word/theme/theme1.xml`. Each AST field stores resolved value **plus its `source`**
- `[ ]` Canonical `paragraph_text(p_el)` used by parser, word counts, segmentation, caption regex, and Gemini payload — divergent text extraction across modules produces inconsistent results that are miserable to debug
- `[ ]` `iter_block_items()` over `body.iterchildren()` so paragraph/table order is true (`document.paragraphs` loses interleaving, which breaks caption-position logic)
- `[ ]` Table-cell paragraphs emitted into the flat `paragraphs` list tagged `in_table`/`cell` — §5.1 omits them, so `table-text-size` would have nothing to check
- `[ ]` Figures via `body.xpath('//w:drawing | //w:pict')` then `ancestor::w:p[1]` — `document.inline_shapes` misses anchored and VML images and has no paragraph back-reference
- `[ ]` `ElementIndex`: `p0042` → element, `p0042.r03` → run element via `.//w:p` and `.//w:r[not(ancestor::w:rPr)]`. IDs positional **at build time only**; the map then holds element objects, which survive reparenting. Because each clone is byte-identical at build time, IDs match 1:1 across read/fixed/redline/annotated clones
- `[ ]` `w:sz` is half-points (`w:val="18"` = 9pt); bold/italic tri-state (absent = inherit, `<w:b/>` = true, `<w:b w:val="0"/>` = false) — compare *effective* values, write *explicit* ones
- **Done when:** every §5.1 field populated on the compliant fixture and all real documents · resolution tests cover all four inheritance sources including theme fonts · parse→parse ID stability · input SHA-256 identical before and after parse (FR-9, asserted not assumed)

### 5. `[ ]` Segmenter *(M4, ~2 d)*
`segmenter/{headings,heuristics,section_index}.py`. The single largest source of *cascading* false positives — a title mislabelled as a heading fails `title-size`, `title-bold`, `title-case` **and** `heading-style` at once.
- `[ ]` Heading detection as a **score**, not a branch chain: style name / `outlineLvl` +3, all runs bold +2, literal uppercase +2, ≤8 words +1, no terminal period +1, vocabulary hit +3; ≥3 = heading
- `[ ]` Normalize NFKC → casefold → strip leading enumeration → strip trailing colon → collapse whitespace; match exact → token-set (makes "materials and methods" ≡ "methods and materials" for free) → fuzzy ≥0.85 for already-scored headings only
- `[ ]` Front-matter state machine for title/author/affiliation/corresponding-author — these have no headings; score signals, don't use fixed indices
- `[ ]` **Synonym tables and `section_order` live in the rule config JSON, not in code** — heading vocabulary is the most journal-specific thing in the system, and §2's "second journal = config addition" is false otherwise
- `[ ]` `on_missing_section: "skip" | "violation" | "check_failed"` added to the rule schema. Default `skip` for formatting rules, so a missing Methods section doesn't emit 40 identical violations. Closes a real spec gap: `select_nodes(ast, "title")` returning `[]` means **FR-11 passes on a manuscript with no title**
- `[ ]` Generated `section-present-*` rule family from a `required_sections` list (`acknowledgement` excluded — optional per §6)
- `[ ]` `front_matter_only` degradation when fewer than 4 canonical body headings are found: mark body rules `check_failed` with reason `"section boundaries undetected"`. Emitting 200 garbage violations is far worse than saying "I could not parse this"
- `[ ]` Per-paragraph `section_confidence` and `section_source` recorded
- **Done when:** all 14 labels assignable · tested against compliant, scrambled-order, and heading-variant fixtures plus all real documents

---

## Phase 3 — Validation

### 6. `[ ]` Rule config + deterministic engine + report shape *(M5, ~4 d)*
Full `journal_v1.json` (~38 entries from §6's 25 rows), `rules/{engine,deterministic,comparators,selectors}.py`, `models/report.py`.
- `[ ]` Envelope: `ruleset_id`, `ruleset_version`, `section_order`, `required_sections`, `optional_sections`, `section_synonyms`, `defaults`, `rules`
- `[ ]` Schema additions beyond §5.2 — **`selector`** (`node_type`, `scope`, optional `filter`), because `applies_to_section` alone can't express "the caption paragraph of each table"; **`prompt_file`**, because §7.2's 8-line prompt escaped into a JSON string is unreviewable and undiffable; plus `on_missing_section` and `priority`
- `[ ]` **Invariant: one rule = one condition = one fix action.** §6's `author-bold-superscript` bundles three conditions into one `fix_action` slot, so when only superscript fails there's no answer to "which fix?"
- `[ ]` Comparator registry: `==`, `!=`, `<=`, `>=`, `in`, `not_in`, `matches_regex`, `not_matches_regex`, `is_title_case`, `is_uppercase_literal`, `word_count_lte`, `is_non_empty`
- `[ ]` Rules added beyond §6: `table-cited-in-text` / `figure-cited-in-text` (§6 buries "and cites it" inside a semantic rule, but `referenced_in_paragraph_ids` being non-empty is exactly deterministic and free — saves LLM calls) and `table-/figure-numbering-sequence` (must start at 1/I, no gaps; a very common real violation, ~15 lines)
- `[ ]` Run-level violations aggregate to **one per paragraph per rule** with `run_indices` in `details` — Word splits runs at rsid boundaries, so a 5-run title must not emit 5 identical violations
- `[ ]` Semantic rules route to a stub returning `check_failed`, proving the §7 router works with zero network dependency
- `[ ]` `test_rules_coverage.py`: every rule ID in `journal_v1.json` has a `violating()` builder and a test — prevents rules being added to config without tests, the most likely long-term decay path
- **Done when:** **one test per rule** feeds `violating(rule_id)` and asserts exactly one violation with the matching ID (the strongest test in the suite, and the reason Task 3 came first) · compliant fixture yields zero deterministic violations · report JSON validates against a committed JSON Schema

### 7. `[ ]` Rule-implementation traps *(folded into Tasks 4 and 6)*
Tracked separately because each is a silent-wrongness bug, not a missing feature.
- `[ ]` `uppercase_literal` = `bool(re.search(r'[A-Za-z]', t)) and t == t.upper()`; record `w:caps` separately as `all_caps_property`. Text that *looks* uppercase via the style transform but isn't typed that way is exactly what the journal rule targets. The fix uppercases text **and** clears `w:caps`, or the document looks right and fails the literal check forever — and it's a text edit, so `del`/`ins` in the redline
- `[ ]` Citation superscripting straddles runs (`"[1"` + `"]"`): detect over paragraph text with a run-offset map, then split runs; set `xml:space="preserve"` on segments with edge whitespace
- `[ ]` **Citation idempotency guard** — the check is "every citation span is superscript **and** its boundaries coincide with run boundaries". Without the second clause the fix re-splits every pass and FR-11 never converges
- `[ ]` Scope citations to body sections, digits-only inside brackets — otherwise `[Figure 1]`, math intervals `[0,1]`, and dose ranges get mangled
- `[ ]` SEQ-field captions: Word keeps the number in `w:instrText` (` SEQ Table \* ROMAN `) with a cached `w:t`. Read the style from the field switch; if a field produced it, mark not auto-fixable — patching cached text is futile, Word re-renders and reverts
- `[ ]` Caption inside the table (merged first row) → report `position: "inside"`, not auto-fixable
- `[ ]` Word counting: `w:tab`/`w:br`/`w:noBreakHyphen` produce no `w:t`, so `"A<tab>B"` counts as one word; normalize in `paragraph_text()`, plus NBSP → space. Abstract limit excludes the keywords line by default via `exclude_patterns`
- `[ ]` Declare scope: **body only in v1**. State in the report that headers, footers, footnotes, endnotes, and textboxes were not checked rather than silently skipping them

---

## Phase 4 — Correction & output

### 8. `[ ]` Fix planner + audit log + conflict detector *(M6, ~3 d)*
`autofix/{engine,actions}.py`. `plan_fixes(ast, violations, ruleset) -> (FixPlan, audit_log)` where `FixPlan` is **pure data replayed twice** (corrected + redline) — this guarantees the two outputs can never diverge, a classic bug in this class of tool, and delivers §13's independently-testable fix actions.
- `[ ]` `fix_action` registry: the nine from §8 plus `strip_trailing_colon`, `set_citation_brackets`. `set_caption_position` and `set_title_case` registered but **disabled in v1**
- `[ ]` **Conflict detector** (not in the spec, required for FR-11): `global-font`, `abstract-size`, `heading-style`, and `body-text-size` all write the same runs. If segmentation mislabels the title as a heading, `title-size` writes 14pt and `heading-style` writes 9pt to the same `w:sz`; last-writer wins, re-validation reports the loser, FR-11 fails and the audit log lies. Group `FixOp`s by `(element_id, attribute)`; on differing targets apply none, mark all `conflict`, report
- `[ ]` `priority` int per rule for reproducible apply order
- `[ ]` `global-font` fix pops `asciiTheme`/`hAnsiTheme`/`cstheme`/`eastAsiaTheme` before setting `ascii`/`hAnsi`/`cs` (spec-alignment risk 2)
- `[ ]` Run splitting registers children as `p0042.r03/a`,`/b`,`/c` and records `split_from` in the audit entry
- **Done when:** each fix action has its own unit test on a synthetic node · audit entries match §5.5 · input AST provably unmutated

### 9. `[ ]` Output writer + round-trip *(M7, ~2.5 d)*
`output/{writer,naming}.py` — replays `FixPlan` against a fresh `Document(BytesIO(original_bytes))` via `ElementIndex`.
- `[ ]` Pipeline shape: read source to `bytes` **once** at entry, never pass the path downstream — makes FR-9 structural rather than a convention; assert `Path(src).read_bytes() == original_bytes` at the end of the run
- `[ ]` Output naming `<stem>.corrected.docx` etc., written to a user-chosen folder — never silently beside the original, which risks confusing the author about which file is the submission
- **Done when (the strongest gate in the project):** the written file re-parses, re-segments, and re-validates to zero auto-fixable deterministic violations — FR-11 **end-to-end**, since in-memory re-validation misses serialization loss · reopens without corruption · original hash unchanged · a test asserts images, tables, and section count survive the patch, guarding against regression toward C2's failure mode

### 10. `[ ]` Tracked-changes generator *(M8, ~2.5 d)*
`output/tracked_changes.py` — `RevisionWriter` implementing C3's three modes, `w:author="Manuscript Validator"`, `w:date` as `%Y-%m-%dT%H:%M:%SZ` (no microseconds; Word rejects some fractional forms).
- `[ ]` Inside `w:del`, rename `<w:t>` to `<w:delText>` — the #1 cause of "Word found unreadable content"
- `[ ]` `w:rPrChange` must be the **last** child of `w:rPr`. python-docx's `ZeroOrOne(successors=...)` will happily append `w:sz` *after* it if you attach the change first, producing invalid XML — so mutate `rPr` fully, then attach, then assert `rPr[-1].tag == qn('w:rPrChange')`
- `[ ]` Revision IDs share one namespace — scan the input for existing `w:ins|w:del|w:rPrChange|w:pPrChange|w:moveFrom|w:moveTo|w:tblPrChange|w:cellIns|w:cellDel` ids and start above the max (manuscripts often arrive with co-author revisions)
- `[ ]` Skip `w:moveFrom`/`w:moveTo` entirely
- `[ ]` **Never re-validate the redline** — `Paragraph.runs` skips `w:ins`, so it would report phantom violations for every inserted run
- `[ ]` *Fallback if this overruns:* `output.redline_mode: "tracked" | "highlighted"` config switch, where `highlighted` gives `w:highlight` + a comment stating `before → after`. Loses Accept/Reject and must be said plainly in the UI — but ships
- **Done when:** every audit entry appears as a revision · XSD-validates against `tests/schemas/wml.xsd` · `soffice --headless --convert-to docx` round-trips · XML tests assert `rPrChange` for format ops and `ins`/`del` for text ops. **Real-Word verification deferred to Task 14 and tracked as an open risk until then**

### 11. `[ ]` Report generator *(M9, ~2 d)*
`report/{generator,annotate_docx.py}`.
- `[ ]` Use **native** `Document.add_comment(runs, text, author, initials)` — python-docx 1.2.0 auto-wires `word/comments.xml`, the content-type override, the relationship, and the `commentRangeStart`/`End`/`commentReference` markers, and correctly continues ID allocation on reopened files. §11 implies work that no longer needs doing
- `[ ]` `anchor_runs()` resolver — `paragraph.runs` can be empty (empty paragraphs, or content inside `w:hyperlink`/`w:ins`), so fall back to a zero-width run rather than raising `IndexError`
- `[ ]` Optional `anchor_paragraph_id` on `Violation`, distinct from `paragraph_id`, so document-level violations (`doc-order`, `section-missing:*`) can be anchored without the report JSON lying
- `[ ]` Annotate a clone of the **original**, so the author sees comments against what they submitted — never on `corrected.docx` or the redline

---

## Phase 5 — Semantic layer

### 12. `[ ]` Semantic validator (Gemini) *(M10, ~3 d)*
`rules/{semantic,llm_client,cache}.py` + `rules/prompts/*.txt`. `semantic.py` stays rule-agnostic and SDK-free; `llm_client.py` is the only file importing `google.genai`, behind a `SemanticClient` Protocol.
- `[ ]` Call shape: `Client(api_key, http_options=HttpOptions(timeout=30_000, retry_options=HttpRetryOptions(attempts=3, …)))` then `generate_content(config=GenerateContentConfig(response_mime_type="application/json", response_schema=SemanticVerdict, temperature=0.0, seed=42, thinking_config=ThinkingConfig(thinking_budget=0)))`
- `[ ]` Never rely on `resp.parsed` alone — fall back to `SemanticVerdict.model_validate_json(resp.text)`, then `check_failed(bad_response)`
- `[ ]` **Cache on normalized section text, not document version** (§7.2 says version): `sha256(ruleset_version | rule_id | prompt_template | model_id | temperature | normalized_section_text)`. Formatting fixes don't change plain text, so FR-7's post-fix re-validation is a 100% cache hit — zero incremental calls per document. Including prompt and model invalidates automatically on a rule edit or model upgrade
- `[ ]` `ThreadPoolExecutor(max_workers=4)` — pure stdlib, no Qt. Seven rules at ~3 s serial is 20 s of dead UI
- `[ ]` Every failure classified: `api_key_missing`, `api_key_invalid`, `quota_exceeded`, `service_error`, `offline`, `timeout`, `bad_response`, `unknown` — each surfaced in the report per §4.2/§13, each covered by a fault-injection test
- `[ ]` "Test connection" uses `client.models.list()` — a real auth check with zero token spend
- `[ ]` Redaction filter stripping `AIza[0-9A-Za-z_\-]{35}`; test asserts the key appears in neither report JSON nor audit log
- `[ ]` Test layers: `FakeSemanticClient` (default) · recorded payloads in `tests/data/gemini/` including truncated JSON, markdown-fenced JSON, prose around the object, schema-valid-but-wrong-types — where most real-world LLM bugs live · prompt-contract tests (no unsubstituted `{placeholder}`) · `@pytest.mark.live`, deselected by default
- **Done when:** `check()` never raises, under any injected fault

---

## Phase 6 — Delivery surfaces

### 13. `[ ]` Pipeline façade + headless CLI *(M11, ~1.5 d)*
`pipeline.py`, `cli.py`. This is what delivers usable value on the Linux box weeks before a window exists, and it becomes the acceptance-test harness.
- `[ ]` C4's `pipeline.run(source, options, progress: Callable[[str, float], None]) -> PipelineResult`
- `[ ]` `validate paper.docx -o out/` emits `<stem>.{corrected,tracked,annotated}.docx` + `.report.json` + `.audit.json`; exit code reflects severity
- `[ ]` `--no-semantic` runs fully offline per §13
- **Done when:** end-to-end acceptance test passes over all real manuscripts

### 14. `[ ]` PySide6 UI *(M12, ~4 d)*
`ui/{main_window,settings_window,report_view,workers}.py`, `app.py`. Developed with `QT_QPA_PLATFORM=offscreen`.
- `[ ]` Pipeline in a `QRunnable` on a `QThreadPool`; C4's `progress` callable marshals via signals
- `[ ]` Settings screen talks to the settings-store **protocol**, so it works against the dev backend on Linux and DPAPI on Windows with no code change
- `[ ]` First launch with no key opens Settings modally before file operations are enabled (§4.1)
- `[ ]` **Section-override panel** — detected sections with a per-block dropdown. ~60 lines of Qt that eliminates segmentation's worst failure mode; store overrides in the report so re-runs are reproducible
- `[ ]` `test_no_qt_imports.py` mechanically asserts no pipeline module transitively imports PySide6. §13's Qt-freedom mandate is the single constraint making Linux development viable — enforce it, don't hope for it

---

## Phase 7 — Windows packaging & release

### 15. `[ ]` Windows-only: DPAPI, PyInstaller, Inno Setup *(M13, ~3 d — requires the Windows VM)*
Three files, because the `SecretBox` seam keeps DPAPI to ~60 lines.
- `[ ]` `config/settings_store.py`: `SecretBox` Protocol + platform factory. **Lazy `import win32crypt` inside the method**, never at module top level — that's the whole trick that keeps the module importable and testable on Linux
- `[ ]` `DpapiSecretBox` with app-specific entropy and `flags=0` (per-user; never `CRYPTPROTECT_LOCAL_MACHINE`); `FernetSecretBox` for dev, env-guarded; `NullSecretBox` for tests, refusing to construct when frozen
- `[ ]` Scheme-tagged config file (`{"scheme": "dpapi", "ciphertext": "…"}`) so a config written on the dev box is *detected and rejected* on Windows rather than producing a garbage decrypt surfacing as a mysterious "key rejected" from Gemini
- `[ ]` Atomic write via `os.replace()`; `get_api_key()` returns `None` and **never raises** for missing file, absent key, decrypt failure, scheme mismatch, or JSON parse error
- `[ ]` Linux-runnable DPAPI test injecting a fake `sys.modules["win32crypt"]` and asserting call shape — catches the most likely bugs without Windows
- `[ ]` `pyinstaller --name ManuscriptValidator --windowed --onedir main.py` with `--hidden-import win32crypt --hidden-import win32timezone`; `journal_v1.json` and `prompts/*.txt` must load (the `datas` entry is the usual failure)
- `[ ]` Inno Setup `Setup.exe`: Program Files install, Start Menu shortcut, uninstall entry
- `[ ]` `dist/` runs on a clean VM with no Python
- `[ ]` **Open `<stem>.tracked.docx` in real Word** and confirm formatting changes show as "Formatted: Font: 14 pt, Bold" rather than as retyped text — the deferred Task 10 check, and the one gate no Linux tooling can substitute for

### 16. `[ ]` Hardening & release *(M14, ~2 d)*
- `[ ]` 60-page manuscript under 5 s for the deterministic pass
- `[ ]` Key-redaction audit across logs, reports, audit entries
- `[ ]` README + user guide; `ruleset_version` bump procedure
- `[ ]` `docs/decisions.md` finalized with every deviation from §6 and §9

---

## Progress Summary

| Phase | Tasks | Done | Partial | Remaining |
|---|---|---|---|---|
| 0 — Partial implementation tracking | 0 | 0 | 0 | 0 |
| 1 — Foundation | 3 | 1 | 0 | 2 |
| 2 — Document understanding | 2 | 0 | 0 | 2 |
| 3 — Validation | 2 | 0 | 0 | 2 |
| 4 — Correction & output | 4 | 0 | 0 | 4 |
| 5 — Semantic layer | 1 | 0 | 0 | 1 |
| 6 — Delivery surfaces | 2 | 0 | 0 | 2 |
| 7 — Windows packaging & release | 2 | 0 | 0 | 2 |
| **Total** | **16** | **1** | **0** | **15** |

Estimate ≈37 dev-days. Only Task 15 requires the Windows machine.

---

## Verification

Every task:
```bash
pytest -q && ruff check src/ tests/ && mypy --strict src/
```

End-to-end, once Task 13 lands:
```bash
python -m manuscript_validator.cli validate tests/fixtures/real/sample1.docx -o /tmp/out --no-semantic
```
Confirm: `corrected.docx` reopens and re-validates to zero auto-fixable deterministic violations (FR-11) · original SHA-256 unchanged (FR-9) · `report.json` matches §5.4 with consistent `summary` arithmetic · `audit.json` has one entry per applied fix with before/after values (FR-10) · `annotated.docx` opens with comments on the right runs.

Structural gates available on the Linux dev box:
```bash
python -c "import zipfile,lxml.etree as E; s=E.XMLSchema(E.parse('tests/schemas/wml.xsd')); assert s.validate(E.fromstring(zipfile.ZipFile('/tmp/out/sample1.tracked.docx').read('word/document.xml')))"
```
```bash
soffice --headless --convert-to docx --outdir /tmp/lo /tmp/out/sample1.tracked.docx
```

Semantic layer (key configured) and GUI (offscreen):
```bash
pytest -m live -q
```
```bash
QT_QPA_PLATFORM=offscreen pytest -m gui -q
```

---

## Notes

- 2026-09-11 — Checklist created from `technical_specification.md` and the approved development plan. 16 tasks across 7 phases, none started. Four spec corrections adopted before implementation (C1–C4 in the Spec alignment block) plus three unaddressed risks documented. User decisions locked: Windows VM available for Phase 7, real `.docx` samples to be supplied for Task 3, CLI before GUI, caption repositioning and title-case flag-only in v1, PySide6 over PyQt.
- 2026-09-11 — Task 1 complete. Package scaffold, `pyproject.toml` with the gui/windows/dev dependency split, typed stubs for every pipeline module carrying the design constraints in their docstrings, and `docs/decisions.md` with C1–C5 plus the §6 deviation table. Also landed `errors.py`, `logging_setup.py` with the §13 key-redaction filter, and three guard tests (module imports, Qt-freedom, C1 `deepcopy` ban). 104 tests pass; ruff and mypy --strict clean. Added C5 (resources load via `importlib.resources`) during the work — not a spec deviation, but a cross-module constraint worth recording before Task 2 writes the loader.

_Last updated: 2026-09-11_
