"""Everything the "one day" screen shows, and the typical day by hour.

Like the night screen, each track is one independent query registered in
``DAY_TRACKS``. A day runs from midnight to midnight in the local time each
record was taken.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import date, datetime, time, timedelta
from types import MappingProxyType
from typing import Final, TypedDict

from misalud.queries.common import ALL_TIME, Period, Record, records
from misalud.storage.database import Connection

Track = Callable[[Connection, datetime, datetime], list[Record]]


def _pulse(connection: Connection, start: datetime, end: datetime) -> list[Record]:
    """Heart rate, minute by minute."""
    return records(
        connection,
        """SELECT start_at AS at, heart_rate AS value FROM heart_rate_minute
        WHERE start_at >= ? AND start_at < ? AND heart_rate IS NOT NULL ORDER BY start_at""",
        [start, end],
    )


def _stress(connection: Connection, start: datetime, end: datetime) -> list[Record]:
    """Stress, one point per measurement."""
    return records(
        connection,
        """SELECT start_at AS at, score AS value FROM stress
        WHERE start_at >= ? AND start_at < ? AND score IS NOT NULL ORDER BY start_at""",
        [start, end],
    )


def _steps(connection: Connection, start: datetime, end: datetime) -> list[Record]:
    """Steps of each 10-minute interval that has any."""
    return records(
        connection,
        """SELECT start_at AS "from", start_at + INTERVAL 10 MINUTE AS "to", steps AS value
        FROM steps_interval WHERE day = ? AND steps > 0 ORDER BY interval""",
        [start],
    )


def _exercise(connection: Connection, start: datetime, end: datetime) -> list[Record]:
    """Recorded exercise sessions, cut to the day, with their name."""
    return records(
        connection,
        """SELECT greatest(e.start_at, ?) AS "from", least(e.end_at, ?) AS "to",
            l.label, e.duration_min AS minutes
        FROM exercise e JOIN exercise_label l USING (samsung_id)
        WHERE e.start_at < ? AND e.end_at > ? ORDER BY e.start_at""",
        [start, end, end, start],
    )


def _sleep(connection: Connection, start: datetime, end: datetime) -> list[Record]:
    """Sleep sessions, cut to the day: the end of last night and the start of the next."""
    return records(
        connection,
        """SELECT greatest(start_at, ?) AS "from", least(end_at, ?) AS "to", is_night
        FROM sleep_session WHERE start_at < ? AND end_at > ? ORDER BY start_at""",
        [start, end, end, start],
    )


DAY_TRACKS: Final[MappingProxyType[str, Track]] = MappingProxyType(
    {"pulse": _pulse, "stress": _stress, "steps": _steps, "exercise": _exercise, "sleep": _sleep}
)
"""The five tracks of a day, by name, in display order."""


class DayDetail(TypedDict):
    """One day with its tracks and its neighbours."""

    day: Record
    tracks: dict[str, list[Record]]
    previous: str | None
    next: str | None


def day_detail(connection: Connection, day: date) -> DayDetail | None:
    """Return one day with its tracks and its neighbours.

    Args:
        connection: An open connection.
        day: The calendar day.

    Returns:
        ``day``: the row of ``day``. ``tracks``: the data of every track, by
        name; a track without data is an empty list. ``previous`` and ``next``:
        the neighbouring days that have records, or ``None`` at either end. The
        whole result is ``None`` when the day has no records.
    """
    found = records(connection, "SELECT * FROM day WHERE day = ?", [day])
    if not found:
        return None
    start = datetime.combine(day, time.min)
    end = start + timedelta(days=1)
    neighbours = records(
        connection,
        """SELECT (SELECT max(day) FROM day WHERE day < ?) AS previous,
            (SELECT min(day) FROM day WHERE day > ?) AS next""",
        [day, day],
    )[0]
    return {
        "day": found[0],
        "tracks": {name: track(connection, start, end) for name, track in DAY_TRACKS.items()},
        "previous": neighbours["previous"],
        "next": neighbours["next"],
    }


def _by_hour(connection: Connection, table: str, value: str, period: Period) -> list[Record]:
    """Average a measurement by hour of the day, apart for weekdays and weekends."""
    condition, parameters = period.condition("CAST(start_at AS DATE)")
    return records(
        connection,
        f"""SELECT hour(start_at) AS hour,
            avg({value}) FILTER (isodow(start_at) < 6) AS weekdays,
            avg({value}) FILTER (isodow(start_at) >= 6) AS weekend
        FROM "{table}" WHERE {condition} GROUP BY 1 ORDER BY 1""",
        parameters,
    )


def hourly_profile(connection: Connection, period: Period = ALL_TIME) -> Record:
    """Return the typical day: average pulse and stress for each hour.

    Args:
        connection: An open connection.
        period: Dates to include.

    Returns:
        ``pulse`` and ``stress``: one record per hour that has data, with
        ``hour`` (0 to 23), ``weekdays`` (Monday to Friday) and ``weekend``
        (Saturday and Sunday); either average is ``None`` without data.
    """
    return {
        "pulse": _by_hour(connection, "heart_rate_minute", "heart_rate", period),
        "stress": _by_hour(connection, "stress", "score", period),
    }
