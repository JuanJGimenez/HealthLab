"""Tests for installing a built folder over the one the user runs.

Building itself needs PyInstaller and a minute, so it is run by hand at each
release; what is tested here is the part that touches a folder with user data.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from release import build
from release.build import BuildError, install


def built_folder(root: Path, mark: str) -> Path:
    """Create a folder shaped like a built app, with ``mark`` in each file."""
    folder = root / "HealthLab"
    (folder / build.INTERNAL_FOLDER / "healthlab").mkdir(parents=True)
    (folder / build.EXECUTABLE).write_text(mark, encoding="utf-8")
    (folder / build.INTERNAL_FOLDER / "healthlab" / "app.js").write_text(mark, encoding="utf-8")
    for name in (build.MANUAL_NAME, build.LICENSE_NAME, build.NOTICES_NAME):
        (folder / name).write_text(mark, encoding="utf-8")
    return folder


def test_a_first_installation_creates_the_folder(tmp_path: Path) -> None:
    source = built_folder(tmp_path / "dist", "v1")
    target = tmp_path / "apps" / "HealthLab"
    assert install(source, target) == list(build.PROGRAM_ITEMS)
    assert (target / build.EXECUTABLE).read_text(encoding="utf-8") == "v1"
    assert not (target / build.DATA_FOLDER).exists()


def test_an_update_replaces_the_program_and_keeps_the_data(tmp_path: Path) -> None:
    target = tmp_path / "apps" / "HealthLab"
    install(built_folder(tmp_path / "old", "v1"), target)
    (target / build.INTERNAL_FOLDER / "left_over.dll").write_text("old", encoding="utf-8")
    data = target / build.DATA_FOLDER
    (data / "backups").mkdir(parents=True)
    (data / "salud.duckdb").write_text("records", encoding="utf-8")
    (data / "backups" / "salud_1.duckdb").write_text("backup", encoding="utf-8")
    (target / "notes.txt").write_text("mine", encoding="utf-8")

    install(built_folder(tmp_path / "new", "v2"), target)

    assert (target / build.EXECUTABLE).read_text(encoding="utf-8") == "v2"
    assert (target / build.INTERNAL_FOLDER / "healthlab" / "app.js").read_text("utf-8") == "v2"
    assert not (target / build.INTERNAL_FOLDER / "left_over.dll").exists()
    assert (data / "salud.duckdb").read_text(encoding="utf-8") == "records"
    assert (data / "backups" / "salud_1.duckdb").read_text(encoding="utf-8") == "backup"
    assert (target / "notes.txt").read_text(encoding="utf-8") == "mine"


def test_a_source_with_data_or_without_program_is_refused(tmp_path: Path) -> None:
    source = built_folder(tmp_path / "dist", "v1")
    with pytest.raises(BuildError, match="different"):
        install(source, source)
    (source / build.DATA_FOLDER).mkdir()
    with pytest.raises(BuildError, match="refusing"):
        install(source, tmp_path / "target")
    (source / build.DATA_FOLDER).rmdir()
    (source / build.EXECUTABLE).unlink()
    with pytest.raises(BuildError, match="missing"):
        install(source, tmp_path / "target")
    assert not (tmp_path / "target").exists()


def test_a_missing_optional_item_is_skipped(tmp_path: Path) -> None:
    source = built_folder(tmp_path / "dist", "v1")
    (source / build.MANUAL_NAME).unlink()
    assert install(source, tmp_path / "target") == [
        build.EXECUTABLE,
        build.INTERNAL_FOLDER,
        build.LICENSE_NAME,
        build.NOTICES_NAME,
    ]


def test_an_update_over_a_folder_from_before_the_rename_leaves_one_program(
    tmp_path: Path,
) -> None:
    target = tmp_path / "MiSalud"
    (target / build.DATA_FOLDER).mkdir(parents=True)
    (target / build.DATA_FOLDER / "salud.duckdb").write_text("records", encoding="utf-8")
    (target / "MiSalud.exe").write_text("old program", encoding="utf-8")
    (target / "MiSalud").mkdir()  # a folder of the user that happens to share the name
    install(built_folder(tmp_path / "dist", "v2"), target)
    assert not (target / "MiSalud.exe").exists()
    assert (target / "MiSalud").is_dir()
    assert (target / build.EXECUTABLE).read_text(encoding="utf-8") == "v2"
    assert (target / build.DATA_FOLDER / "salud.duckdb").read_text(encoding="utf-8") == "records"
