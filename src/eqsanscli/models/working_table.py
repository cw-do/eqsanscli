"""Working table models — named collections of runs ready for reduction."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

from eqsanscli.models.config_id import config_ids_match, make_config_id


@dataclass
class WorkingTableRow:
    """A single row in a working table — one scattering run with all associated runs.

    Run number fields are strings because drtsans accepts comma-separated
    multi-run strings like "172760, 172761" for combining statistics.
    An empty string "" means no run assigned (equivalent to None/null).
    """

    index: int
    scattering_run: str  # e.g., "172760" or "172760, 172761"
    sample_name: str
    transmission_run: str = ""  # "" means not assigned
    background_scatt: str = ""
    background_trans: str = ""
    empty_beam: str = ""
    detector_distance: float = 0.0  # meters (from ONCat)
    wavelength: float = 0.0  # Angstroms (from ONCat)
    frequency: int = 60  # Hz (chopper frequency from ONCat)
    thickness: float = 0.1  # cm
    status: str = "ready"  # ready | reducing | done | error | modified
    output_file: Optional[str] = None

    # Fields that affect reduction output — changing any of these on a "done"
    # row means the previous output is stale and needs re-reduction.
    _REDUCTION_FIELDS = frozenset({
        "transmission_run", "background_scatt", "background_trans",
        "empty_beam", "thickness", "sample_name",
    })

    def set_field(self, attr_name: str, value) -> None:
        """Set a field and auto-reset status to 'modified' if the row was 'done'
        and the field affects reduction output."""
        old_value = getattr(self, attr_name, None)
        setattr(self, attr_name, value)
        if attr_name in self._REDUCTION_FIELDS and self.status == "done" and old_value != value:
            self.status = "modified"

    @property
    def configuration(self) -> str:
        return make_config_id(self.detector_distance, self.wavelength, self.frequency)

    @property
    def config_key(self) -> tuple[float, float, int]:
        """Configuration grouping key: (distance, wavelength, frequency)."""
        return (round(self.detector_distance, 1), round(self.wavelength, 1), self.frequency)

    def to_dict(self) -> dict:
        """Serialize for persistence."""
        return {
            "index": self.index,
            "scattering_run": self.scattering_run,
            "sample_name": self.sample_name,
            "transmission_run": self.transmission_run,
            "background_scatt": self.background_scatt,
            "background_trans": self.background_trans,
            "empty_beam": self.empty_beam,
            "detector_distance": self.detector_distance,
            "wavelength": self.wavelength,
            "frequency": self.frequency,
            "thickness": self.thickness,
            "status": self.status,
            "output_file": self.output_file,
        }

    @classmethod
    def from_dict(cls, data: dict) -> WorkingTableRow:
        """Deserialize from saved state."""
        return cls(**data)


@dataclass
class WorkingTable:
    """A named collection of runs ready for reduction. Acts as a tab in the TUI."""

    name: str
    ipts: int = 0
    rows: list[WorkingTableRow] = field(default_factory=list)
    created_at: datetime = field(default_factory=datetime.now)
    last_reduced_at: Optional[datetime] = None

    def add_row(self, row: WorkingTableRow) -> None:
        """Add a row and auto-assign index."""
        row.index = len(self.rows) + 1
        self.rows.append(row)

    def get_row(self, index: int) -> Optional[WorkingTableRow]:
        """Get row by 1-based index."""
        for row in self.rows:
            if row.index == index:
                return row
        return None

    def remove_row(self, index: int) -> Optional[WorkingTableRow]:
        """Remove and return row by 1-based index. Re-indexes remaining rows."""
        removed = None
        new_rows = []
        for row in self.rows:
            if row.index == index:
                removed = row
            else:
                new_rows.append(row)
        self.rows = new_rows
        self._reindex()
        return removed

    def _reindex(self) -> None:
        """Re-assign 1-based indices after row removal."""
        for i, row in enumerate(self.rows):
            row.index = i + 1

    @property
    def configurations(self) -> list[str]:
        """Unique configuration labels in this table, sorted."""
        configs = sorted(set(row.configuration for row in self.rows))
        return configs

    def rows_by_config(self, config_label: str) -> list[WorkingTableRow]:
        return [r for r in self.rows if config_ids_match(r.configuration, config_label)]

    def to_dict(self) -> dict:
        """Serialize for persistence."""
        return {
            "name": self.name,
            "ipts": self.ipts,
            "rows": [r.to_dict() for r in self.rows],
            "created_at": self.created_at.isoformat(),
            "last_reduced_at": self.last_reduced_at.isoformat() if self.last_reduced_at else None,
        }

    @classmethod
    def from_dict(cls, data: dict) -> WorkingTable:
        """Deserialize from saved state."""
        table = cls(
            name=data["name"],
            ipts=data.get("ipts", 0),
            created_at=datetime.fromisoformat(data["created_at"]),
            last_reduced_at=(
                datetime.fromisoformat(data["last_reduced_at"])
                if data.get("last_reduced_at")
                else None
            ),
        )
        table.rows = [WorkingTableRow.from_dict(r) for r in data.get("rows", [])]
        return table
