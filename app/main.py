"""Application entry point for the Job Cost Tool review UI."""

from __future__ import annotations

import sys
from pathlib import Path

from PySide6.QtWidgets import QApplication

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from app.window import MainWindow


def main() -> int:
    """Launch the desktop review application."""
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
