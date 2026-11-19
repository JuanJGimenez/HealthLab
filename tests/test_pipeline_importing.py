"""Tests for an import run from start to finish."""

from __future__ import annotations

import zipfile
from datetime import datetime, timedelta
from pathlib import Path

import pytest

from healthlab.config import Paths
from healthlab.pipeline.importing import confirm_import, prepare_import
from healthlab.reading.errors import ExportNotFoundError
from healthlab.storage.backup import list_backups
from healthlab.storage.database import open_database
from tests.support.synthetic_export import SyntheticExport, build_export

NOW = datetime(2026, 2, 1, 9, 0, 0)


def zipped(export: SyntheticExport, target: Path) -> Path:
    """Zip a synthetic export the way Samsung Health does."""
    with zipfile.ZipFile(target, "w") as bundle:
        for path in sorted(export.root.rglob("*")):
            if path.is_file():
                bundle.write(path, path.relative_to(export.root.parent))
    return target


def count(paths: Paths, sql: str) -> int:
    """Run a counting query against the app database."""
    with open_database(paths.database) as connection:
        return int(connection.execute(sql).fetchall()[0][0])


@pytest.fixture
def paths(tmp_path: Path) -> Paths:
    """An app folder with nothing in it yet."""
    return Paths(tmp_path / "app")


def run(tmp_path: Path, paths: Paths, days: int, moment: datetime, tag: str) -> Path:
    """Import a synthetic export of ``days`` days and return the archive used."""
    export = build_export(tmp_path / f"export_{tag}", n_days=days)
    archive = zipped(export, tmp_path / f"samsunghealth_{tag}.zip")
    prepared = prepare_import(archive, paths, tmp_path / f"work_{tag}")
    confirm_import(prepared, paths, now=moment)
    return archive


def test_preparing_an_import_shows_the_preview_and_stores_no_record(
    tmp_path: Path, paths: Paths, export_zip: Path
) -> None:
    steps: list[str] = []
    prepared = prepare_import(export_zip, paths, tmp_path / "work", steps.append)
    assert steps == ["opening", "checking", "transforming", "comparing"]
    assert prepared.info.file_name == "export.zip"
    assert prepared.archive == export_zip
    assert prepared.plan.total("new") > 0
    assert prepared.plan.total("updated") == 0
    assert "sleep_session" in prepared.transformed.tables
    assert not prepared.compatibility.is_compatible
    assert "hrv" in prepared.transformed.failures
    assert count(paths, "SELECT count(*) FROM sleep_session") == 0
    assert count(paths, "SELECT count(*) FROM import_log") == 0
    assert list_backups(paths.backups_dir) == []


def test_the_first_confirmed_import_fills_the_database_without_a_backup(
    tmp_path: Path, paths: Paths, export_zip: Path
) -> None:
    prepared = prepare_import(export_zip, paths, tmp_path / "work")
    result = confirm_import(prepared, paths, now=NOW)
    assert result.backup is None
    assert result.summary.import_id == 1
    assert result.summary.plan == prepared.plan
    assert (result.derived.nights, result.derived.days) == (3, 4)
    assert count(paths, "SELECT count(*) FROM night") == 3
    assert count(paths, "SELECT count(*) FROM sleep_session") == 4
    assert count(paths, "SELECT count(*) FROM import_failure") == len(prepared.transformed.failures)
    assert count(paths, "SELECT count(*) FROM validation_issue") == 1
    assert (paths.exports_dir / "export.zip").is_file()


def test_a_later_import_backs_up_first_and_keeps_what_the_design_says(
    tmp_path: Path, paths: Paths
) -> None:
    archives = [
        run(tmp_path, paths, days, NOW + timedelta(days=index), f"2026010{days}")
        for index, days in enumerate((3, 4, 5, 6))
    ]
    assert count(paths, "SELECT count(*) FROM import_log") == 4
    assert count(paths, "SELECT count(*) FROM steps_day") == 6
    assert count(paths, "SELECT count(*) FROM record_history WHERE table_name = 'steps_day'") == 3
    backups = list_backups(paths.backups_dir)
    assert [path.name for path in backups] == [
        "salud_20260203_090000.duckdb",
        "salud_20260204_090000.duckdb",
    ]
    with open_database(backups[-1]) as before_last:
        assert before_last.execute("SELECT count(*) FROM steps_day").fetchall() == [(5,)]
    kept = sorted(path.name for path in paths.exports_dir.iterdir())
    assert kept == [archives[2].name, archives[3].name]


def test_an_export_folder_is_imported_without_filing_an_archive(
    tmp_path: Path, paths: Paths, export: SyntheticExport
) -> None:
    prepared = prepare_import(export.root, paths, tmp_path / "work")
    assert prepared.archive is None
    confirm_import(prepared, paths, now=NOW)
    assert count(paths, "SELECT count(*) FROM sleep_session") == 4
    assert list(paths.exports_dir.iterdir()) == []


def test_something_that_is_not_an_export_is_refused_before_touching_the_database(
    tmp_path: Path, paths: Paths
) -> None:
    empty = tmp_path / "empty"
    empty.mkdir()
    with pytest.raises(ExportNotFoundError):
        prepare_import(empty, paths, tmp_path / "work")
    assert not paths.database.exists()
