"""Working table widget — displays run associations for reduction."""

from __future__ import annotations

from textual.widgets import DataTable

from eqsanscli.models.working_table import WorkingTable as WorkingTableModel


class WorkingTableWidget(DataTable):
    """DataTable for displaying the current working table."""

    DEFAULT_CSS = """
    WorkingTableWidget {
        height: 1fr;
    }
    """

    COLUMNS = [
        ("Idx", 5),
        ("Scatt", 8),
        ("Sample", 20),
        ("Trans", 8),
        ("Bkg", 8),
        ("BkgTr", 8),
        ("Empty", 8),
        ("Config", 12),
        ("Status", 10),
    ]

    def on_mount(self) -> None:
        """Set up columns on mount."""
        for label, _width in self.COLUMNS:
            self.add_column(label, key=label)

    def load_table(self, table: WorkingTableModel) -> None:
        """Populate the widget from a WorkingTable model."""
        self.clear()
        for row in table.rows:
            self.add_row(
                str(row.index),
                str(row.scattering_run),
                row.sample_name,
                str(row.transmission_run or "—"),
                str(row.background_scatt or "—"),
                str(row.background_trans or "—"),
                str(row.empty_beam or "—"),
                row.configuration,
                row.status,
                key=str(row.index),
            )
