"""Tests for keeping the original export archives."""

from __future__ import annotations

from collections.abc import Iterator
from datetime import date, datetime
from pathlib import Path

import pytest

from misalud.storage.database import Connection, open_database
from misalud.storage.exports import archive_export, prune_exports


@pytest.fixture
def connection() -> Iterator[Connection]:
    """An empty database in memory."""
    with open_database(None) as opened:
        yield opened


def log_import(connection: Connection, name: str, exported: datetime, first: date | None) -> None:
    """Record an import the way the merge does."""
    connection.execute(
        """INSERT INTO import_log
        SELECT coalesce(max(import_id), 0) + 1, ?, ?, NULL, ?, ?, ? FROM import_log""",
        [exported, name, exported, first, exported.date()],
    )


def store(folder: Path, *names: str) -> None:
    """Create empty archives in the exports folder."""
    folder.mkdir(exist_ok=True)
    for name in names:
        (folder / name).write_bytes(b"zip")


def test_an_imported_archive_is_copied_into_the_exports_folder(tmp_path: Path) -> None:
    archive = tmp_path / "downloads" / "samsunghealth_20260301.zip"
    archive.parent.mkdir()
    archive.write_bytes(b"first")
    stored = archive_export(archive, tmp_path / "exports")
    assert stored == tmp_path / "exports" / "samsunghealth_20260301.zip"
    assert stored.read_bytes() == b"first"
    assert archive.is_file()
    archive.write_bytes(b"again")
    assert archive_export(archive, tmp_path / "exports").read_bytes() == b"again"
    assert archive_export(stored, tmp_path / "exports") == stored
    assert stored.read_bytes() == b"again"


def test_older_archives_are_deleted_when_the_kept_ones_cover_their_history(
    tmp_path: Path, connection: Connection
) -> None:
    folder = tmp_path / "exports"
    store(folder, "jan.zip", "feb.zip", "mar.zip", "stray.zip")
    start = date(2025, 3, 30)
    log_import(connection, "jan.zip", datetime(2026, 1, 1), start)
    log_import(connection, "feb.zip", datetime(2026, 2, 1), start)
    log_import(connection, "mar.zip", datetime(2026, 3, 1), start)
    log_import(connection, "gone.zip", datetime(2026, 3, 15), start)
    assert prune_exports(connection, folder) == [folder / "jan.zip"]
    assert sorted(path.name for path in folder.iterdir()) == ["feb.zip", "mar.zip", "stray.zip"]


def test_an_archive_that_reaches_further_back_is_never_deleted(
    tmp_path: Path, connection: Connection
) -> None:
    folder = tmp_path / "exports"
    store(folder, "full.zip", "unknown.zip", "trimmed1.zip", "trimmed2.zip")
    log_import(connection, "full.zip", datetime(2026, 1, 1), date(2025, 3, 30))
    log_import(connection, "unknown.zip", datetime(2026, 1, 15), None)
    log_import(connection, "trimmed1.zip", datetime(2026, 2, 1), date(2025, 9, 1))
    log_import(connection, "trimmed2.zip", datetime(2026, 3, 1), date(2025, 9, 1))
    assert prune_exports(connection, folder) == []
    assert len(list(folder.iterdir())) == 4


def test_nothing_is_deleted_when_the_kept_archives_have_no_known_period(
    tmp_path: Path, connection: Connection
) -> None:
    folder = tmp_path / "exports"
    store(folder, "a.zip", "b.zip")
    log_import(connection, "a.zip", datetime(2026, 1, 1), date(2025, 3, 30))
    log_import(connection, "b.zip", datetime(2026, 2, 1), None)
    assert prune_exports(connection, folder, keep=1) == []
