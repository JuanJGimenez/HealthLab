"""Tests for opening an export from a folder or a zip archive."""

from __future__ import annotations

import zipfile
from pathlib import Path

import pytest

from healthlab.reading.archive import extract_archive, is_export_folder, locate_export, open_export
from healthlab.reading.errors import ExportNotFoundError, UnsafeArchiveError
from tests.support.synthetic_export import SyntheticExport


def test_the_export_folder_itself_is_recognised(export: SyntheticExport) -> None:
    assert is_export_folder(export.root)
    assert not is_export_folder(export.root / "jsons")
    assert not is_export_folder(export.root / "missing")


def test_a_parent_folder_leads_to_the_export(export: SyntheticExport) -> None:
    assert locate_export(export.root) == export.root
    assert locate_export(export.root.parent) == export.root
    assert locate_export(export.root.parent.parent) == export.root


def test_the_shallowest_export_wins(export: SyntheticExport, tmp_path: Path) -> None:
    nested = export.root / "jsons" / "old_copy"
    nested.mkdir(parents=True)
    (nested / "com.samsung.shealth.sleep.20200101000000.csv").write_text("x", "utf-8")
    assert locate_export(export.root.parent) == export.root


def test_a_folder_without_tables_is_not_an_export(tmp_path: Path) -> None:
    (tmp_path / "notes").mkdir()
    (tmp_path / "notes" / "readme.txt").write_text("x", "utf-8")
    with pytest.raises(ExportNotFoundError, match="no Samsung Health export"):
        locate_export(tmp_path)


def test_a_folder_is_used_in_place(export: SyntheticExport, tmp_path: Path) -> None:
    workdir = tmp_path / "work"
    assert open_export(export.root.parent, workdir) == export.root
    assert not workdir.exists()


def test_a_zip_is_extracted_into_the_work_folder(export_zip: Path, tmp_path: Path) -> None:
    workdir = tmp_path / "work"
    root = open_export(export_zip, workdir)
    assert workdir in root.parents
    assert is_export_folder(root)
    assert (root / "jsons").is_dir()


def test_a_missing_source_is_reported(tmp_path: Path) -> None:
    with pytest.raises(ExportNotFoundError, match="does not exist"):
        open_export(tmp_path / "nothing.zip", tmp_path / "work")


def test_a_file_that_is_not_a_zip_is_rejected(tmp_path: Path) -> None:
    fake = tmp_path / "export.zip"
    fake.write_text("not a zip", "utf-8")
    with pytest.raises(ExportNotFoundError, match="not a zip archive"):
        open_export(fake, tmp_path / "work")


def test_a_zip_without_an_export_is_rejected(tmp_path: Path) -> None:
    archive = tmp_path / "photos.zip"
    with zipfile.ZipFile(archive, "w") as bundle:
        bundle.writestr("holiday/picture.txt", "x")
    with pytest.raises(ExportNotFoundError, match="no Samsung Health export"):
        open_export(archive, tmp_path / "work")


def test_an_archive_entry_cannot_escape_the_target(tmp_path: Path) -> None:
    archive = tmp_path / "evil.zip"
    with zipfile.ZipFile(archive, "w") as bundle:
        bundle.writestr("inside.txt", "ok")
        bundle.writestr("../outside.txt", "bad")
    target = tmp_path / "work"
    with pytest.raises(UnsafeArchiveError, match="escapes"):
        extract_archive(archive, target)
    assert not target.exists()
    assert not (tmp_path / "outside.txt").exists()


def test_a_file_is_not_an_export_folder(export: SyntheticExport) -> None:
    with pytest.raises(ExportNotFoundError, match="no Samsung Health export"):
        locate_export(export.csv_path("sleep"))
