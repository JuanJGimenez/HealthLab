"""Figures for the doctor's report that no screen needs.

Oxygen figures follow the same rule as everywhere else: only nights with at
least three hours of oxygen recording count.
"""

from __future__ import annotations

from dataclasses import replace

from misalud.config import THRESHOLDS
from misalud.queries.common import ALL_TIME, NightScope, Period, Record, records
from misalud.queries.nights import VALID_OXYGEN
from misalud.storage.database import Connection
from misalud.storage.schema import NOTE_TAG_KEY

LONG_LOW_MIN = 10
"""Second level of minutes under 90 % reported in the summary, above the main one of 5."""


def report_summary(connection: Connection, period: Period = ALL_TIME) -> Record:
    """Return the one-page summary of a period.

    Returns:
        ``nights``, ``first_night`` and ``last_night``; ``nights_with_oxygen``;
        ``average_spo2``; ``nights_below_90`` (any time under 90 %),
        ``nights_5_min`` and ``nights_10_min`` (that many minutes or more);
        ``max_low_minutes`` and ``max_low_date``; ``average_night_hr``;
        ``average_asleep_hours``; ``snoring_nights`` (nights with snoring
        recorded) and ``median_snoring_min`` among them.
    """
    condition, parameters = period.condition("night_date")
    return records(
        connection,
        f"""SELECT
            count(*) AS nights,
            min(night_date) AS first_night,
            max(night_date) AS last_night,
            count(*) FILTER ({VALID_OXYGEN}) AS nights_with_oxygen,
            avg(spo2_avg) FILTER ({VALID_OXYGEN}) AS average_spo2,
            count(*) FILTER ({VALID_OXYGEN} AND low_minutes > 0) AS nights_below_90,
            count(*) FILTER ({VALID_OXYGEN} AND low_minutes >= ?) AS nights_5_min,
            count(*) FILTER ({VALID_OXYGEN} AND low_minutes >= ?) AS nights_10_min,
            max(low_minutes) FILTER ({VALID_OXYGEN}) AS max_low_minutes,
            arg_max(night_date, low_minutes) FILTER ({VALID_OXYGEN}) AS max_low_date,
            avg(night_hr_avg) AS average_night_hr,
            avg(asleep_hours) AS average_asleep_hours,
            count(snoring_min) AS snoring_nights,
            median(snoring_min) AS median_snoring_min
        FROM night WHERE {condition}""",
        [THRESHOLDS.sustained_low_min, LONG_LOW_MIN, *parameters],
    )[0]


def low_minutes_series(connection: Connection, period: Period = ALL_TIME) -> list[Record]:
    """Return the minutes under 90 % of each night with a valid oxygen recording."""
    condition, parameters = period.condition("night_date")
    return records(
        connection,
        f"""SELECT night_date, low_minutes FROM night
        WHERE {condition} AND {VALID_OXYGEN} ORDER BY night_date""",
        parameters,
    )


def top_nights(connection: Connection, period: Period = ALL_TIME, limit: int = 10) -> list[Record]:
    """Return the nights with the most time under 90 %, with the tags of their date.

    Nights are ranked by accumulated minutes, never by the lowest reading: one
    isolated low value can be a sensor artifact.

    Returns:
        One record per night, worst first, with ``night_date``, ``weekday``,
        ``low_minutes``, ``spo2_min``, ``night_hr_avg``, ``snoring_min``,
        ``bedtime_hour`` and ``tags``: a list of ``name`` and ``builtin_key``.
        Nights without any time under 90 % are left out.
    """
    condition, parameters = period.condition("night_date")
    return records(
        connection,
        f"""SELECT night_date, weekday, low_minutes, spo2_min, night_hr_avg, snoring_min,
            bedtime_hour,
            coalesce((
                SELECT list(struct_pack(name := t.name, builtin_key := t.builtin_key)
                    ORDER BY t.tag_id)
                FROM annotation a JOIN tag t USING (tag_id)
                WHERE a.day = night_date AND t.builtin_key IS DISTINCT FROM ?
            ), []) AS tags
        FROM night
        WHERE {condition} AND {VALID_OXYGEN} AND low_minutes > 0
        ORDER BY low_minutes DESC, night_date LIMIT ?""",
        [NOTE_TAG_KEY, *parameters, limit],
    )


def _sustained_share(connection: Connection, scope: NightScope) -> tuple[int, int]:
    """Return the nights with valid oxygen in a scope and how many had a sustained drop."""
    condition, parameters = scope.condition("night_date")
    row = records(
        connection,
        f"""SELECT count(*) AS nights, count(*) FILTER (low_minutes >= ?) AS sustained
        FROM night WHERE {condition} AND {VALID_OXYGEN}""",
        [THRESHOLDS.sustained_low_min, *parameters],
    )[0]
    return row["nights"], row["sustained"]


def tag_patterns(connection: Connection, period: Period = ALL_TIME) -> list[Record]:
    """Compare, for each tag, the share of nights with five minutes or more under 90 %.

    A tag appears only when both groups, with and without it, have at least ten
    nights with valid oxygen: a smaller group would mislead.

    Returns:
        One record per tag with ``name``, ``builtin_key``, and for each group
        ``with_nights``, ``with_sustained``, ``with_share_pct`` and the same
        three with the ``without_`` prefix.
    """
    base = period if isinstance(period, NightScope) else NightScope(period.start, period.end)
    tags = records(
        connection,
        """SELECT tag_id, name, builtin_key FROM tag
        WHERE builtin_key IS DISTINCT FROM ? ORDER BY tag_id""",
        [NOTE_TAG_KEY],
    )
    patterns: list[Record] = []
    for tag in tags:
        groups = {
            label: _sustained_share(connection, replace(base, tag_id=tag["tag_id"], tagged=flag))
            for label, flag in (("with", True), ("without", False))
        }
        if min(nights for nights, _ in groups.values()) < THRESHOLDS.min_nights_per_group:
            continue
        pattern: Record = {"name": tag["name"], "builtin_key": tag["builtin_key"]}
        for label, (nights, sustained) in groups.items():
            pattern[f"{label}_nights"] = nights
            pattern[f"{label}_sustained"] = sustained
            pattern[f"{label}_share_pct"] = 100.0 * sustained / nights
        patterns.append(pattern)
    return patterns
