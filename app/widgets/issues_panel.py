"""Issues panel for surfacing export-blocking workflow problems."""

from __future__ import annotations

from PySide6.QtWidgets import QLabel, QListWidget, QListWidgetItem, QVBoxLayout, QWidget


class IssuesPanel(QWidget):
    """Display aggregate blocking issues and export readiness state."""

    def __init__(self) -> None:
        super().__init__()
        self._status_label = QLabel()
        self._count_label = QLabel()
        self._issues_list = QListWidget()
        self._build_layout()
        self.set_issues([])

    def _build_layout(self) -> None:
        """Build the issues panel layout."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)
        layout.addWidget(self._status_label)
        layout.addWidget(self._count_label)
        layout.addWidget(self._issues_list)

    def set_issues(self, issues: list[str]) -> None:
        """Populate the panel with aggregate blocking issues."""
        self._issues_list.clear()

        if issues:
            self._status_label.setText("Export blocked")
            self._count_label.setText(f"Blocking issues: {len(issues)}")
            for issue in issues:
                self._issues_list.addItem(QListWidgetItem(issue))
            return

        self._status_label.setText("Ready for export")
        self._count_label.setText("Blocking issues: 0")
        self._issues_list.addItem(QListWidgetItem("No blocking issues."))
