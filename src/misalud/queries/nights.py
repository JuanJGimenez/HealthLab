"""Questions about nights: the list, oxygen, monthly and weekday views, and relations.

Oxygen figures follow one rule everywhere: a night counts only when its oxygen
recording lasted at least three hours, so a short recording cannot pass for a
clean night.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Final

import pandas as pd

from misalud.config import THRESHOLDS
from misalud.queries.common import (
    ALL_TIME,
    Period,
    Record,
    check_metrics,
    records,
)
from misalud.storage.database import Connection

NIGHT_METRICS: Final = (
    "hours",
    "extra_sleep_min",
    "score",
    "efficiency_pct",
    "physical_recovery",
    "mental_recovery",
    "movement_awakening",
    "bedtime_hour",
    "awake_min",
    "light_min",
    "deep_min",
    "rem_min",
    "spo2_avg",
    "spo2_min",
    "low_minutes",
    "intervals_below_90",
    "intervals_below_85",
    "hrv_rmssd_ms",
    "hrv_sdnn_ms",
    "night_hr_avg",
    "night_hr_min",
    "skin_temp_c",
    "skin_temp_vs_baseline_c",
    "respiratory_rate_avg",
    "snoring_min",
    "snoring_events",
    "exercise_min",
    "steps",
    "stress_avg",
)
"""Numeric columns of ``night`` a screen may chart, average or relate."""

OXYGEN_METRICS: Final = frozenset(
    {"spo2_avg", "spo2_min", "low_minutes", "intervals_below_90", "intervals_below_85"}
)
"""Metrics that only count on nights with enough oxygen recording."""

MIN_NIGHTS_TO_CORRELATE: Final = 3
"""A rank correlation of fewer points is always trivially perfect or undefined."""

VALID_OXYGEN: Final = f"spo2_recorded_hours >= {THRESHOLDS.spo2_min_recorded_hours}"


def _value(metric: str) -> str:
    """Return the SQL for a metric, blank on nights where it must not be reported."""
    if metric in OXYGEN_METRICS:
        return f"CASE WHEN {VALID_OXYGEN} THEN {metric} END"
    return metric


def list_nights(connection: Connection, period: Period = ALL_TIME) -> list[Record]:
    """Return every night of a period with all its columns, oldest first.

    Adds ``has_valid_oxygen``: whether the night's oxygen figures may be reported.
    """
    condition, parameters = period.condition("night_date")
    return records(
        connection,
        f"""SELECT *, coalesce({VALID_OXYGEN}, FALSE) AS has_valid_oxygen
        FROM night WHERE {condition} ORDER BY night_date""",
        parameters,
    )


def oxygen_summary(connection: Connection, period: Period = ALL_TIME) -> Record:
    """Summarise the oxygen of a period in one record.

    Returns:
        ``nights``: nights in the period. ``nights_with_oxygen``: those with a
        valid oxygen recording. ``nights_below_90``: valid nights with any time
        under 90 %. ``nights_sustained_low``: valid nights with five minutes or
        more under 90 %. ``median_low_minutes`` and ``average_spo2`` over valid
        nights. ``lowest_spo2`` and ``lowest_spo2_date``: the lowest reading.
    """
    condition, parameters = period.condition("night_date")
    return records(
        connection,
        f"""SELECT
            count(*) AS nights,
            count(*) FILTER ({VALID_OXYGEN}) AS nights_with_oxygen,
            count(*) FILTER ({VALID_OXYGEN} AND low_minutes > 0) AS nights_below_90,
            count(*) FILTER ({VALID_OXYGEN} AND low_minutes >= ?) AS nights_sustained_low,
            median(low_minutes) FILTER ({VALID_OXYGEN}) AS median_low_minutes,
            avg(spo2_avg) FILTER ({VALID_OXYGEN}) AS average_spo2,
            min(spo2_min) FILTER ({VALID_OXYGEN}) AS lowest_spo2,
            arg_min(night_date, spo2_min) FILTER ({VALID_OXYGEN}) AS lowest_spo2_date
        FROM night WHERE {condition}""",
        [THRESHOLDS.sustained_low_min, *parameters],
    )[0]


def worst_oxygen_nights(
    connection: Connection, period: Period = ALL_TIME, limit: int = 30
) -> list[Record]:
    """Return the nights with the most minutes under 90 %, worst first.

    Only nights with a valid oxygen recording and some time under 90 % appear.
    """
    condition, parameters = period.condition("night_date")
    return records(
        connection,
        f"""SELECT * FROM night
        WHERE {condition} AND {VALID_OXYGEN} AND low_minutes > 0
        ORDER BY low_minutes DESC, spo2_min, night_date LIMIT ?""",
        [*parameters, limit],
    )


def nights_by_month(
    connection: Connection, metrics: Sequence[str], period: Period = ALL_TIME
) -> list[Record]:
    """Average metrics month by month.

    Args:
        connection: An open connection.
        metrics: Names from ``NIGHT_METRICS``.
        period: Dates to include.

    Returns:
        One record per month with ``month`` (its first day), ``nights``, the
        average of each metric and ``enough_nights``: false when the month has
        fewer than five nights and its averages should not be charted.

    Raises:
        UnknownMetricError: If a metric is not on the list.
    """
    check_metrics(metrics, NIGHT_METRICS)
    averages = "".join(f", avg({_value(metric)}) AS {metric}" for metric in metrics)
    condition, parameters = period.condition("night_date")
    return records(
        connection,
        f"""SELECT CAST(date_trunc('month', night_date) AS DATE) AS month,
            count(*) AS nights, count(*) >= ? AS enough_nights{averages}
        FROM night WHERE {condition} GROUP BY 1 ORDER BY 1""",
        [THRESHOLDS.min_nights_per_month, *parameters],
    )


def nights_by_weekday(
    connection: Connection, metric: str, period: Period = ALL_TIME
) -> list[Record]:
    """Average and median of a metric for each day of the week.

    Returns:
        One record per weekday that has nights, with ``weekday`` (1 is Monday,
        7 is Sunday; the day the night began), ``nights`` with a value,
        ``average`` and ``median``.

    Raises:
        UnknownMetricError: If the metric is not on the list.
    """
    check_metrics([metric], NIGHT_METRICS)
    condition, parameters = period.condition("night_date")
    value = _value(metric)
    return records(
        connection,
        f"""SELECT weekday, count({value}) AS nights,
            avg({value}) AS average, median({value}) AS median
        FROM night WHERE {condition} GROUP BY weekday ORDER BY weekday""",
        parameters,
    )


def relate(connection: Connection, x: str, y: str, period: Period = ALL_TIME) -> Record:
    """Pair two metrics night by night and measure how they move together.

    Args:
        connection: An open connection.
        x: Metric on the horizontal axis.
        y: Metric on the vertical axis.
        period: Dates to include.

    Returns:
        ``points``: one record per night that has both values, with
        ``night_date``, ``x`` and ``y``. ``nights``: how many. ``spearman``:
        Spearman's rank correlation, or ``None`` with fewer than three nights or
        when a metric never changes. ``enough_nights``: false below ten nights,
        when the correlation is not reliable.

    Raises:
        UnknownMetricError: If a metric is not on the list.
    """
    check_metrics([x, y], NIGHT_METRICS)
    condition, parameters = period.condition("night_date")
    points = records(
        connection,
        f"""SELECT night_date, x, y
        FROM (SELECT night_date, {_value(x)} AS x, {_value(y)} AS y FROM night WHERE {condition})
        WHERE x IS NOT NULL AND y IS NOT NULL ORDER BY night_date""",
        parameters,
    )
    spearman = None
    frame = pd.DataFrame(points, columns=["night_date", "x", "y"])
    if (
        len(frame) >= MIN_NIGHTS_TO_CORRELATE
        and frame["x"].nunique() > 1
        and frame["y"].nunique() > 1
    ):
        ranks_x = frame["x"].astype("float64").rank()
        ranks_y = frame["y"].astype("float64").rank()
        spearman = float(ranks_x.corr(ranks_y))
    return {
        "points": points,
        "nights": len(points),
        "spearman": spearman,
        "enough_nights": len(points) >= THRESHOLDS.min_nights_per_group,
    }
