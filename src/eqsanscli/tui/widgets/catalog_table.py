"""Catalog table widget — displays ONCat catalog data in a DataTable."""

from __future__ import annotations

from textual.widgets import DataTable


class CatalogTable(DataTable):
    """DataTable for displaying experiment catalog from ONCat."""

    DEFAULT_CSS = """
    CatalogTable {
        height: 1fr;
    }
    """

    COLUMNS = [
        ("Run #", 8),
        ("Title", 30),
        ("Dist (m)", 9),
        ("λ (Å)", 7),
        ("Count", 8),
        ("Time(s)", 8),
    ]

    def on_mount(self) -> None:
        """Set up columns on mount."""
        for label, _width in self.COLUMNS:
            self.add_column(label, key=label)
