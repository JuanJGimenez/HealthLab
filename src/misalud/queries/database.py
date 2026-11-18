"""Questions about the database itself, for the "Database" panel."""

from __future__ import annotations

from typing import TypedDict, cast

from misalud.queries.common import Record, records
from misalud.storage.database import Connection
from misalud.storage.schema import DETAIL_TABLES


def import_history(connection: Connection) -> list[Record]:
    """Return every import, most recent first, with its totals.

    Returns:
        One record per import with the columns of ``import_log`` plus the sums
        of new, updated, unchanged, kept, superseded and rejected records and
        the number of domains that failed.
    """
    return records(
        connection,
        """SELECT l.*,
            coalesce(t.new_count, 0) AS new_count,
            coalesce(t.updated_count, 0) AS updated_count,
            coalesce(t.unchanged_count, 0) AS unchanged_count,
            coalesce(t.kept_count, 0) AS kept_count,
            coalesce(t.superseded_count, 0) AS superseded_count,
            coalesce(t.rejected_count, 0) AS rejected_count,
            coalesce(f.failed_domains, 0) AS failed_domains
        FROM import_log l
        LEFT JOIN (
            SELECT import_id, sum(new_count) AS new_count, sum(updated_count) AS updated_count,
                sum(unchanged_count) AS unchanged_count, sum(kept_count) AS kept_count,
                sum(superseded_count) AS superseded_count, sum(rejected_count) AS rejected_count
            FROM import_table GROUP BY import_id
        ) t USING (import_id)
        LEFT JOIN (
            SELECT import_id, count(*) AS failed_domains FROM import_failure GROUP BY import_id
        ) f USING (import_id)
        ORDER BY l.import_id DESC""",
    )


def table_sizes(connection: Connection) -> list[Record]:
    """Return the number of records and the dates covered by each detail table.

    Returns:
        One record per table, in name order, with ``table``, ``records``,
        ``first_date`` and ``last_date`` (``None`` for an empty table).
    """
    selects = [
        f"""SELECT '{spec.name}' AS "table", count(*) AS records,
            CAST(min("{spec.time_column}") AS DATE) AS first_date,
            CAST(max("{spec.time_column}") AS DATE) AS last_date
        FROM "{spec.name}\""""
        for spec in DETAIL_TABLES.values()
    ]
    return records(connection, " UNION ALL ".join(selects) + ' ORDER BY "table"')


class DataPeriod(TypedDict):
    """The stretch of time the database covers. Dates are ISO texts."""

    first_night: str | None
    last_night: str | None
    nights: int
    first_day: str | None
    last_day: str | None
    days: int


def data_period(connection: Connection) -> DataPeriod:
    """Return the first and last night and day available, to bound the date filters.

    Returns:
        ``first_night``, ``last_night``, ``nights``, ``first_day``, ``last_day``
        and ``days``; dates are ``None`` while the database is empty.
    """
    row = records(
        connection,
        """SELECT
            (SELECT min(night_date) FROM night) AS first_night,
            (SELECT max(night_date) FROM night) AS last_night,
            (SELECT count(*) FROM night) AS nights,
            (SELECT min(day) FROM day) AS first_day,
            (SELECT max(day) FROM day) AS last_day,
            (SELECT count(*) FROM day) AS days""",
    )[0]
    return cast(DataPeriod, row)


def issue_summary(connection: Connection) -> list[Record]:
    """Summarise what the validations found in the most recent import.

    Returns:
        One record per table, rule and action with ``table``, ``rule``,
        ``action`` (``rejected`` or ``kept``) and ``records``; empty when the
        database has no imports or the last one had no issues.
    """
    return records(
        connection,
        """SELECT table_name AS "table", rule, action, count(*) AS records
        FROM validation_issue
        WHERE import_id = (SELECT max(import_id) FROM import_log)
        GROUP BY ALL ORDER BY action DESC, records DESC, "table", rule""",
    )
