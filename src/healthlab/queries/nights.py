"""Questions about nights: the list, oxygen, monthly and weekday views, and relations.

Oxygen figures follow one rule everywhere: a night counts only when its oxygen
recording lasted at least three hours, so a short recording cannot pass for a
clean night.
"""

from __future__ import annotations

import csv
import io
from collections.abc import Sequence
from dataclasses import replace
from types import MappingProxyType
from typing import Final, TypedDict, cast

import pandas as pd

from healthlab.config import THRESHOLDS
from healthlab.queries.common import (
    ALL_TIME,
    NightScope,
    Period,
    Record,
    check_metrics,
    records,
)
from healthlab.storage.database import Connection

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
    "asleep_hours",
    "spo2_avg",
    "spo2_min",
    "low_minutes",
    "below_85_minutes",
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

DAY_RELATE_METRICS: Final = (
    "day.active_min",
    "day.distance_m",
    "day.floors",
    "day.active_calorie_kcal",
    "day.hr_avg",
    "day.hr_min",
    "day.hr_max",
    "day.energy_score",
)
"""Measures of a day that can be related with the night that follows it.

Steps, exercise and stress of the day are already columns of ``night``.
"""

RELATE_METRICS: Final = (*NIGHT_METRICS, *DAY_RELATE_METRICS)
"""Everything the Relate view can put on an axis."""

_DAY_COLUMNS: Final = ", ".join(
    f'{name.removeprefix("day.")} AS "{name}"' for name in DAY_RELATE_METRICS
)

OXYGEN_METRICS: Final = frozenset({"spo2_avg", "spo2_min", "low_minutes", "below_85_minutes"})
"""Metrics that only count on nights with enough oxygen recording."""

MIN_NIGHTS_TO_CORRELATE: Final = 3
"""A rank correlation of fewer points is always trivially perfect or undefined."""

VALID_OXYGEN: Final = f"spo2_recorded_hours >= {THRESHOLDS.spo2_min_recorded_hours}"


def metric_value(metric: str) -> str:
    """Return the SQL for a metric, blank on nights where it must not be reported."""
    if metric in OXYGEN_METRICS:
        return f"CASE WHEN {VALID_OXYGEN} THEN {metric} END"
    if metric in DAY_RELATE_METRICS:
        return f'"{metric}"'
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


WORST_ORDERS: Final = MappingProxyType(
    {
        "low_minutes": "low_minutes DESC, spo2_min, night_date",
        "spo2_min": "spo2_min, low_minutes DESC, night_date",
        "below_85_minutes": "below_85_minutes DESC, low_minutes DESC, night_date",
    }
)
"""Ways to rank the hardest nights, by the metric that comes first."""


def worst_oxygen_nights(
    connection: Connection,
    period: Period = ALL_TIME,
    limit: int = 15,
    order_by: str = "low_minutes",
) -> list[Record]:
    """Return the hardest nights for oxygen, worst first.

    Only nights with a valid oxygen recording appear.

    Args:
        connection: An open connection.
        period: Dates to include.
        limit: Largest number of nights to return.
        order_by: ``low_minutes`` (most minutes under 90 %), ``spo2_min``
            (lowest reading) or ``below_85_minutes`` (most time under 85 %).

    Raises:
        UnknownMetricError: If ``order_by`` is not one of the three.
    """
    check_metrics([order_by], list(WORST_ORDERS))
    condition, parameters = period.condition("night_date")
    return records(
        connection,
        f"""SELECT * FROM night WHERE {condition} AND {VALID_OXYGEN}
        ORDER BY {WORST_ORDERS[order_by]} LIMIT ?""",
        [*parameters, limit],
    )


def overview(connection: Connection, period: Period = ALL_TIME) -> Record:
    """Return the headline figures of a period, for the cards above every view.

    Returns:
        The fields of ``oxygen_summary`` plus ``first_night`` and ``last_night``,
        ``average_hours`` in bed and ``average_asleep_hours``, ``median_hrv_ms``
        and ``average_night_hr``.
    """
    condition, parameters = period.condition("night_date")
    sleep = records(
        connection,
        f"""SELECT min(night_date) AS first_night, max(night_date) AS last_night,
            avg(hours) AS average_hours, avg(asleep_hours) AS average_asleep_hours,
            median(hrv_rmssd_ms) AS median_hrv_ms, avg(night_hr_avg) AS average_night_hr
        FROM night WHERE {condition}""",
        parameters,
    )[0]
    return {**oxygen_summary(connection, period), **sleep}


def sustained_low_by_weekday(connection: Connection, period: Period = ALL_TIME) -> Record:
    """Count, for each day of the week, the nights with five minutes or more under 90 %.

    Returns:
        ``weekdays``: one record per weekday with nights, holding ``weekday``
        (1 is Monday), ``nights`` with valid oxygen, ``sustained`` among them and
        ``share_pct``. ``overall_share_pct``: the same share over the whole period,
        ``None`` when no night has valid oxygen.
    """
    condition, parameters = period.condition("night_date")
    counts = f"""count(*) AS nights,
        count(*) FILTER (low_minutes >= {THRESHOLDS.sustained_low_min}) AS sustained"""
    share = "100.0 * sustained / nights AS share_pct"
    weekdays = records(
        connection,
        f"""SELECT weekday, nights, sustained, {share} FROM (
            SELECT weekday, {counts} FROM night WHERE {condition} AND {VALID_OXYGEN}
            GROUP BY weekday) ORDER BY weekday""",
        parameters,
    )
    nights = sum(row["nights"] for row in weekdays)
    sustained = sum(row["sustained"] for row in weekdays)
    return {
        "weekdays": weekdays,
        "overall_share_pct": 100.0 * sustained / nights if nights else None,
    }


def rolling_median(
    connection: Connection, metric: str, period: Period = ALL_TIME, window: int = 14
) -> list[Record]:
    """Return the median of a metric over the last ``window`` nights, night by night.

    Nights without a value are skipped: the window always holds the most recent
    nights that have one.

    Args:
        connection: An open connection.
        metric: A name from ``NIGHT_METRICS``.
        period: Dates to include.
        window: Number of nights in the window.

    Returns:
        One record per night with a value, holding ``night_date`` and ``value``.

    Raises:
        UnknownMetricError: If the metric is not on the list.
    """
    check_metrics([metric], NIGHT_METRICS)
    condition, parameters = period.condition("night_date")
    points = records(
        connection,
        f"""SELECT night_date, value FROM (
            SELECT night_date, {metric_value(metric)} AS value FROM night WHERE {condition})
        WHERE value IS NOT NULL ORDER BY night_date""",
        parameters,
    )
    values = pd.Series([point["value"] for point in points], dtype="float64")
    medians = values.rolling(window, min_periods=1).median()
    return [
        {"night_date": point["night_date"], "value": float(median)}
        for point, median in zip(points, medians, strict=True)
    ]


def nights_csv(connection: Connection, period: Period = ALL_TIME) -> str:
    """Return the nights of a period as CSV text, one line per night.

    The first line holds the column names. Empty values are empty cells.
    """
    rows = list_nights(connection, period)
    output = io.StringIO()
    if rows:
        writer = csv.DictWriter(output, fieldnames=list(rows[0]), lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
    return output.getvalue()


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
    averages = "".join(f", avg({metric_value(metric)}) AS {metric}" for metric in metrics)
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
    value = metric_value(metric)
    return records(
        connection,
        f"""SELECT weekday, count({value}) AS nights,
            avg({value}) AS average, median({value}) AS median
        FROM night WHERE {condition} GROUP BY weekday ORDER BY weekday""",
        parameters,
    )


class Relation(TypedDict):
    """Two metrics paired night by night, with how they move together."""

    points: list[Record]
    nights: int
    spearman: float | None
    enough_nights: bool


class GroupFigures(TypedDict):
    """Figures of the nights on one side of a with-and-without comparison."""

    nights: int
    nights_with_oxygen: int
    median_low_minutes: float | None
    average_low_minutes: float | None
    average_night_hr: float | None
    median_hrv_ms: float | None
    enough_nights: bool


# Functional form: ``with`` is a reserved word and cannot be a class attribute.
TagComparison = TypedDict("TagComparison", {"with": GroupFigures, "without": GroupFigures})
"""The nights whose date carries a tag, beside the nights whose date does not."""


def relate(
    connection: Connection,
    x: str,
    y: str,
    period: Period = ALL_TIME,
    highlight_tag_id: int | None = None,
) -> Relation:
    """Pair two metrics night by night and measure how they move together.

    Args:
        connection: An open connection.
        x: Metric on the horizontal axis, from ``RELATE_METRICS``. A name that
            starts with ``day.`` is a measure of the day the night began.
        y: Metric on the vertical axis.
        period: Dates to include.
        highlight_tag_id: A tag whose nights are flagged in the result, to draw
            them in another colour.

    Returns:
        ``points``: one record per night that has both values, with
        ``night_date``, ``x``, ``y`` and ``tagged``. ``nights``: how many. ``spearman``:
        Spearman's rank correlation, or ``None`` with fewer than three nights or
        when a metric never changes. ``enough_nights``: false below ten nights,
        when the correlation is not reliable.

    Raises:
        UnknownMetricError: If a metric is not on the list.
    """
    check_metrics([x, y], RELATE_METRICS)
    condition, parameters = period.condition("night_date")
    points = records(
        connection,
        f"""SELECT night_date, x, y, tagged
        FROM (SELECT night_date, {metric_value(x)} AS x, {metric_value(y)} AS y,
                night_date IN (SELECT day FROM annotation WHERE tag_id = ?) AS tagged
            FROM night
            LEFT JOIN (SELECT day AS day_key, {_DAY_COLUMNS} FROM day) ON day_key = night_date
            WHERE {condition})
        WHERE x IS NOT NULL AND y IS NOT NULL ORDER BY night_date""",
        [highlight_tag_id, *parameters],
    )
    spearman = None
    frame = pd.DataFrame(points, columns=["night_date", "x", "y", "tagged"])
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


def _group_figures(connection: Connection, scope: NightScope) -> GroupFigures:
    """Return the figures of one side of a with-and-without comparison."""
    condition, parameters = scope.condition("night_date")
    figures = records(
        connection,
        f"""SELECT count(*) AS nights,
            count(*) FILTER ({VALID_OXYGEN}) AS nights_with_oxygen,
            median(low_minutes) FILTER ({VALID_OXYGEN}) AS median_low_minutes,
            avg(low_minutes) FILTER ({VALID_OXYGEN}) AS average_low_minutes,
            avg(night_hr_avg) AS average_night_hr,
            median(hrv_rmssd_ms) AS median_hrv_ms
        FROM night WHERE {condition}""",
        parameters,
    )[0]
    figures["enough_nights"] = figures["nights"] >= THRESHOLDS.min_nights_per_group
    return cast(GroupFigures, figures)


def tag_comparison(connection: Connection, tag_id: int, period: Period = ALL_TIME) -> TagComparison:
    """Compare the nights whose date carries a tag with the nights whose date does not.

    The number of nights of each group is always part of the answer, and
    ``enough_nights`` is false for a group of fewer than ten: a difference seen
    on a handful of nights says little.

    Args:
        connection: An open connection.
        tag_id: The tag that splits the nights.
        period: Dates and kind of night to include. A tag filter in it is replaced.

    Returns:
        ``with`` and ``without``: for each group, ``nights``,
        ``nights_with_oxygen``, ``median_low_minutes``, ``average_low_minutes``,
        ``average_night_hr``, ``median_hrv_ms`` and ``enough_nights``.
    """
    base = period if isinstance(period, NightScope) else NightScope(period.start, period.end)
    return {
        "with": _group_figures(connection, replace(base, tag_id=tag_id, tagged=True)),
        "without": _group_figures(connection, replace(base, tag_id=tag_id, tagged=False)),
    }
