"""Renders a ValidationReport in-app (Task 14).

Two widgets: `ReportView` (one row per violation) and `SectionOverridePanel`
(one row per paragraph, a dropdown to relabel its detected section). The
override panel is what eliminates segmentation's worst failure mode -- a
wrong section label cascades into every rule scoped to it -- by letting a
human correct it and re-run rather than requiring a perfect segmenter.
"""

from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QComboBox,
    QHeaderView,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from manuscript_validator.models.ast import Ast
from manuscript_validator.models.enums import Section
from manuscript_validator.models.report import ValidationReport


class ReportView(QTableWidget):
    """One row per violation: rule id, section, severity, status, message."""

    _COLUMNS = ("Rule", "Section", "Severity", "Status", "Message")

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setColumnCount(len(self._COLUMNS))
        self.setHorizontalHeaderLabels(self._COLUMNS)
        self.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)

    def set_report(self, report: ValidationReport) -> None:
        self.setRowCount(len(report.violations))
        for row, violation in enumerate(report.violations):
            section = violation.section.value if violation.section else ""
            values = (
                violation.rule_id,
                section,
                violation.severity.value,
                violation.status.value,
                violation.message or violation.found,
            )
            for column, value in enumerate(values):
                self.setItem(row, column, QTableWidgetItem(value))


class SectionOverridePanel(QWidget):
    """Detected sections with a per-block dropdown. Emits `overrides_applied`
    with a `{paragraph_id: section_value}` dict -- only entries the user
    actually changed from the segmenter's own labelling -- for the caller to
    pass as `PipelineOptions.section_overrides` on the next run.
    """

    overrides_applied = Signal(dict)

    _COLUMNS = ("Paragraph", "Text", "Detected section")

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._original_sections: dict[str, str | None] = {}

        self._table = QTableWidget()
        self._table.setColumnCount(len(self._COLUMNS))
        self._table.setHorizontalHeaderLabels(self._COLUMNS)
        self._table.horizontalHeader().setSectionResizeMode(
            1, QHeaderView.ResizeMode.Stretch
        )

        apply_button = QPushButton("Apply overrides and re-validate")
        apply_button.clicked.connect(self._on_apply)

        layout = QVBoxLayout(self)
        layout.addWidget(self._table)
        layout.addWidget(apply_button)

    def set_ast(self, ast: Ast) -> None:
        self._original_sections = {
            paragraph.id: (paragraph.section.value if paragraph.section else None)
            for paragraph in ast.paragraphs
        }
        self._table.setRowCount(len(ast.paragraphs))
        for row, paragraph in enumerate(ast.paragraphs):
            self._table.setItem(row, 0, QTableWidgetItem(paragraph.id))
            self._table.setItem(row, 1, QTableWidgetItem(paragraph.text.strip()[:80]))

            combo = QComboBox()
            combo.addItem("(unassigned)", None)
            for section in Section:
                combo.addItem(section.value, section.value)
            if paragraph.section is not None:
                index = combo.findData(paragraph.section.value)
                if index >= 0:
                    combo.setCurrentIndex(index)
            self._table.setCellWidget(row, 2, combo)

    def _on_apply(self) -> None:
        overrides: dict[str, str] = {}
        for row in range(self._table.rowCount()):
            paragraph_id_item = self._table.item(row, 0)
            combo = self._table.cellWidget(row, 2)
            if paragraph_id_item is None or not isinstance(combo, QComboBox):
                continue
            paragraph_id = paragraph_id_item.text()
            new_value = combo.currentData()
            if new_value is not None and new_value != self._original_sections.get(paragraph_id):
                overrides[paragraph_id] = new_value
        self.overrides_applied.emit(overrides)


__all__ = ["ReportView", "SectionOverridePanel"]
