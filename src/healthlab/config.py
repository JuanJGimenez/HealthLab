"""Paths, analysis thresholds and validation ranges shared by every layer.

This module is the single place where a number that shapes a result lives. Each
threshold records why it has its value, so a change is a deliberate decision and
not an edit buried in the code that uses it.

This module holds no logic beyond resolving where the app keeps its files.
"""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType
from typing import Final

APP_NAME: Final = "HealthLab"

HOME_ENV_VAR: Final = "HEALTHLAB_HOME"
"""Environment variable that overrides the app folder. Used by tests and development."""


@dataclass(frozen=True, slots=True)
class Paths:
    """Locations of everything the app reads or writes on disk.

    All user data sits under ``root / "data"`` (design decision 2): the database,
    its backups and the original export archives travel together when the app
    folder is copied.

    Attributes:
        root: The app folder.
    """

    root: Path

    @property
    def data_dir(self) -> Path:
        """Folder that holds all user data. Never replaced by an app update."""
        return self.root / "data"

    @property
    def database(self) -> Path:
        """The DuckDB file with every imported record."""
        return self.data_dir / "salud.duckdb"

    @property
    def backups_dir(self) -> Path:
        """Copies of the database taken before each merge."""
        return self.data_dir / "backups"

    @property
    def exports_dir(self) -> Path:
        """Original Samsung Health archives, kept so an import can be redone."""
        return self.data_dir / "exports"

    @property
    def logs_dir(self) -> Path:
        """Technical log files."""
        return self.data_dir / "logs"

    def ensure(self) -> None:
        """Create the data folders that do not exist yet.

        Safe to call on every start: existing folders and their contents are left
        untouched.
        """
        for folder in (self.data_dir, self.backups_dir, self.exports_dir, self.logs_dir):
            folder.mkdir(parents=True, exist_ok=True)


def app_root() -> Path:
    """Return the folder the app runs from.

    Resolution order:

    1. The ``HEALTHLAB_HOME`` environment variable, when set.
    2. The folder of the executable, when running as a packaged app.
    3. The project folder, when running from source.

    Returns:
        The absolute path of the app folder.
    """
    override = os.environ.get(HOME_ENV_VAR)
    if override:
        return Path(override).expanduser().resolve()
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    # src/healthlab/config.py -> project folder is two levels above the package.
    return Path(__file__).resolve().parents[2]


def default_paths() -> Paths:
    """Return the paths for the current app folder."""
    return Paths(root=app_root())


@dataclass(frozen=True, slots=True)
class Thresholds:
    """Numbers that decide how records are grouped, counted and kept.

    Attributes:
        night_min_duration_min: A sleep session longer than this is a night; shorter
            ones are naps or fragments. With 120 the September 2026 export yields
            503 nights.
        signal_join_padding_min: Samsung does not link oxygen, temperature or
            breathing records to a sleep session. A record belongs to a night when
            it starts between this many minutes before sleep onset and wake-up.
            30 matched 545 of 547 nights in the prototype.
        low_spo2_threshold_pct: Oxygen saturation under this value counts as low.
            It is Samsung's own threshold: ``low_duration`` is above zero exactly
            in the nights whose minimum fell below 90.
        sustained_low_min: Minutes under the threshold from which a night is
            reported as a sustained drop. A single low reading is often a sensor
            artifact; five accumulated minutes are not.
        spo2_min_recorded_hours: Oxygen figures are reported only for nights with
            at least this many recorded hours, so a short recording cannot pass
            for a clean night.
        min_nights_per_month: A month with fewer nights is not charted, because an
            average of two nights misleads.
        min_nights_per_group: Smallest group for a with/without comparison; below
            it the app warns that the comparison is not reliable.
        recalculation_warning_age_days: The import preview highlights changes to
            records older than this, the sign that Samsung recalculated history.
        backups_to_keep: Database backups kept (design decision 16).
        exports_to_keep: Original archives kept (design decision 18). An archive
            holding dates older than every newer archive is never deleted.
    """

    night_min_duration_min: int = 120
    signal_join_padding_min: int = 30
    low_spo2_threshold_pct: int = 90
    sustained_low_min: int = 5
    spo2_min_recorded_hours: float = 3.0
    min_nights_per_month: int = 5
    min_nights_per_group: int = 10
    recalculation_warning_age_days: int = 30
    backups_to_keep: int = 2
    exports_to_keep: int = 2


THRESHOLDS: Final = Thresholds()


@dataclass(frozen=True, slots=True)
class ValueRange:
    """Closed interval of plausible values for one measure.

    Attributes:
        low: Smallest accepted value.
        high: Largest accepted value.
    """

    low: float
    high: float

    def __post_init__(self) -> None:
        """Reject an interval whose bounds are inverted."""
        if self.low > self.high:
            msg = f"low ({self.low}) must not exceed high ({self.high})"
            raise ValueError(msg)

    def contains(self, value: float) -> bool:
        """Tell whether ``value`` lies inside the interval, bounds included."""
        return self.low <= value <= self.high


VALID_RANGES: Final = MappingProxyType(
    {
        # A wrist oximeter does not report below 60 %; such a value is a read error.
        "spo2_pct": ValueRange(60, 100),
        # Lowest and highest heart rates seen in the reference export are 30 and 183.
        "heart_rate_bpm": ValueRange(30, 220),
        # A session cannot last a full day; zero or negative means a broken record.
        "sleep_duration_min": ValueRange(1, 24 * 60 - 1),
        # Skin temperature on the wrist during sleep; the export ranges 31.5 to 37.2.
        "skin_temperature_c": ValueRange(25, 42),
        # Breaths per minute; zero means "no measurement" and is stored as missing.
        "respiratory_rate_bpm": ValueRange(4, 40),
    }
)
"""Plausible ranges by measure. A value outside its range is rejected at import."""

EARLIEST_VALID_YEAR: Final = 2020
"""Records dated before this year are rejected; the export has a few dated 1970."""
