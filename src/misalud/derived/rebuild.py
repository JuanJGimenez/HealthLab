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
    except BaseException:
        connection.execute("ROLLBACK")
        raise
    connection.execute("COMMIT")
    return DerivedCounts(nights=nights, days=days)
