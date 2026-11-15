"""Recompute every calculated table after an import."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final

from misalud.derived.day import rebuild_day
from misalud.derived.night import rebuild_night
from misalud.storage.database import Connection

EXERCISE_LABEL_SQL: Final = """
CREATE OR REPLACE VIEW exercise_label AS
SELECT e.samsung_id,
    coalesce(custom.name, standard.name, 'type ' || CAST(e.type_code AS VARCHAR)) AS label
FROM exercise e
LEFT JOIN exercise_custom_type custom USING (custom_id)
LEFT JOIN exercise_type_code standard ON standard.code = e.type_code
"""
"""Name of each exercise session.

The user's own name for a custom type comes first, then the name of a standard
code, then the bare code for a type MiSalud has not seen before.
"""


DERIVED_VERSION: Final = 2
"""Version of the way ``night`` and ``day`` are calculated.

Raise it whenever a column or a rule of the calculated tables changes: a database
built by an older MiSalud is then recalculated the first time it is opened.
"""


@dataclass(frozen=True, slots=True)
class DerivedCounts:
    """Size of the calculated tables after a rebuild.

    Attributes:
        nights: Rows in ``night``.
        days: Rows in ``day``.
    """

    nights: int
    days: int


def rebuild_derived(connection: Connection) -> DerivedCounts:
    """Recompute ``night`` and ``day`` in full, in one transaction.

    The calculated tables hold nothing of their own: dropping and rebuilding
    them loses no data, and doing it after every import keeps them in step with
    the detail tables.

    Args:
        connection: An open connection.

    Returns:
        The number of nights and days.
    """
    connection.execute("BEGIN")
    try:
        connection.execute(EXERCISE_LABEL_SQL)
        nights = rebuild_night(connection)
        days = rebuild_day(connection)
        connection.execute(
            "CREATE OR REPLACE TABLE derived_version AS SELECT ? AS version", [DERIVED_VERSION]
        )
    except BaseException:
        connection.execute("ROLLBACK")
        raise
    connection.execute("COMMIT")
    return DerivedCounts(nights=nights, days=days)


def ensure_derived(connection: Connection) -> bool:
    """Recompute the calculated tables if they are missing or out of date.

    Args:
        connection: An open connection.

    Returns:
        True when the tables had to be recomputed.
    """
    exists = connection.execute(
        "SELECT count(*) FROM information_schema.tables WHERE table_name = 'derived_version'"
    ).fetchall()
    if exists[0][0]:
        stored = connection.execute("SELECT max(version) FROM derived_version").fetchall()
        if stored[0][0] == DERIVED_VERSION:
            return False
    rebuild_derived(connection)
    return True
