"""Session state model — complete application state, saved/restored across sessions."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

import pandas as pd

from eqsanscli.models.working_table import WorkingTable


def _sessions_dir() -> Path:
    d = Path.cwd() / ".eqsanscli" / "sessions"
    d.mkdir(parents=True, exist_ok=True)
    return d


@dataclass
class CalibrationFiles:
    """Cycle-specific calibration files, set by user."""

    cycle: str = ""
    sensitivity_4m: str = ""
    sensitivity_2o5m: str = ""
    sensitivity_1o3m: str = ""
    dark_current: str = ""
    beam_flux: str = ""

    def to_dict(self) -> dict:
        return {
            "cycle": self.cycle,
            "sensitivity_4m": self.sensitivity_4m,
            "sensitivity_2o5m": self.sensitivity_2o5m,
            "sensitivity_1o3m": self.sensitivity_1o3m,
            "dark_current": self.dark_current,
            "beam_flux": self.beam_flux,
        }

    @classmethod
    def from_dict(cls, data: dict) -> CalibrationFiles:
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})


@dataclass
class SessionState:
    """Complete application state — saved/restored across sessions."""

    name: str = "default"
    ipts: int = 0
    catalog_data: Optional[list[dict]] = None  # serializable form of catalog DataFrame
    tables: dict[str, WorkingTable] = field(default_factory=lambda: {"default": WorkingTable("default")})
    active_table: str = "default"
    configurations: dict[str, dict] = field(default_factory=dict)  # config_label -> param dict
    calibration: CalibrationFiles = field(default_factory=CalibrationFiles)
    stitch_groups: list = field(default_factory=list)
    output_directory: str = "./output/"
    reduced_files: list[str] = field(default_factory=list)
    command_history: list[str] = field(default_factory=list)
    wrap_width: int = 100
    plot_figsize: tuple[int, int] = (5, 4)
    plot_dpi: int = 150
    plot_logx: bool = True
    plot_logy: bool = True
    plot_errorbars: bool = True
    plot_linestyle: str = "line+marker"
    max_workers: int = 1
    drtsans_version: str = "default"
    llm_tokens_used: int = 0
    llm_calls: int = 0

    @property
    def catalog(self) -> Optional[pd.DataFrame]:
        """Get catalog as DataFrame."""
        if self.catalog_data is None:
            return None
        return pd.DataFrame(self.catalog_data)

    @catalog.setter
    def catalog(self, df: Optional[pd.DataFrame]) -> None:
        """Store catalog from DataFrame."""
        if df is None:
            self.catalog_data = None
        else:
            self.catalog_data = df.to_dict("records")

    def run_title(self, run_number: str) -> str:
        """Look up the title for a run number from the catalog.

        Accepts comma-separated run numbers (e.g. "172804, 172805") — uses the first.
        Returns empty string if not found.
        """
        if not run_number or self.catalog_data is None:
            return ""
        # Handle comma-separated multi-run
        first = run_number.split(",")[0].strip()
        try:
            first_int = int(first)
        except ValueError:
            return ""
        for record in self.catalog_data:
            try:
                if int(record.get("run_number", 0)) == first_int:
                    return str(record.get("title", ""))
            except (ValueError, TypeError):
                continue
        return ""

    @property
    def current_table(self) -> WorkingTable:
        """Get the currently active working table."""
        if self.active_table not in self.tables:
            self.tables[self.active_table] = WorkingTable(self.active_table)
        return self.tables[self.active_table]

    def add_to_history(self, command: str) -> None:
        """Append a command to history."""
        self.command_history.append(command)

    def restore_from(self, other: SessionState) -> None:
        """Copy all persistent state from *other* into this instance.

        Used by /session load and /continue so that every field is restored
        without manually listing them (which is error-prone when new fields
        are added).
        """
        # Fields that should NOT be overwritten (transient / runtime-only)
        _skip = {"llm_tokens_used", "llm_calls"}
        for fld in self.__dataclass_fields__:
            if fld in _skip:
                continue
            setattr(self, fld, getattr(other, fld))

    def save(self, path: str | None = None) -> str:
        if path is None:
            path = str(_sessions_dir() / f"{self.name}.json")

        data = {
            "name": self.name,
            "ipts": self.ipts,
            "catalog_data": self.catalog_data,
            "tables": {k: v.to_dict() for k, v in self.tables.items()},
            "active_table": self.active_table,
            "configurations": self.configurations,
            "calibration": self.calibration.to_dict(),
            "output_directory": self.output_directory,
            "reduced_files": self.reduced_files,
            "wrap_width": self.wrap_width,
            "plot_figsize": list(self.plot_figsize),
            "plot_dpi": self.plot_dpi,
            "plot_logx": self.plot_logx,
            "plot_logy": self.plot_logy,
            "plot_errorbars": self.plot_errorbars,
            "plot_linestyle": self.plot_linestyle,
            "max_workers": self.max_workers,
            "drtsans_version": self.drtsans_version,
            "command_history": self.command_history[-500:],  # keep last 500
        }
        with open(path, "w") as f:
            json.dump(data, f, indent=2, default=str)

        # Update the global breadcrumb so /continue can find this autosave from
        # any cwd — but only when the session has real content, so we don't
        # clobber a good breadcrumb with an empty just-launched-elsewhere session.
        has_content = (
            self.ipts != 0
            or any(t.rows for t in self.tables.values())
        )
        if has_content and os.path.basename(path) == "_autosave.json":
            self.record_breadcrumb(path)

        return path

    @classmethod
    def load(cls, name_or_path: str) -> SessionState:
        """Load session from file."""
        path = name_or_path
        if not os.path.exists(path):
            path = str(_sessions_dir() / f"{name_or_path}.json")
        if not os.path.exists(path):
            raise FileNotFoundError(f"Session not found: {name_or_path}")

        with open(path) as f:
            data = json.load(f)

        state = cls(
            name=data.get("name", "default"),
            ipts=data.get("ipts", 0),
            catalog_data=data.get("catalog_data"),
            active_table=data.get("active_table", "default"),
            configurations=data.get("configurations", {}),
            calibration=CalibrationFiles.from_dict(data.get("calibration", {})),
            output_directory=data.get("output_directory", "./output/"),
            reduced_files=data.get("reduced_files", []),
            wrap_width=data.get("wrap_width", 100),
            plot_figsize=tuple(data.get("plot_figsize", [5, 4])),
            plot_dpi=data.get("plot_dpi", 150),
            plot_logx=data.get("plot_logx", True),
            plot_logy=data.get("plot_logy", True),
            plot_errorbars=data.get("plot_errorbars", True),
            plot_linestyle=data.get("plot_linestyle", "line+marker"),
            max_workers=data.get("max_workers", 1),
            drtsans_version=data.get("drtsans_version", "default"),
            command_history=data.get("command_history", []),
        )
        state.tables = {
            k: WorkingTable.from_dict(v) for k, v in data.get("tables", {}).items()
        }
        if not state.tables:
            state.tables = {"default": WorkingTable("default")}
        return state

    @classmethod
    def auto_save_path(cls) -> str:
        return str(_sessions_dir() / "_autosave.json")

    @classmethod
    def _breadcrumb_path(cls) -> Path:
        """Global pointer to the most recent autosave, regardless of cwd."""
        d = Path.home() / ".eqsanscli"
        d.mkdir(parents=True, exist_ok=True)
        return d / "last_autosave"

    @classmethod
    def record_breadcrumb(cls, autosave_path: str) -> None:
        """Write the latest autosave path to the global breadcrumb (best-effort)."""
        try:
            cls._breadcrumb_path().write_text(autosave_path)
        except OSError:
            pass

    @classmethod
    def read_breadcrumb(cls) -> str | None:
        """Return the path from the breadcrumb if it exists and is non-empty."""
        try:
            p = cls._breadcrumb_path()
            if p.exists():
                text = p.read_text().strip()
                return text or None
        except OSError:
            pass
        return None
