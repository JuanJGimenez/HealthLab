"""Shared pieces of the query layer: the period filter and plain-data results.

Every query returns plain Python data (lists and dictionaries of text, numbers,
booleans and ``None``) so the window can pass it to the screens as it is.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date, datetime
from typing import Any

from misalud.storage.database import Connection

Record = dict[str, Any]


class UnknownMetricError(ValueError):
    """A screen asked for a column that is not on the list of metrics."""


@dataclass(frozen=True, slots=True)
class Period:
    """Range of dates a screen is looking at, both ends included.

    Attributes:
        start: First date, or ``None`` for no lower limit.
        end: Last date, or ``None`` for no upper limit.
    """

    start: date | None = None
    end: date | None = None

    def condition(self, column: str) -> tuple[str, list[date]]:
        """Return the SQL condition that keeps the rows of this period.

        Args:
            column: Name of the date column to filter.

        Returns:
            The condition text and its parameters, in order.
        """
        parts, parameters = ["TRUE"], []
        if self.start is not None:
            parts.append(f"{column} >= ?")
            parameters.append(self.start)
        if self.end is not None:
            parts.append(f"{column} <= ?")
            parameters.append(self.end)
        return " AND ".join(parts), parameters


ALL_TIME = Period()


def plain(value: object) -> object:
    """Turn a database value into something a screen can show.

    Dates and moments become ISO text; a number that is not a number becomes
    ``None``. Everything else passes unchanged.
    """
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if isinstance(value, float) and math.isnan(value):
        return None
    return value


def records(connection: Connection, sql: str, parameters: Sequence[object] = ()) -> list[Record]:
    """Run a query and return its rows as dictionaries of plain values.

    Args:
        connection: An open connection.
        sql: The query.
        parameters: Values for the ``?`` placeholders.

    Returns:
        One dictionary per row, keyed by column name.
    """
    cursor = connection.execute(sql, list(parameters))
    names = [column[0] for column in cursor.description]
    return [dict(zip(names, map(plain, row), strict=True)) for row in cursor.fetchall()]


def check_metrics(metrics: Sequence[str], allowed: Sequence[str]) -> None:
    """Make sure every requested metric is a known column.

    Metric names end up inside SQL text, so only names from a fixed list are
    accepted.

    Raises:
        UnknownMetricError: If a name is not on the list.
    """
    unknown = sorted(set(metrics) - set(allowed))
    if unknown:
        msg = f"unknown metrics: {', '.join(unknown)}"
        raise UnknownMetricError(msg)
