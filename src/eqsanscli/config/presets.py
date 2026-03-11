"""Configuration presets — reduction algorithm parameters by (distance, wavelength).

These contain ONLY reduction algorithm parameters — NOT file paths.
Calibration files (sensitivity, dark, mask, flux) are set separately by the user.
"""

from __future__ import annotations

# Pattern for cycle-specific calibration directories
MP_DIR_PATTERN = "/SNS/EQSANS/shared/NeXusFiles/EQSANS/{cycle}_mp/"

# Known cycle directories
MP_DIRS = {
    "2025B": "/SNS/EQSANS/shared/NeXusFiles/EQSANS/2025B_mp/",
    "2025A": "/SNS/EQSANS/shared/NeXusFiles/EQSANS/2025A_mp/",
    "2024B": "/SNS/EQSANS/shared/NeXusFiles/EQSANS/2024B_mp/",
}

# Reduction algorithm presets by configuration label.
# A configuration is identified by (detector_distance, wavelength).
# These do NOT include calibration file paths.
CONFIG_PRESETS: dict[str, dict] = {
    "9m8a": {
        "numqbins": 80,
        "qbintype": "linear",
        "cuttofmin": 1000,
        "cuttofmax": 3000,
        "wavelengthstep": 0.1,
        "fitinelasticincoh": False,
        "selectminincoh": True,
        "useerrorweighting": True,
        "incohfit_qmin": 0.3,
        "incohfit_qmax": 0.4,
    },
    "4m10a": {
        "qmin": 0.003,
        "qmax": 0.05,
        "numqbins": 50,
        "qbintype": "log",
        "cuttofmin": 1000,
        "cuttofmax": 3000,
        "wavelengthstep": 0.5,
        "fitinelasticincoh": False,
        "selectminincoh": True,
        "useerrorweighting": True,
        "incohfit_qmin": 0.04,
        "incohfit_qmax": 0.08,
    },
    "4m2.5a": {
        "qmin": 0.006,
        "qmax": 0.1,
        "numqbins": 40,
        "qbintype": "log",
        "cuttofmin": 1000,
        "cuttofmax": 3000,
        "wavelengthstep": 0.1,
        "fitinelasticincoh": False,
        "selectminincoh": True,
        "useerrorweighting": True,
        "incohfit_qmin": 0.025,
        "incohfit_qmax": 0.05,
    },
    "2.5m2.5a": {
        "numqbins": 60,
        "qbintype": "log",
        "cuttofmin": 2000,
        "cuttofmax": 3000,
        "wavelengthstep": 0.1,
        "fitinelasticincoh": True,
        "selectminincoh": True,
        "useerrorweighting": True,
        "incohfit_qmin": 0.1,
        "incohfit_qmax": 0.2,
        "outputwavelengthdependentprofile": True,
    },
    "1.3m4a": {
        "numqbins": 80,
        "qbintype": "log",
        "cuttofmin": 1000,
        "cuttofmax": 3000,
        "wavelengthstep": 0.2,
        "fitinelasticincoh": True,
        "selectminincoh": True,
        "useerrorweighting": True,
        "incohfit_qmin": 0.6,
        "incohfit_qmax": 0.8,
        "outputwavelengthdependentprofile": True,
        "usemaskbacktubes": True,
    },
    "1.3m1a": {
        "numqbins": 80,
        "qbintype": "linear",
        "cuttofmin": 1000,
        "cuttofmax": 3000,
        "wavelengthstep": 0.2,
        "fitinelasticincoh": True,
        "selectminincoh": True,
        "useerrorweighting": True,
        "incohfit_qmin": 0.6,
        "incohfit_qmax": 0.8,
        "outputwavelengthdependentprofile": True,
    },
}


def get_preset(config_label: str) -> dict | None:
    """Get preset parameters for a configuration label, or None if not found."""
    return CONFIG_PRESETS.get(config_label)


def list_presets() -> list[str]:
    """List all available preset configuration labels."""
    return list(CONFIG_PRESETS.keys())
