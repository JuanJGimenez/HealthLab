"""Tests for paths, thresholds and validation ranges."""

from __future__ import annotations

import dataclasses
import sys
from pathlib import Path

import pytest

from misalud import config


def test_all_user_data_lives_under_the_data_folder(tmp_path: Path) -> None:
    paths = config.Paths(root=tmp_path)
    assert paths.data_dir == tmp_path / "data"
    for location in (paths.database, paths.backups_dir, paths.exports_dir, paths.logs_dir):
        assert paths.data_dir in location.parents


def test_ensure_creates_folders_and_keeps_existing_content(tmp_path: Path) -> None:
    paths = config.Paths(root=tmp_path)
    paths.ensure()
    marker = paths.backups_dir / "keep.txt"
    marker.write_text("x", encoding="utf-8")
    paths.ensure()
    assert paths.exports_dir.is_dir()
    assert paths.logs_dir.is_dir()
    assert marker.read_text(encoding="utf-8") == "x"
    assert not paths.database.exists()


def test_app_root_honours_the_environment_override(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv(config.HOME_ENV_VAR, str(tmp_path))
    assert config.app_root() == tmp_path.resolve()
    assert config.default_paths().root == tmp_path.resolve()


def test_app_root_is_the_executable_folder_when_packaged(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv(config.HOME_ENV_VAR, raising=False)
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "executable", str(tmp_path / "MiSalud.exe"))
    assert config.app_root() == tmp_path.resolve()


def test_app_root_is_the_project_folder_when_run_from_source(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv(config.HOME_ENV_VAR, raising=False)
    monkeypatch.delattr(sys, "frozen", raising=False)
    assert (config.app_root() / "pyproject.toml").is_file()


def test_thresholds_match_the_design_decisions() -> None:
    thresholds = config.THRESHOLDS
    assert thresholds.night_min_duration_min == 120
    assert thresholds.signal_join_padding_min == 30
    assert thresholds.low_spo2_threshold_pct == 90
    assert thresholds.sustained_low_min == 5
    assert thresholds.spo2_min_recorded_hours == 3.0
    assert thresholds.backups_to_keep == 2
    assert thresholds.exports_to_keep == 2


def test_thresholds_cannot_be_changed_at_runtime() -> None:
    with pytest.raises(dataclasses.FrozenInstanceError):
        config.THRESHOLDS.night_min_duration_min = 60  # type: ignore[misc]


def test_value_range_includes_its_bounds() -> None:
    spo2 = config.VALID_RANGES["spo2_pct"]
    assert spo2.contains(60)
    assert spo2.contains(100)
    assert not spo2.contains(59.9)
    assert not spo2.contains(100.1)


def test_value_range_rejects_inverted_bounds() -> None:
    with pytest.raises(ValueError, match="must not exceed"):
        config.ValueRange(low=10, high=5)


def test_valid_ranges_are_read_only() -> None:
    with pytest.raises(TypeError):
        config.VALID_RANGES["spo2_pct"] = config.ValueRange(0, 1)  # type: ignore[index]
