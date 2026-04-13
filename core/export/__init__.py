"""Export helpers for writing reviewed recap workbooks.

Keep imports lazy so cache-clearing and recap-only flows do not eagerly import
the Excel writer and workbook dependencies.
"""

from __future__ import annotations

from typing import Any

__all__ = ["build_recap_payload", "export_to_excel"]


def build_recap_payload(*args: Any, **kwargs: Any) -> dict[str, Any]:
    """Build recap payloads without importing workbook-writing dependencies eagerly."""
    from core.export.recap_mapper import build_recap_payload as _build_recap_payload

    return _build_recap_payload(*args, **kwargs)


def export_to_excel(*args: Any, **kwargs: Any) -> None:
    """Write recap workbooks without importing workbook deps at package import time."""
    from core.export.excel_exporter import export_to_excel as _export_to_excel

    _export_to_excel(*args, **kwargs)
