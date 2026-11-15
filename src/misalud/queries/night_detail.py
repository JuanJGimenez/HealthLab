"""Everything the "one night" screen shows: the night's figures and its eight tracks.

Each track is one independent query registered in ``TRACKS`` (design decision
26): adding, hiding or removing a track touches nothing else. Times are returned
in the local time of the night, as ISO text.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import date, datetime, timedelta
from types import MappingProxyType
from typing import Any, Final

from misalud.config import THRESHOLDS
from misalud.queries.common import Record, records
from misalud.storage.database import Connection

DEFAULT_TRACKS: Final = ("stages", "oxygen", "pulse", "snoring")
"""Tracks shown until the user chooses otherwise."""


class _Night:
    """The span of one night, in UTC, and what is needed to find its records."""

    def __init__(self, row: Record) -> None:
        self.offset = timedelta(minutes=row["utc_offset_min"])
        self.start_utc = datetime.fromisoformat(row["start_at"]) - self.offset
        self.end_utc = datetime.fromisoformat(row["end_at"]) - self.offset
        self.session_id: str = row["session_id"]
        self.spo2_id: str | None = row["spo2_id"]
        self.skin_id: str | None = row["skin_id"]
        self.breathing_id: str | None = row["breathing_id"]
        self.offset_min: int = row["utc_offset_min"]


def _local(column: str) -> str:
    """Return the SQL that turns a UTC column into the night's local time."""
    return f"{column} + to_minutes(?)"


def _minute_series(table: str, value: str) -> Callable[[Connection, _Night], list[Record]]:
    """Build a track that reads a per-minute series keyed by UTC moment."""

    def track(connection: Connection, night: _Night) -> list[Record]:
        return records(
            connection,
            f"""SELECT {_local("start_utc")} AS at, {value} AS value FROM "{table}"
            WHERE start_utc BETWEEN ? AND ? AND {value} IS NOT NULL ORDER BY start_utc""",
            [night.offset_min, night.start_utc, night.end_utc],
        )

    return track


def _night_series(
    table: str, value: str, parent: str
) -> Callable[[Connection, _Night], list[Record]]:
    """Build a track that reads the per-minute series of the night's own record."""

    def track(connection: Connection, night: _Night) -> list[Record]:
        return records(
            connection,
            f"""SELECT {_local("start_utc")} AS at, {value} AS value FROM "{table}"
            WHERE night_samsung_id = ? AND {value} IS NOT NULL ORDER BY start_utc""",
            [night.offset_min, getattr(night, parent)],
        )

    return track


def _stages(connection: Connection, night: _Night) -> list[Record]:
    """Sleep stages of the night's session, as spans with their code."""
    return records(
        connection,
        """SELECT start_at AS "from", end_at AS "to", stage_code AS code FROM sleep_stage
        WHERE session_id = ? ORDER BY start_at""",
        [night.session_id],
    )


def _oxygen(connection: Connection, night: _Night) -> list[Record]:
    """Oxygen of each 10-minute interval, flagged when its lowest reading is under 90 %."""
    return records(
        connection,
        f"""SELECT {_local("start_utc")} AS "from",
            {_local("start_utc")} + INTERVAL 10 MINUTE AS "to",
            spo2_avg AS average, spo2_min AS lowest, spo2_min < ? AS is_low
        FROM spo2_interval WHERE night_samsung_id = ? ORDER BY start_utc""",
        [night.offset_min, night.offset_min, THRESHOLDS.low_spo2_threshold_pct, night.spo2_id],
    )


def _snoring(connection: Connection, night: _Night) -> list[Record]:
    """Snoring events inside the night, as spans with their duration."""
    return records(
        connection,
        """SELECT start_at AS "from", end_at AS "to", duration_s AS seconds FROM snoring_event
        WHERE start_at - to_minutes(CAST(utc_offset_min AS BIGINT)) BETWEEN ? AND ?
        ORDER BY start_at""",
        [night.start_utc, night.end_utc],
    )


TRACKS: Final = MappingProxyType(
    {
        "stages": _stages,
        "oxygen": _oxygen,
        "pulse": _minute_series("heart_rate_minute", "heart_rate"),
        "variability": _minute_series("hrv_window", "rmssd_ms"),
        "snoring": _snoring,
        "breathing": _night_series("respiratory_rate_minute", "rate", "breathing_id"),
        "skin_temperature": _night_series("skin_temperature_minute", "mean_c", "skin_id"),
        "movement": _minute_series("movement_minute", "activity_level"),
    }
)
"""The eight tracks, by name, in display order."""


def night_detail(connection: Connection, night_date: date) -> dict[str, Any] | None:
    """Return one night with its tracks and its neighbours.

    Args:
        connection: An open connection.
        night_date: The date the night belongs to.

    Returns:
        ``night``: the row of ``night``. ``tracks``: the data of every track, by
        name; a track without data is an empty list. ``previous`` and ``next``:
        dates of the neighbouring nights, or ``None`` at either end. The whole
        result is ``None`` when there is no night on that date.
    """
    found = records(connection, "SELECT * FROM night WHERE night_date = ?", [night_date])
    if not found:
        return None
    night = _Night(found[0])
    neighbours = records(
        connection,
        """SELECT (SELECT max(night_date) FROM night WHERE night_date < ?) AS previous,
            (SELECT min(night_date) FROM night WHERE night_date > ?) AS next""",
        [night_date, night_date],
    )[0]
    return {
        "night": found[0],
        "tracks": {name: track(connection, night) for name, track in TRACKS.items()},
        **neighbours,
    }
