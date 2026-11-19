"""Tests for listing and reading the CSV tables of an export."""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from healthlab.reading.errors import TableFormatError
from healthlab.reading.tables import TableFile, list_tables, read_header, read_table, short_name
from tests.support import synthetic_export as synth
from tests.support.synthetic_export import SyntheticExport


def test_short_name_drops_the_prefix() -> None:
    assert short_name("com.samsung.health.sleep.start_time") == "start_time"
    assert short_name("sleep_score") == "sleep_score"


def test_every_table_is_listed_with_its_versions(export: SyntheticExport) -> None:
    tables = list_tables(export.root)
    assert list(tables) == sorted(synth.TABLES)
    for name, table in tables.items():
        spec = synth.TABLES[name]
        assert table.namespace == spec.namespace
        assert table.schema_version == spec.schema_version
        assert table.app_version == synth.APP_VERSION
        assert table.stamp == export.stamp
        assert table.path == export.csv_path(name)
    assert tables["sleep_stage"].full_name == "com.samsung.health.sleep_stage"


def test_other_files_in_the_folder_are_ignored(export: SyntheticExport) -> None:
    (export.root / "notes.csv").write_text("a,b\n1,2\n", "utf-8")
    (export.root / "com.samsung.shealth.sleep.csv").write_text("x", "utf-8")
    assert list(list_tables(export.root)) == sorted(synth.TABLES)


def test_a_table_without_metadata_line_is_rejected(export: SyntheticExport) -> None:
    export.csv_path("sleep").write_text("start_time,end_time\n1,2,\n", "utf-8")
    with pytest.raises(TableFormatError, match="first line"):
        list_tables(export.root)


def test_two_files_for_one_table_are_rejected(export: SyntheticExport) -> None:
    twin = export.root / "com.samsung.health.sleep.20990101000000.csv"
    twin.write_text("com.samsung.health.sleep,1,1\ndatauuid\n", "utf-8")
    with pytest.raises(TableFormatError, match="two files for table sleep"):
        list_tables(export.root)


def test_header_names_come_without_prefix_and_in_file_order(export: SyntheticExport) -> None:
    table = list_tables(export.root)["sleep"]
    assert read_header(table) == [short_name(name) for name in synth.TABLES["sleep"].header]


def test_a_table_is_read_as_text_without_the_trailing_field(export: SyntheticExport) -> None:
    table = list_tables(export.root)["sleep"]
    frame = read_table(table)
    assert list(frame.columns) == read_header(table)
    assert len(frame) == 4
    assert all(str(dtype) == "string" for dtype in frame.dtypes)
    assert frame["sleep_duration"].tolist().count("450") == 3
    assert frame["time_offset"].str.startswith("UTC-").all()


def test_empty_cells_are_missing_values(export: SyntheticExport) -> None:
    frame = read_table(list_tables(export.root)["sleep"])
    assert frame["combined_id"].isna().all()
    assert frame["datauuid"].notna().all()


def test_text_that_looks_like_a_missing_marker_is_kept(tmp_path: Path) -> None:
    path = tmp_path / "com.samsung.shealth.note.20260101000000.csv"
    path.write_text("com.samsung.shealth.note,1,1\nname,value\nNA,null,\n,3,\n", "utf-8-sig")
    frame = read_table(TableFile("note", "shealth", path, "20260101000000", "1", 1))
    assert frame["name"].tolist()[0] == "NA"
    assert frame["value"].tolist() == ["null", "3"]
    assert pd.isna(frame["name"].tolist()[1])


def test_quoted_cells_with_commas_are_one_field(tmp_path: Path) -> None:
    path = tmp_path / "com.samsung.shealth.note.20260101000000.csv"
    path.write_text('com.samsung.shealth.note,1,1\nname,value\n"a,b",1,\n', "utf-8-sig")
    frame = read_table(TableFile("note", "shealth", path, "20260101000000", "1", 1))
    assert frame["name"].tolist() == ["a,b"]


def test_a_table_with_only_a_header_is_empty(tmp_path: Path) -> None:
    path = tmp_path / "com.samsung.shealth.note.20260101000000.csv"
    path.write_text("com.samsung.shealth.note,1,1\nname,value\n", "utf-8-sig")
    frame = read_table(TableFile("note", "shealth", path, "20260101000000", "1", 1))
    assert frame.empty
    assert list(frame.columns) == ["name", "value"]


def test_columns_that_share_a_short_name_are_rejected(tmp_path: Path) -> None:
    path = tmp_path / "com.samsung.shealth.note.20260101000000.csv"
    path.write_text(
        "com.samsung.shealth.note,1,1\ncustom,com.samsung.x.custom\n1,2,\n", "utf-8-sig"
    )
    with pytest.raises(TableFormatError, match="share a short name: custom"):
        read_table(TableFile("note", "shealth", path, "20260101000000", "1", 1))


def test_a_file_without_header_is_rejected(tmp_path: Path) -> None:
    path = tmp_path / "com.samsung.shealth.note.20260101000000.csv"
    path.write_text("com.samsung.shealth.note,1,1\n", "utf-8-sig")
    with pytest.raises(TableFormatError, match="no header line"):
        read_table(TableFile("note", "shealth", path, "20260101000000", "1", 1))


def test_a_row_with_too_many_fields_is_rejected(tmp_path: Path) -> None:
    path = tmp_path / "com.samsung.shealth.note.20260101000000.csv"
    path.write_text("com.samsung.shealth.note,1,1\nname,value\na,1,extra,\n", "utf-8-sig")
    with pytest.raises(TableFormatError):
        read_table(TableFile("note", "shealth", path, "20260101000000", "1", 1))


def test_an_unterminated_quote_is_rejected(tmp_path: Path) -> None:
    path = tmp_path / "com.samsung.shealth.note.20260101000000.csv"
    path.write_text('com.samsung.shealth.note,1,1\nname,value\n"abc,1,\n', "utf-8-sig")
    with pytest.raises(TableFormatError, match="note"):
        read_table(TableFile("note", "shealth", path, "20260101000000", "1", 1))
