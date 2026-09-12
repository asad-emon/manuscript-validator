# Design decisions

Decisions that shape more than one module, and every deviation from
[`technical_specification.md`](../technical_specification.md). A decision recorded
here should not need re-litigating; if one turns out to be wrong, amend the entry
rather than deleting it, so the reasoning stays visible.

Status key: **Adopted** · **Superseded** · **Open**

---

## C1 — `copy.deepcopy(Document)` is banned

**Status:** Adopted (2026-09-11) · **Affects:** `autofix/`, `output/`
**Spec:** section 8 opens `apply_fixes` with `fixed_ast = deep_copy(ast)`.

`Document.__dict__` caches a `_Document__body` wrapping `self._element.body`.
`deepcopy` copies both `_part` and `_body`, producing two independent XML trees.
`.paragraphs` and `.runs` reach the caller through `_body` and mutate tree B,
while `.save()` serialises `part._element`, which is tree A. Mutations are lost
**with no error raised**:

```python
d = docx.Document(); d.add_paragraph("original")
c = copy.deepcopy(d)
c.paragraphs[0].runs[0].text = "MUTATED"
c.save(buf)
docx.Document(buf).paragraphs[0].text   # -> "original"
```

**Decision.** Clone only via `Document(BytesIO(original_bytes))`. The AST itself
is deep-copyable and always was -- it is a pure data snapshot -- so the spec's
intent survives; only the mechanism changes.

**Enforcement.** A test asserts `deepcopy` appears nowhere in `autofix/`.

---

## C2 — The corrected document is a patched clone, not a serialised AST

**Status:** Adopted (2026-09-11) · **Affects:** `models/`, `parser/binding.py`, `autofix/`, `output/`
**Spec:** section 9, "Write `fixed_ast` back to OOXML via `python-docx`".

The AST models roughly ten attributes per run. Regenerating a document from it
discards everything it does not model: images, `sectPr`, headers and footers,
numbering definitions, hyperlinks, fields, footnotes, endnotes, bookmarks,
content controls, pre-existing revisions, and equations. For a manuscript that
is not a tradeoff, it is data loss.

**Decision.** The AST is a **read-only projection**. Fixes are planned as data
(`FixPlan`, a list of `FixOp`) and replayed against freshly-opened clones of the
original bytes, located through `ElementIndex`.

Planning as data buys three things beyond fidelity: `corrected.docx` and the
redline replay the *same* plan, so they cannot drift apart; each `FixOp` is
testable against a synthetic one-paragraph document, satisfying section 13; and
reading the source to bytes once at pipeline entry, never passing the path
downstream, makes FR-9 structural rather than a convention.

**Consequence.** FR-11 is verified end-to-end -- save, reopen, re-parse,
re-validate -- not in memory, because an in-memory check cannot catch
serialisation loss.

---

## C3 — Formatting revisions use `w:rPrChange`, not `w:ins`

**Status:** Adopted (2026-09-11) · **Affects:** `output/tracked_changes.py`
**Spec:** section 9, "wrap modified runs in `<w:ins>` nodes".

That is right for text edits and wrong for everything else. Most fixes in the
section 6 rule set are format-only -- font, size, bold, italic, superscript --
and Word represents those as `<w:rPr><w:rPrChange>{old rPr}</w:rPrChange></w:rPr>`,
displayed as "Formatted: Font: 14 pt, Bold". Wrapping a format change in `w:ins`
tells the author their sentence was deleted and retyped, which is worse than
shipping no redline at all.

**Decision.** Three modes: `w:rPrChange` for run formatting, `w:del` + `w:ins`
for genuine text changes (literal uppercasing, caption renumbering),
`w:ins` for insertions. `w:moveFrom`/`w:moveTo` is out of scope; a caption move
is reported as a comment instead.

**Verified constraints** (against `wml.xsd`, ISO-IEC 29500-4:2016):
- Inside `w:del`, `w:t` must be renamed `w:delText`. Omitting this is the most
  common cause of "Word found unreadable content".
- `w:rPrChange` must be the **last** child of `w:rPr`. python-docx inserts
  property elements before the first known successor and appends otherwise, and
  `w:rPrChange` is in no successor list -- so attaching it before finishing the
  formatting mutations yields invalid XML. Mutate fully, attach last, assert.
- A nested `w:rPrChange` inside `CT_RPrOriginal` is illegal; snapshots must strip
  any pre-existing one.
- `w:author` is required; `w:date` must have no fractional seconds.
- Revision ids share one namespace across `w:ins`, `w:del`, `w:rPrChange`,
  `w:pPrChange`, `w:moveFrom`, `w:moveTo`, `w:tblPrChange`, `w:cellIns`, and
  `w:cellDel`. Manuscripts often arrive carrying co-author revisions, so ids
  must start above the maximum already present.

**Fallback if this overruns.** A `redline_mode: "tracked" | "highlighted"` switch,
where `highlighted` marks changed runs and comments the before/after values. It
loses Accept/Reject and the UI must say so plainly -- but it ships.

---

## C4 — A Qt-free `pipeline` facade sits between the UI and the stages

**Status:** Adopted (2026-09-11) · **Affects:** `pipeline.py`, `cli.py`, `ui/`
**Spec:** section 4 has `ui.main_window` depending on `parser`, `validator`, `autofix`, and `report`.

That places orchestration, error handling, and progress reporting inside a Qt
class: the code most worth testing, in the one place it cannot be tested without
a display, and unavailable to any second front end.

**Decision.** `pipeline.run(source, options, progress) -> PipelineResult`, with
`progress` a plain callable. The main window and the CLI are both shells over it.

This is what makes section 13's "no Qt in pipeline modules" achievable rather
than aspirational, and it is enforced by `test_no_qt_imports`.

---

## C5 — Resources load via `importlib.resources`

**Status:** Adopted (2026-09-11) · **Affects:** `rules/loader.py`

Rule configs and prompt templates are package data. `__file__`-relative paths
work in a source checkout and break under PyInstaller `--onedir`, where the
failure surfaces during packaging -- the point in the schedule where debugging
is most expensive. Using `importlib.resources` from the start costs nothing.

---

## Deviations from the section 6 rule set

| Spec | Deviation | Reason |
|---|---|---|
| `table-caption-position`, `figure-caption-position` marked `auto_fixable: yes` | **Flag only** in v1 | A caption move is a cross-paragraph structural edit that section 8 explicitly forbids, and the redline cannot represent it. Reported with a message naming where the caption belongs. **User decision, 2026-09-11** |
| `title-caps` marked `auto_fixable: yes` | **Flag only** in v1 | Automatic title-casing mangles acronyms and Latin binomials (COVID, mRNA, p53, *S. aureus*). Destroying an author's terminology is the kind of error that ends trust in the whole tool. **User decision, 2026-09-11** |
| Section 5.1 gives tables metadata only | Cell paragraphs emitted into the flat paragraph list, tagged `in_table`/`cell` | `table-text-size` (cell font 8) has nothing to check otherwise, and every run-level rule then works uniformly inside tables |
| `author-bold-superscript` bundles three checks | Split into `author-bold`, `author-size`, `author-affiliation-superscript` | One rule, one condition, one fix action. A bundled rule has no answer to "which fix?" when only one condition fails |
| Section 6's 25 rows | 40 config entries (Task 6, verified against the fixture factory's own inventory in both directions by `test_rules_coverage.py`) | The splits above, plus `table-cited-in-text` / `figure-cited-in-text` (the cross-reference half of `result-text-before-figure` is deterministic and free) and `*-numbering-sequence` (numbers must start at 1/I with no gaps -- a common real violation, ~15 lines) |
| FR-11 "zero deterministic violations" | Zero remaining **auto-fixable** deterministic violations | Flag-only rules such as the word limits survive autofix by design; the literal reading is unsatisfiable |
| Section 7.2 caches per document version | Cache per normalised section **text** | Formatting fixes do not change text, so FR-7's post-fix re-validation becomes a complete cache hit and costs no extra API calls. A version key would miss that entirely |
| Section 10 "PyQt or PySide" | **PySide6** | LGPL, so no commercial-licence question for a distributed `Setup.exe`; official binding; good PyInstaller support; runs offscreen on the Linux dev box |
| Section 6 `body-text-size` lists four sections | Extend to conclusion, conflict of interest, funding, acknowledgement | All body prose at the same size. The list lives in the rule's `applies_to_section`, so it is a one-line config change either way. **Note:** Task 6 shipped with the literal four-section list; this row's own decision wasn't actually applied to `journal_v1.json` until the Task 16 hardening pass caught the gap by re-reading this file against the shipped config -- confirmed it catches a real violation (`conclusion` section, wrong body size) on one of the five real manuscripts that the narrower scope missed entirely |
| — | **Body only in v1**; headers, footers, footnotes, endnotes, and textboxes unchecked | They are separate OOXML parts. Stated in the report rather than silently skipped -- discovering the omission via a reviewer's markup later is a credibility problem |

## Confirmed spec assumptions (section 14)

All three hold as written: heading detection by case-insensitive text match
(through the synonym table); Vancouver validation covers formatting and ordering
conventions, not whether cited works exist; word counts are whitespace-delimited.

## Resolved questions

- **Gemini model tier.** Resolved (Task 12): `gemini-2.5-flash` is the
  `llm_client.DEFAULT_MODEL` default -- fast and cheap enough for a
  single-boolean-plus-explanation structured verdict, not open-ended
  generation. Not exposed as a user setting in v1; revisit if a specific rule
  needs a stronger model.

## Open questions

- **Real-Word redline verification.** No Linux gate substitutes for opening
  the redline in Word; deferred to Task 15 (blocked on Windows access) and
  tracked as a risk until then. Task 10's XSD-schema validation and LibreOffice
  round-trip are the closest available substitutes and both pass, but neither
  proves Word specifically renders a formatting change as "Formatted: Font:
  14 pt, Bold" rather than something else.
- **PyInstaller Windows build, Inno Setup installer, real DPAPI round trip.**
  All of Task 15's code is written and tested against a fake `win32crypt`
  module (see Task 15 in the development checklist); the actual Windows build
  and packaging steps are blocked on Windows VM access.
