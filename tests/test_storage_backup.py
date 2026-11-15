"""Tests for database backups."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pytest

from misalud.storage.backup import backup_database, list_backups, prune_backups, restore_backup
from misalud.storage.database import open_database
from misalud.storage.errors import StorageError


def make_database(path: Path, tag: str) -> None:
    """Create a database that holds one recognisable row."""
    with open_database(path) as connection:
        connection.execute("INSERT INTO tag (tag_id, name, is_active) VALUES (100, ?, true)", [tag])


def tag_in(path: Path) -> str:
    """Return the recognisable row of a database."""
    with open_database(path) as connection:
        return str(connection.execute("SELECT name FROM tag WHERE tag_id = 100").fetchall()[0][0])


def test_there_is_nothing_to_back_up_before_the_first_import(tmp_path: Path) -> None:
    assert backup_database(tmp_path / "salud.duckdb", tmp_path / "backups") is None
    assert list_backups(tmp_path / "backups") == []


def test_a_backup_is_a_dated_copy_that_opens_on_its_own(tmp_path: Path) -> None:
    database = tmp_path / "salud.duckdb"
    make_database(database, "before")
    backup = backup_database(database, tmp_path / "backups", now=datetime(2026, 4, 2, 9, 5, 7))
    assert backup is not None
    assert backup.name == "salud_20260402_090507.duckdb"
    assert tag_in(backup) == "before"
    assert list_backups(tmp_path / "backups") == [backup]


def test_only_the_most_recent_backups_are_kept(tmp_path: Path) -> None:
    database, folder = tmp_path / "salud.duckdb", tmp_path / "backups"
    make_database(database, "x")
    made = [
        backup_database(database, folder, now=datetime(2026, 4, day, 9, 0, 0)) for day in (3, 1, 2)
    ]
    (folder / "notes.txt").write_text("not a backup")
    deleted = prune_backups(folder)
    assert deleted == [made[1]]
    assert list_backups(folder) == [made[2], made[0]]
    assert prune_backups(folder) == []
    assert (folder / "notes.txt").is_file()
    assert len(prune_backups(folder, keep=0)) == 2


def test_a_backup_can_be_put_back(tmp_path: Path) -> None:
    database = tmp_path / "salud.duckdb"
    make_database(database, "before")
    backup = backup_database(database, tmp_path / "backups")
    assert backup is not None
    database.unlink()
    make_database(database, "after a bad merge")
    leftover = database.with_name("salud.duckdb.wal")
    leftover.write_bytes(b"")
    restore_backup(backup, database)
    assert not leftover.exists()
    assert tag_in(database) == "before"


def test_restoring_a_backup_that_is_gone_fails_clearly(tmp_path: Path) -> None:
    with pytest.raises(StorageError, match=r"backup not found: salud_x\.duckdb"):
        restore_backup(tmp_path / "salud_x.duckdb", tmp_path / "salud.duckdb")
