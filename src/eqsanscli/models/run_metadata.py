"""Run metadata model — represents a single neutron scattering run from ONCat."""

from __future__ import annotations

from dataclasses import dataclass

from eqsanscli.models.config_id import make_config_id


@dataclass
class RunMetadata:
    """Metadata for a single EQSANS run, fetched from ONCat.

    Fields map to ONCat projection fields:
        - indexed.run_number → run_number
        - metadata.entry.title → title
        - metadata.entry.daslogs.detectorz.average_value → detector_distance
        - metadata.entry.daslogs.wavelength.average_value → wavelength
        - metadata.entry.total_counts → total_counts
        - metadata.entry.duration → duration
        - metadata.entry.proton_charge → proton_charge
        - experiment → experiment
        - location → location
    """

    run_number: int
    title: str
    detector_distance: float  # meters
    wavelength: float  # Angstroms
    frequency: int = 60  # Hz (chopper frequency, typically 30 or 60)
    total_counts: int = 0
    duration: int = 0  # seconds
    proton_charge: float = 0.0  # Coulombs
    experiment: str = ""  # e.g., "IPTS-35520"
    location: str = ""  # NeXus file path

    @property
    def config_key(self) -> tuple[float, float, int]:
        """Configuration grouping key: (distance, wavelength, frequency)."""
        return (round(self.detector_distance, 1), round(self.wavelength, 1), self.frequency)

    @property
    def config_label(self) -> str:
        """Canonical configuration label.

        Format: "<dist>m_<wl>a_<freq>hz" (lowercase, underscores)
        Examples: "1.3m_4.0a_60hz", "4.0m_2.5a_30hz"
        """
        d, w, f = self.config_key
        return make_config_id(d, w, f)

    @property
    def counts_display(self) -> str:
        """Format total_counts for display (e.g., 1.2M, 450K)."""
        if self.total_counts >= 1_000_000:
            return f"{self.total_counts / 1_000_000:.1f}M"
        if self.total_counts >= 1_000:
            return f"{self.total_counts / 1_000:.0f}K"
        return str(self.total_counts)
