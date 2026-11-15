"""Tests for reading the detail files referenced from table cells."""

from __future__ import annotations

import pytest

from misalud.reading.details import detail_path, read_detail
from misalud.reading.errors import DetailFileError
from misalud.reading.tables import list_tables, read_table
from tests.support.synthetic_export import SyntheticExport


def test_a_detail_file_is_found_from_the_cell_value(export: SyntheticExport) -> None:
    table = list_tables(export.root)["tracker.oxygen_saturation"]
    name = read_table(table)["binning"].dropna().tolist()[0]
    assert detail_path(export.root, table, name) == export.json_path(table.name, name)
    bins = read_detail(export.root, table, name)
    assert len(bins) == 45
    assert {"spo2", "spo2_min", "spo2_max", "start_time", "end_time"} <= set(bins[0])


def test_every_referenced_detail_file_can_be_read(export: SyntheticExport) -> None:
    tables = list_tables(export.root)
    for name, column in (
        ("tracker.heart_rate", "binning_data"),
        ("step_daily_trend", "binning_data"),
    ):
        for file_name in read_table(tables[name])[column].dropna():
            assert isinstance(read_detail(export.root, tables[name], file_name), list)


def test_a_missing_detail_file_is_reported(export: SyntheticExport) -> None:
    table = list_tables(export.root)["step_daily_trend"]
    with pytest.raises(DetailFileError, match="not found"):
        read_detail(export.root, table, "0000.binning_data.json")


def test_a_corrupt_detail_file_is_reported(export: SyntheticExport) -> None:
    table = list_tables(export.root)["step_daily_trend"]
    name = read_table(table)["binning_data"].tolist()[0]
    export.json_path(table.name, name).write_text("{not json", "utf-8")
    with pytest.raises(DetailFileError, match="not valid JSON"):
        read_detail(export.root, table, name)


@pytest.mark.parametrize("name", ["", "../secret.json", "folder/file.json"])
def test_a_name_that_leaves_its_folder_is_rejected(export: SyntheticExport, name: str) -> None:
    table = list_tables(export.root)["step_daily_trend"]
    with pytest.raises(DetailFileError, match="invalid detail file name"):
        detail_path(export.root, table, name)
