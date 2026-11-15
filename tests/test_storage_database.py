"""Tests for opening the database and keeping its schema up to date."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pytest

from misalud.storage.database import MIGRATIONS, Connection, open_database, schema_version
from misalud.storage.errors import SchemaVersionError
from misalud.storage.schema import DETAIL_TABLES

NOW = datetime(2026, 1, 10, 12, 0, 0)


def table_names(connection: Connection) -> set[str]:
    """Return the names of the tables in a database."""
    rows = connection.execute("SELECT table_name FROM information_schema.tables").fetchall()
    return {row[0] for row in rows}


def test_a_new_database_gets_every_table_and_the_codes() -> None:
    with open_database(None, now=NOW) as connection:
        names = table_names(connection)
        assert set(DETAIL_TABLES) <= names
        assert {"import_log", "import_table", "import_failure", "record_history"} <= names
        assert {"validation_issue", "schema_version", "tag", "annotation", "user_profile"} <= names
        assert schema_version(connection) == 1
        assert connection.execute("SELECT * FROM schema_version").fetchall() == [(1, NOW)]
        stages = connection.execute("SELECT * FROM sleep_stage_code ORDER BY code").fetchall()
        assert stages[1] == (40002, "light", True)
        assert len(stages) == 4
        walking = connection.execute(
            "SELECT name FROM exercise_type_code WHERE code = 1001"
        ).fetchall()
        assert walking == [("walking",)]


def test_reopening_a_database_keeps_its_data_and_does_not_migrate_again(tmp_path: Path) -> None:
    path = tmp_path / "salud.duckdb"
    with open_database(path, now=NOW) as connection:
        connection.execute("INSERT INTO tag VALUES (1, 'alcohol', true)")
    with open_database(path) as connection:
        assert connection.execute("SELECT name FROM tag").fetchall() == [("alcohol",)]
        assert connection.execute("SELECT count(*) FROM schema_version").fetchall() == [(1,)]


def test_an_empty_connection_has_schema_version_zero(tmp_path: Path) -> None:
    with open_database(tmp_path / "empty.duckdb", migrations=()) as connection:
        assert schema_version(connection) == 0


def test_a_database_from_a_newer_version_is_refused(tmp_path: Path) -> None:
    path = tmp_path / "salud.duckdb"
    open_database(path).close()
    with pytest.raises(SchemaVersionError, match="schema version 1"):
        open_database(path, migrations=())


def test_an_older_database_gets_only_the_migrations_it_lacks(tmp_path: Path) -> None:
    path = tmp_path / "salud.duckdb"
    with open_database(path) as connection:
        connection.execute("INSERT INTO tag VALUES (1, 'alcohol', true)")

    def add_column(connection: Connection) -> None:
        connection.execute("ALTER TABLE tag ADD COLUMN color VARCHAR")

    with open_database(path, now=NOW, migrations=(*MIGRATIONS, add_column)) as connection:
        assert schema_version(connection) == 2
        assert connection.execute("SELECT name, color FROM tag").fetchall() == [("alcohol", None)]


def test_a_failing_migration_leaves_the_database_as_it_was(tmp_path: Path) -> None:
    path = tmp_path / "salud.duckdb"
    open_database(path).close()

    def add_column(connection: Connection) -> None:
        connection.execute("ALTER TABLE tag ADD COLUMN color VARCHAR")

    def broken(_: Connection) -> None:
        raise RuntimeError("boom")

    with pytest.raises(RuntimeError, match="boom"):
        open_database(path, migrations=(*MIGRATIONS, add_column, broken))
    with open_database(path) as connection:
        assert schema_version(connection) == 1
        columns = connection.execute("SELECT * FROM tag").description
        assert [column[0] for column in columns] == ["tag_id", "name", "is_active"]
