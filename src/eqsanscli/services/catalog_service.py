"""Catalog service — fetches, caches, and manages experiment catalog data."""

from __future__ import annotations

import logging
from pathlib import Path

import pandas as pd

from eqsanscli.integrations.oncat import fetch_catalog
from eqsanscli.models.run_metadata import RunMetadata

logger = logging.getLogger(__name__)


class CatalogService:
    """Manages experiment catalog data from ONCat."""

    def fetch(self, ipts: int) -> pd.DataFrame:
        """Fetch catalog from ONCat for an IPTS number."""
        return fetch_catalog(ipts)

    def save_catalog(self, df: pd.DataFrame, path: str) -> None:
        """Save catalog to CSV."""
        df.to_csv(path, index=False)
        logger.info("Catalog saved to %s", path)

    def load_catalog(self, path: str) -> pd.DataFrame:
        """Load catalog from CSV."""
        if not Path(path).exists():
            raise FileNotFoundError(f"Catalog file not found: {path}")
        df = pd.read_csv(path)
        logger.info("Catalog loaded from %s (%d rows)", path, len(df))
        return df

    def to_run_metadata_list(self, df: pd.DataFrame) -> list[RunMetadata]:
        """Convert catalog DataFrame to list of RunMetadata objects."""
        runs = []
        for _, row in df.iterrows():
            runs.append(
                RunMetadata(
                    run_number=int(row.get("run_number", 0)),
                    title=str(row.get("title", "")),
                    detector_distance=float(row.get("detector_distance", 0)),
                    wavelength=float(row.get("wavelength", 0)),
                    total_counts=int(row.get("total_counts", 0)),
                    duration=int(row.get("duration", 0)),
                    proton_charge=float(row.get("proton_charge", 0)),
                    experiment=str(row.get("experiment", "")),
                    location=str(row.get("location", "")),
                )
            )
        return runs
