"""Open the database, creating or upgrading its schema when needed.

The database stores its schema version. Each version is produced by one migration
function; opening a database runs the migrations it has not seen yet, so a user
who updates MiSalud keeps their data.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from datetime import datetime
from pathlib import Path
from typing import Final

import duckdb

from misalud.storage.errors import SchemaVersionError
from misalud.storage.schema import (
    CONTROL_STATEMENTS,
    DETAIL_TABLES,
    EXERCISE_TYPE_CODES,
    OWN_STATEMENTS,
    SLEEP_STAGE_CODES,
)

Connection = duckdb.DuckDBPyConnection
Migration = Callable[[Connection], None]


def _create_version_1(connection: Connection) -> None:
    """Create every table of the first schema and fill the code tables."""
    for statement in (*CONTROL_STATEMENTS, *OWN_STATEMENTS):
        connection.execute(statement)
    for spec in DETAIL_TABLES.values():
        connection.execute(spec.create_statement())
    connection.executemany("INSERT INTO sleep_stage_code VALUES (?, ?, ?)", SLEEP_STAGE_CODES)
    connection.executemany("INSERT INTO exercise_type_code VALUES (?, ?, ?)", EXERCISE_TYPE_CODES)


MIGRATIONS: Final[tuple[Migration, ...]] = (_create_version_1,)
"""Migration ``i`` takes the database from version ``i`` to version ``i + 1``."""


def schema_version(connection: Connection) -> int:
    """Return the schema version of a database; 0 when it has no schema yet.

    Args:
        connection: An open connection.

    Returns:
        The highest version recorded, or 0 for an empty database.
    """
    exists = connection.execute(
        "SELECT count(*) FROM information_schema.tables WHERE table_name = 'schema_version'"
    ).fetchall()
    if not exists[0][0]:
        return 0
    rows = connection.execute("SELECT coalesce(max(version), 0) FROM schema_version").fetchall()
    return int(rows[0][0])


def open_database(
    path: Path | None,
    *,
    now: datetime | None = None,
    migrations: Sequence[Migration] = MIGRATIONS,
) -> Connection:
    """Open the database, bringing its schema up to date first.

    A new database gets the whole schema. An older one gets the migrations it
    lacks, all in one transaction: either every pending migration applies or
    the database stays as it was.

    Args:
        path: Database file. ``None`` opens a database in memory, for tests.
        now: Moment recorded for each migration applied. Defaults to the clock.
        migrations: Migrations to know about. Defaults to the real ones.

    Returns:
        An open connection.

    Raises:
        SchemaVersionError: If the database was made by a newer MiSalud.
    """
    connection = duckdb.connect(":memory:" if path is None else str(path))
    current = schema_version(connection)
    if current > len(migrations):
        connection.close()
        msg = (
            f"the database has schema version {current}; this MiSalud knows up to {len(migrations)}"
        )
        raise SchemaVersionError(msg)
    if current < len(migrations):
        applied_at = now or datetime.now()
        connection.execute("BEGIN")
        try:
            for version, migrate in enumerate(migrations[current:], start=current + 1):
                migrate(connection)
                connection.execute(
                    "INSERT INTO schema_version VALUES (?, ?)", [version, applied_at]
                )
        except BaseException:
            connection.execute("ROLLBACK")
            connection.close()
            raise
        connection.execute("COMMIT")
    return connection
