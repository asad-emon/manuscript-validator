"""Tracked-changes redline generator (docs/decisions.md C3).

Replays the *same* `FixPlan` Task 8/9 apply directly to `corrected.docx`, but
wraps each edit as a Word revision instead of writing it in place -- three
modes, matched to what each `FixAction` actually changes:

- **`w:rPrChange`** for a pure formatting edit (`set_font`, `set_font_size`,
  `set_bold`, `set_italic`, `set_superscript`): the run keeps its identity,
  Word shows "Formatted: Font: 14 pt, Bold". Spec section 9 says wrap every
  edit in `w:ins`; that is right for text and wrong for formatting -- it
  would tell the author their sentence was deleted and retyped.
- **`w:del` + `w:ins`** for a genuine text edit (`set_uppercase_literal`,
  `strip_trailing_colon`, `set_citation_brackets`, `set_numbering_style`): a
  clone of the run, textually unchanged, is marked deleted (`w:t` renamed to
  `w:delText`); the original run, now edited, is marked inserted.
- **`w:ins`** alone for a pure insertion (`insert_line_break`): nothing existed
  before, so there is nothing to mark deleted.

`w:moveFrom`/`w:moveTo` is out of scope (docs/decisions.md C3) -- a caption
reposition is not auto-fixable in v1 at all (locked decision), so no
`FixOp` ever asks for one.

Never re-validate a redline: it exists to show the *proposed* edits inside
the manuscript the author submitted, not to be fed back into the pipeline. A
`w:del`-wrapped run's `w:t` has already been renamed `w:delText`, so
`Run.text` (python-docx) reads it as empty -- reasonably safe by accident --
but that is not something to depend on. Re-validate `corrected.docx` instead
(Task 9), which is what FR-11 actually asks for.
"""

from __future__ import annotations

import copy
from collections.abc import Callable
from typing import Any

from docx.document import Document as DocumentObject
from docx.oxml import OxmlElement
from docx.oxml.ns import qn

from manuscript_validator.autofix import actions
from manuscript_validator.autofix.engine import resolve_target
from manuscript_validator.errors import DocumentError, FixApplicationError
from manuscript_validator.models.audit import AuditEntry
from manuscript_validator.models.enums import FixAction
from manuscript_validator.models.fix_plan import FixOp, FixPlan
from manuscript_validator.parser.binding import ElementIndex

#: Word's own author label for every revision this application makes.
REVISION_AUTHOR = "Manuscript Validator"

#: Every element type that carries a revision id, sharing one namespace --
#: a manuscript arriving with co-author tracked changes already has some of
#: these, and new ids must start above whatever is already there.
_REVISION_ID_XPATH = (
    ".//w:ins/@w:id | .//w:del/@w:id | .//w:rPrChange/@w:id | .//w:pPrChange/@w:id | "
    ".//w:moveFrom/@w:id | .//w:moveTo/@w:id | .//w:tblPrChange/@w:id | "
    ".//w:cellIns/@w:id | .//w:cellDel/@w:id"
)

_ACTIONS: dict[FixAction, Callable[[Any, dict[str, Any]], actions.ActionResult]] = {
    **actions.RUN_ACTIONS,
    **actions.PARAGRAPH_ACTIONS,
}

_RPRCHANGE_ACTIONS = frozenset(
    {
        FixAction.SET_FONT,
        FixAction.SET_FONT_SIZE,
        FixAction.SET_BOLD,
        FixAction.SET_ITALIC,
        FixAction.SET_SUPERSCRIPT,
    }
)
_TEXT_EDIT_ACTIONS = frozenset(
    {
        FixAction.SET_UPPERCASE_LITERAL,
        FixAction.STRIP_TRAILING_COLON,
        FixAction.SET_CITATION_BRACKETS,
        FixAction.SET_NUMBERING_STYLE,
    }
)
_INSERTION_ACTIONS = frozenset({FixAction.INSERT_LINE_BREAK})

#: For a text edit whose `FixOp.target_id` names a *paragraph*, the run that
#: actually changes is found the same way the direct-write action itself
#: finds it (Task 8) -- one locator per paragraph-scoped text action.
_PARAGRAPH_SCOPED_TEXT_EDIT_LOCATORS: dict[FixAction, Callable[[Any], Any | None]] = {
    FixAction.STRIP_TRAILING_COLON: actions.last_visible_run,
    FixAction.SET_NUMBERING_STYLE: actions.find_caption_run,
}


class RevisionIdAllocator:
    def __init__(self, document: DocumentObject) -> None:
        existing = document.element.body.xpath(_REVISION_ID_XPATH)
        self._next = max((int(value) for value in existing), default=0) + 1

    def next_id(self) -> int:
        value = self._next
        self._next += 1
        return value


def _strip_nested_rpr_change(rpr_snapshot: Any) -> None:
    """A `w:rPrChange` nested inside another `w:rPrChange`'s `w:rPr` snapshot
    is illegal -- if this run already carries a co-author's formatting
    revision, its snapshot must not carry a copy of that revision too."""
    nested = rpr_snapshot.find(qn("w:rPrChange"))
    if nested is not None:
        rpr_snapshot.remove(nested)


def _attach_rpr_change(
    run_el: Any, original_rpr: Any, author: str, date: str, revision_id: int
) -> None:
    """`w:rPrChange` must be the **last** child of `w:rPr` -- python-docx's
    `ZeroOrOne(successors=...)` inserts known properties before their
    declared successor and appends anything else, and `w:rPrChange` has no
    successor entry, so attaching it before the run's other properties are
    finished mutating lets a later property append itself *after* the
    change marker, producing invalid XML. Mutate fully first, attach last,
    then assert the ordering held.
    """
    rpr_el = run_el.get_or_add_rPr()
    rpr_change = OxmlElement("w:rPrChange")
    rpr_change.set(qn("w:id"), str(revision_id))
    rpr_change.set(qn("w:author"), author)
    rpr_change.set(qn("w:date"), date)
    rpr_change.append(original_rpr)
    rpr_el.append(rpr_change)
    assert rpr_el[-1].tag == qn("w:rPrChange")


def _convert_to_del_text(run_el: Any) -> None:
    """Inside `w:del`, `w:t` must be renamed `w:delText` -- the single most
    common cause of "Word found unreadable content" when this is skipped."""
    for t_el in run_el.findall(qn("w:t")):
        t_el.tag = qn("w:delText")


def _wrap_run(run_el: Any, tag: str, author: str, date: str, revision_id: int) -> Any:
    parent = run_el.getparent()
    index = list(parent).index(run_el)
    wrapper = OxmlElement(tag)
    wrapper.set(qn("w:id"), str(revision_id))
    wrapper.set(qn("w:author"), author)
    wrapper.set(qn("w:date"), date)
    parent.insert(index, wrapper)
    wrapper.append(run_el)
    return wrapper


def _apply_as_rpr_change(
    run_el: Any,
    action: FixAction,
    params: dict[str, Any],
    author: str,
    date: str,
    ids: RevisionIdAllocator,
) -> actions.ActionResult:
    """`w:rPrChange` is a `ZeroOrOne` child of `w:rPr` -- at most one is ever
    legal. When two format-only fixes land on the *same* run in the same
    replay (`global-font` sets the font, `author-bold` sets bold on that
    same author-line run), the second call must not simply append a second
    `w:rPrChange` next to the first; it reuses the first one's original
    snapshot (the true pre-any-fix state) and replaces it, so the run ends
    up with exactly one change recording every accumulated edit.
    """
    rpr_el = run_el.get_or_add_rPr()
    existing_change = rpr_el.find(qn("w:rPrChange"))
    if existing_change is not None:
        original_rpr = copy.deepcopy(existing_change.find(qn("w:rPr")))
        rpr_el.remove(existing_change)
    else:
        original_rpr = copy.deepcopy(rpr_el)
        _strip_nested_rpr_change(original_rpr)
    before, after = _ACTIONS[action](run_el, params)
    _attach_rpr_change(run_el, original_rpr, author, date, ids.next_id())
    return before, after


def _apply_as_text_edit(
    element: Any,
    action: FixAction,
    params: dict[str, Any],
    author: str,
    date: str,
    ids: RevisionIdAllocator,
) -> actions.ActionResult:
    locator = _PARAGRAPH_SCOPED_TEXT_EDIT_LOCATORS.get(action)
    target_run = locator(element) if locator is not None else element
    if target_run is None:
        raise FixApplicationError(f"{action.value}: no target run found for tracked change")

    old_run_clone = copy.deepcopy(target_run)
    _convert_to_del_text(old_run_clone)
    target_run.addprevious(old_run_clone)
    _wrap_run(old_run_clone, "w:del", author, date, ids.next_id())

    # Always call the handler with `element` (the id `FixOp.target_id` names),
    # not `target_run`: a paragraph-scoped action (`strip_trailing_colon`,
    # `set_numbering_style`) expects the *paragraph* and re-locates the run
    # itself -- which still finds `target_run` correctly, since the del clone
    # just inserted has no visible text (`w:delText`, not `w:t`) and is
    # skipped by the same locator. A run-scoped action has `element is
    # target_run`, so this is identical to calling it directly.
    before, after = _ACTIONS[action](element, params)

    _wrap_run(target_run, "w:ins", author, date, ids.next_id())
    return before, after


def _apply_as_insertion(
    element: Any,
    action: FixAction,
    params: dict[str, Any],
    author: str,
    date: str,
    ids: RevisionIdAllocator,
) -> actions.ActionResult:
    before, after = _ACTIONS[action](element, params)
    new_run = element[-1]  # insert_line_break appends exactly one run, last
    _wrap_run(new_run, "w:ins", author, date, ids.next_id())
    return before, after


def _apply_as_revision(
    op: FixOp, element: Any, author: str, date: str, ids: RevisionIdAllocator
) -> actions.ActionResult:
    if op.action in _RPRCHANGE_ACTIONS:
        return _apply_as_rpr_change(element, op.action, op.params, author, date, ids)
    if op.action in _TEXT_EDIT_ACTIONS:
        return _apply_as_text_edit(element, op.action, op.params, author, date, ids)
    if op.action in _INSERTION_ACTIONS:
        return _apply_as_insertion(element, op.action, op.params, author, date, ids)
    raise FixApplicationError(f"no tracked-changes handler for {op.action.value!r}")


def apply_fix_plan_as_revisions(
    document: DocumentObject,
    element_index: ElementIndex,
    fix_plan: FixPlan,
    date: str,
    author: str = REVISION_AUTHOR,
) -> list[AuditEntry]:
    """Replay `fix_plan` against `document` (via `element_index`, built over
    the same document) as Word revisions rather than direct writes.

    Returns one `AuditEntry` per successfully applied op, exactly like
    `autofix.engine.apply_fix_plan` -- the two functions replay the identical
    plan, so `corrected.docx` and the redline can never disagree about what
    changed. Does not touch `Violation.status`: that bookkeeping happens once,
    against the direct-write pass (Task 9); the redline is a second rendering
    of already-recorded fixes, not a second source of truth for whether they
    succeeded.
    """
    ids = RevisionIdAllocator(document)
    audit_log: list[AuditEntry] = []
    for op in fix_plan.ordered():
        try:
            element = resolve_target(element_index, op)
            before, after = _apply_as_revision(op, element, author, date, ids)
        except (FixApplicationError, DocumentError, KeyError):
            continue
        audit_log.append(
            AuditEntry(
                rule_id=op.rule_id,
                paragraph_id=op.paragraph_id,
                action=op.action,
                before=before,
                after=after,
                timestamp=date,
                run_indices=(op.run_index,) if op.run_index is not None else (),
            )
        )
    return audit_log


__all__ = ["REVISION_AUTHOR", "RevisionIdAllocator", "apply_fix_plan_as_revisions"]
