"""Shared pieces of the query layer: the period filter and plain-data results.

Every query returns plain Python data (lists and dictionaries of text, numbers,
booleans and ``None``) so the window can pass it to the screens as it is.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date, datetime
from typing import Any, Literal

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

    def condition(self, column: str) -> tuple[str, list[object]]:
        """Return the SQL condition that keeps the rows of this period.

        Args:
            column: Name of the date column to filter.

        Returns:
            The condition text and its parameters, in order.
        """
        parts: list[str] = ["TRUE"]
        parameters: list[object] = []
        if self.start is not None:
            parts.append(f"{column} >= ?")
            parameters.append(self.start)
        if self.end is not None:
            parts.append(f"{column} <= ?")
            parameters.append(self.end)
        return " AND ".join(parts), parameters


NightKind = Literal["all", "weekend", "weekdays"]


@dataclass(frozen=True, slots=True)
class NightScope(Period):
    """The nights a screen is looking at: a period, a kind of night and a tag.

    Attributes:
        nights: ``weekend`` keeps Friday and Saturday nights, ``weekdays`` keeps
            Sunday to Thursday nights, ``all`` keeps every night.
        tag_id: A tag to filter by, or ``None`` for no tag filter.
        tagged: With a tag, True keeps the nights whose date carries it and
            False keeps the nights whose date does not.
    """

    nights: NightKind = "all"
    tag_id: int | None = None
    tagged: bool = True

    def condition(self, column: str) -> tuple[str, list[object]]:
        """Return the SQL condition for the period, the kind of night and the tag."""
        text, parameters = Period.condition(self, column)
        if self.nights == "weekend":
            text += " AND is_weekend_night"
        elif self.nights == "weekdays":
            text += " AND NOT is_weekend_night"
        if self.tag_id is not None:
            membership = "IN" if self.tagged else "NOT IN"
            text += f" AND {column} {membership} (SELECT day FROM annotation WHERE tag_id = ?)"
            parameters.append(self.tag_id)
        return text, parameters


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
