"""Tests for the object that gives access to an opened export."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pytest

from misalud.reading.errors import DetailFileError, TableMissingError
from misalud.reading.source import ExportSource
from tests.support import synthetic_export as synth
from tests.support.synthetic_export import SyntheticExport


def test_a_folder_opens_with_every_table(export: SyntheticExport) -> None:
    source = ExportSource.from_folder(export.root)
    assert set(source.tables) == set(synth.TABLES)
    assert source.has("sleep")
    assert not source.has("badge")


def test_the_export_moment_comes_from_the_file_names(export: SyntheticExport) -> None:
    source = ExportSource.from_folder(export.root)
    assert source.exported_at == datetime.strptime(export.stamp, "%Y%m%d%H%M%S")


def test_an_export_without_tables_has_no_export_moment(tmp_path: Path) -> None:
    with pytest.raises(TableMissingError, match="no tables"):
        _ = ExportSource(root=tmp_path, tables={}).exported_at


def test_a_table_is_read_as_text(export: SyntheticExport) -> None:
    frame = ExportSource.from_folder(export.root).read("sleep")
    assert len(frame) == 4
    assert all(str(dtype) == "string" for dtype in frame.dtypes)


def test_a_detail_file_is_loaded_from_the_cell_that_names_it(export: SyntheticExport) -> None:
    source = ExportSource.from_folder(export.root)
    file_name = source.read("tracker.heart_rate")["binning_data"].iloc[0]
    assert len(source.detail("tracker.heart_rate", file_name)) == 60


def test_asking_for_an_absent_table_fails_clearly(export: SyntheticExport) -> None:
    source = ExportSource.from_folder(export.root)
    with pytest.raises(TableMissingError, match="badge"):
        source.read("badge")
    with pytest.raises(TableMissingError, match="badge"):
        source.detail("badge", "x.json")


def test_an_absent_detail_file_fails_clearly(export: SyntheticExport) -> None:
    source = ExportSource.from_folder(export.root)
    with pytest.raises(DetailFileError):
        source.detail("tracker.heart_rate", "0000.binning_data.json")
