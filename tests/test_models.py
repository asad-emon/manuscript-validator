"""Task 2: the models serialise exactly as the spec says, and deep-copy cleanly."""

from __future__ import annotations

import copy
import json
from pathlib import Path

from manuscript_validator.models import (
    Ast,
    AuditEntry,
    FixAction,
    FixOp,
    Paragraph,
    Run,
    Section,
    Severity,
    ValidationReport,
    Violation,
    ViolationStatus,
)

GOLDEN = Path(__file__).parent / "data" / "golden"


def _golden(name: str) -> dict[str, object]:
    return json.loads((GOLDEN / name).read_text(encoding="utf-8"))


class TestSpecShapes:
    """Serialised output must match the spec's own examples key for key.

    Golden files are transcribed from the spec rather than generated from these
    models: a golden file produced by the code under test would prove only that
    the code agrees with itself.
    """

    def test_violation_matches_spec_5_4(self) -> None:
        violation = Violation(
            rule_id="title-font-size",
            severity=Severity.HIGH,
            section=Section.TITLE,
            paragraph_id="p0001",
            expected="font_size_pt == 14",
            found="font_size_pt == 12",
            auto_fixable=True,
            status=ViolationStatus.FIXED,
        )
        assert violation.to_dict() == _golden("violation.json")

    def test_violation_key_order_matches_spec(self) -> None:
        violation = Violation(rule_id="r", severity=Severity.LOW)
        assert list(violation.to_dict()) == list(_golden("violation.json"))

    def test_audit_entry_matches_spec_5_5(self) -> None:
        entry = AuditEntry(
            rule_id="title-font-size",
            paragraph_id="p0001",
            action=FixAction.SET_FONT_SIZE,
            before={"font_size_pt": 12},
            after={"font_size_pt": 14},
            timestamp="2026-09-03T10:00:02Z",
        )
        assert entry.to_dict() == _golden("audit_entry.json")

    def test_report_matches_spec_5_4(self) -> None:
        report = ValidationReport(
            document_id="uuid",
            ruleset_version="1.0.0",
            validated_at="2026-09-03T10:00:00Z",
        )
        def _violations(prefix: str, status: ViolationStatus, count: int) -> list[Violation]:
            return [
                Violation(rule_id=f"{prefix}-{i}", severity=Severity.LOW, status=status)
                for i in range(count)
            ]

        report.violations = _violations("fixed", ViolationStatus.FIXED, 9) + _violations(
            "open", ViolationStatus.OPEN, 5
        )
        serialised = report.to_dict()
        assert serialised["summary"] == _golden("report.json")["summary"]
        assert list(serialised) == list(_golden("report.json"))

    def test_extension_keys_are_absent_when_empty(self) -> None:
        """Our additions must not leak into a plain violation's JSON."""
        keys = Violation(rule_id="r", severity=Severity.LOW).to_dict()
        for extension in ("run_indices", "explanation", "details", "message"):
            assert extension not in keys

    def test_extension_keys_appear_when_set(self) -> None:
        violation = Violation(
            rule_id="r", severity=Severity.LOW, run_indices=[0, 3], failure_reason="offline"
        )
        data = violation.to_dict()
        assert data["run_indices"] == [0, 3]
        assert data["failure_reason"] == "offline"

    def test_report_json_round_trips(self) -> None:
        report = ValidationReport(document_id="d", ruleset_version="1.0.0")
        assert json.loads(json.dumps(report.to_dict())) == report.to_dict()


class TestSummaryArithmetic:
    def test_check_failed_is_neither_fixed_nor_needing_review(self) -> None:
        """A check that could not run is its own outcome.

        Collapsing it into `needs_review` would overstate what the validator
        actually found; collapsing it into `auto_fixed` would be a lie.
        """
        report = ValidationReport(document_id="d", ruleset_version="1.0.0")
        report.violations = [
            Violation(rule_id="a", severity=Severity.LOW, status=ViolationStatus.FIXED),
            Violation(rule_id="b", severity=Severity.LOW, status=ViolationStatus.CHECK_FAILED),
            Violation(rule_id="c", severity=Severity.LOW, status=ViolationStatus.OPEN),
        ]
        summary = report.summary()
        assert summary == {"total": 3, "auto_fixed": 1, "needs_review": 1, "check_failed": 1}

    def test_conflict_counts_as_needing_review(self) -> None:
        report = ValidationReport(document_id="d", ruleset_version="1.0.0")
        report.violations = [
            Violation(rule_id="a", severity=Severity.LOW, status=ViolationStatus.CONFLICT)
        ]
        assert report.summary()["needs_review"] == 1


class TestAstDeepCopy:
    """Spec section 8 opens by deep-copying the AST; that must actually work.

    It works precisely because the AST holds no live XML -- the same operation
    on a python-docx Document silently discards mutations (docs/decisions.md C1).
    """

    def _ast(self) -> Ast:
        return Ast(
            paragraphs=[
                Paragraph(
                    id="p0001",
                    text="INTRODUCTION",
                    runs=[Run(text="INTRODUCTION", font_size_pt=9.0, bold=True)],
                )
            ],
            document_id="abc",
        )

    def test_deep_copy_is_independent(self) -> None:
        original = self._ast()
        before = json.dumps(original.to_dict(), sort_keys=True)

        clone = copy.deepcopy(original)
        clone.paragraphs[0].runs[0].font_size_pt = 14.0
        clone.paragraphs[0].text = "MUTATED"

        assert json.dumps(original.to_dict(), sort_keys=True) == before
        assert original.paragraphs[0].runs[0].font_size_pt == 9.0

    def test_lookup_helpers(self) -> None:
        ast = self._ast()
        ast.paragraphs[0].section = Section.INTRODUCTION
        assert ast.paragraph_by_id("p0001") is ast.paragraphs[0]
        assert ast.paragraph_by_id("nope") is None
        assert ast.paragraphs_in_section(Section.INTRODUCTION) == [ast.paragraphs[0]]

    def test_unknown_section_serialises_as_null(self) -> None:
        """Section 5.1 shows `section: null`; UNKNOWN is our internal marker."""
        paragraph = Paragraph(id="p0001", section=None)
        assert paragraph.to_dict()["section"] is None


class TestFixOpConflictKeys:
    def test_actions_writing_one_attribute_share_a_conflict_key(self) -> None:
        """Two rules setting different sizes on one run must be detectable."""
        a = FixOp(rule_id="title-size", target_id="p1.r0", action=FixAction.SET_FONT_SIZE)
        b = FixOp(rule_id="heading-size", target_id="p1.r0", action=FixAction.SET_FONT_SIZE)
        assert (a.target_id, a.attribute) == (b.target_id, b.attribute)

    def test_different_attributes_do_not_collide(self) -> None:
        a = FixOp(rule_id="x", target_id="p1.r0", action=FixAction.SET_FONT_SIZE)
        b = FixOp(rule_id="y", target_id="p1.r0", action=FixAction.SET_BOLD)
        assert a.attribute != b.attribute

    def test_ordering_is_deterministic(self) -> None:
        from manuscript_validator.models import FixPlan

        plan = FixPlan(
            ops=[
                FixOp(rule_id="b", target_id="p2", action=FixAction.SET_BOLD, priority=50),
                FixOp(rule_id="a", target_id="p1", action=FixAction.SET_BOLD, priority=50),
                FixOp(rule_id="c", target_id="p0", action=FixAction.SET_BOLD, priority=10),
            ]
        )
        assert [op.rule_id for op in plan.ordered()] == ["c", "a", "b"]
