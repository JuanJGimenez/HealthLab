"""Questions about calendar days: the list and the monthly view of activity."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Final

from misalud.queries.common import ALL_TIME, Period, Record, check_metrics, records
from misalud.storage.database import Connection

DAY_METRICS: Final = (
    "steps",
    "active_min",
    "distance_m",
    "floors",
    "active_calorie_kcal",
    "exercise_min",
    "exercise_count",
    "hr_avg",
    "hr_min",
    "hr_max",
    "stress_avg",
    "energy_score",
)
"""Numeric columns of ``day`` a screen may chart or average."""


def list_days(connection: Connection, period: Period = ALL_TIME) -> list[Record]:
    """Return every day of a period with all its columns, oldest first."""
    condition, parameters = period.condition("day")
    return records(connection, f"SELECT * FROM day WHERE {condition} ORDER BY day", parameters)


def days_by_month(
    connection: Connection, metrics: Sequence[str], period: Period = ALL_TIME
) -> list[Record]:
    """Average metrics month by month.

    Args:
        connection: An open connection.
        metrics: Names from ``DAY_METRICS``.
        period: Dates to include.

    Returns:
        One record per month with ``month`` (its first day), ``days`` and the
        average of each metric.

    Raises:
        UnknownMetricError: If a metric is not on the list.
    """
    check_metrics(metrics, DAY_METRICS)
    averages = "".join(f", avg({metric}) AS {metric}" for metric in metrics)
    condition, parameters = period.condition("day")
    return records(
        connection,
        f"""SELECT CAST(date_trunc('month', day) AS DATE) AS month, count(*) AS days{averages}
        FROM day WHERE {condition} GROUP BY 1 ORDER BY 1""",
        parameters,
    )
