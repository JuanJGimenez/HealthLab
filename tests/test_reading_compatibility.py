"""Tests for the comparison between an export and the contracts."""

from __future__ import annotations

import dataclasses
from pathlib import Path

import pandas as pd
import pytest

from healthlab.reading.compatibility import (
    Finding,
    Severity,
    ValueKind,
    compare_with_contracts,
    kind_of_dtype,
    kind_of_values,
)
from healthlab.reading.contracts import ColumnContract, TableContract, load_contracts
from healthlab.reading.tables import short_name
from tests.support import synthetic_export as synth
from tests.support.synthetic_export import SyntheticExport


def synthetic_contracts() -> dict[str, TableContract]:
    """Return the real contracts cut down to the tables and columns the synthetic export has."""
    real = load_contracts()
    result = {}
    for name, spec in synth.TABLES.items():
        columns = {short_name(column) for column in spec.header}
        kept = {key: value for key, value in real[name].columns.items() if key in columns}
        result[name] = dataclasses.replace(real[name], columns=kept)
    return result


def edit_lines(path: Path, line: int, old: str, new: str) -> None:
    """Replace ``old`` with ``new`` on one line of a table file (0 = metadata, 1 = header)."""
    lines = path.read_text(encoding="utf-8-sig").split("\n")
    assert old in lines[line]
    lines[line] = lines[line].replace(old, new)
    path.write_text("\n".join(lines), encoding="utf-8-sig")


def codes(findings: tuple[Finding, ...]) -> list[tuple[str, str, str, str]]:
    """Return findings as plain tuples, to compare them in one assertion."""
    return [(f.table, f.severity.value, f.code, f.detail) for f in findings]


def test_an_export_that_matches_its_contracts_has_no_findings(export: SyntheticExport) -> None:
    report = compare_with_contracts(export.root, synthetic_contracts())
    assert report.findings == ()
    assert report.is_compatible
    assert report.blocked_tables() == frozenset()
    assert report.app_versions == (synth.APP_VERSION,)
    assert report.tables_in_export == len(synth.TABLES)


def test_a_missing_used_table_blocks_that_table(export: SyntheticExport) -> None:
    export.csv_path("sleep_stage").unlink()
    report = compare_with_contracts(export.root, synthetic_contracts())
    assert codes(report.findings) == [("sleep_stage", "error", "table_missing", "")]
    assert not report.is_compatible
    assert report.blocked_tables() == frozenset({"sleep_stage"})


def test_a_missing_unused_table_is_only_information(export: SyntheticExport) -> None:
    contracts = synthetic_contracts()
    contracts["badge"] = dataclasses.replace(contracts["sleep"], name="badge", feeds=())
    report = compare_with_contracts(export.root, contracts)
    assert codes(report.findings) == [("badge", "info", "table_missing", "")]
    assert report.is_compatible


def test_a_table_without_contract_is_a_warning(export: SyntheticExport) -> None:
    new_table = export.root / f"com.samsung.shealth.brand_new.{export.stamp}.csv"
    new_table.write_text("com.samsung.shealth.brand_new,7013005,1\ndatauuid\nx,\n", "utf-8-sig")
    report = compare_with_contracts(export.root, synthetic_contracts())
    assert codes(report.findings) == [("brand_new", "warning", "table_unknown", "")]
    assert report.is_compatible
    assert report.tables_in_export == len(synth.TABLES) + 1


def test_a_schema_version_change_is_reported_with_both_versions(export: SyntheticExport) -> None:
    edit_lines(export.csv_path("sleep"), 0, ",12", ",13")
    report = compare_with_contracts(export.root, synthetic_contracts())
    assert codes(report.findings) == [("sleep", "warning", "schema_version_changed", "12 -> 13")]


def test_a_new_column_is_a_warning(export: SyntheticExport) -> None:
    path = export.csv_path("sleep_snoring")
    lines = path.read_text(encoding="utf-8-sig").split("\n")
    lines[1] += ",loudness"
    lines[2:] = [line + "7," if line else line for line in lines[2:]]
    path.write_text("\n".join(lines), encoding="utf-8-sig")
    report = compare_with_contracts(export.root, synthetic_contracts())
    assert codes(report.findings) == [("sleep_snoring", "warning", "column_unknown", "loudness")]


def test_a_missing_key_column_blocks_and_another_missing_column_warns(
    export: SyntheticExport,
) -> None:
    edit_lines(export.csv_path("sleep_stage"), 1, "datauuid", "record_id")
    edit_lines(export.csv_path("sleep_snoring"), 1, "duration", "length")
    report = compare_with_contracts(export.root, synthetic_contracts())
    assert codes(report.findings) == [
        ("sleep_snoring", "warning", "column_missing", "duration"),
        ("sleep_snoring", "warning", "column_unknown", "length"),
        ("sleep_stage", "error", "column_missing", "datauuid"),
        ("sleep_stage", "warning", "column_unknown", "record_id"),
    ]
    assert report.blocked_tables() == frozenset({"sleep_stage"})


def test_a_number_column_that_turns_into_text_blocks_the_table(export: SyntheticExport) -> None:
    path = export.csv_path("sleep_stage")
    text = path.read_text(encoding="utf-8-sig").replace(",40002,", ",light,")
    path.write_text(text, encoding="utf-8-sig")
    report = compare_with_contracts(export.root, synthetic_contracts())
    assert codes(report.findings) == [("sleep_stage", "error", "column_kind_changed", "stage")]


def test_a_column_that_was_empty_in_the_reference_export_is_not_typed(
    export: SyntheticExport,
) -> None:
    contracts = synthetic_contracts()
    columns = dict(contracts["sleep_stage"].columns)
    columns["sleep_id"] = ColumnContract("sleep_id", "float64", 0.0)
    contracts["sleep_stage"] = dataclasses.replace(contracts["sleep_stage"], columns=columns)
    assert compare_with_contracts(export.root, contracts).findings == ()


def test_the_synthetic_export_agrees_with_the_real_contracts(export: SyntheticExport) -> None:
    report = compare_with_contracts(export.root)
    found = {finding.code for finding in report.findings}
    assert found <= {"table_missing", "column_missing"}
    real = load_contracts()
    absent_used = {name for name, contract in real.items() if contract.is_used} - set(synth.TABLES)
    assert report.blocked_tables() == absent_used


@pytest.mark.parametrize(
    ("dtype", "kind"),
    [
        ("int64", ValueKind.NUMBER),
        ("float64", ValueKind.NUMBER),
        ("object", ValueKind.TEXT),
        ("bool", ValueKind.TEXT),
    ],
)
def test_kind_of_a_recorded_dtype(dtype: str, kind: ValueKind) -> None:
    assert kind_of_dtype(dtype) is kind


@pytest.mark.parametrize(
    ("values", "kind"),
    [
        (["1", "2.5", "-3"], ValueKind.NUMBER),
        (["1", None, "2"], ValueKind.NUMBER),
        (["1", "abc"], ValueKind.TEXT),
        (["2026-01-01 00:00:00.000"], ValueKind.TEXT),
        ([None, None], ValueKind.EMPTY),
        ([], ValueKind.EMPTY),
    ],
)
def test_kind_of_the_values_of_a_column(values: list[str | None], kind: ValueKind) -> None:
    assert kind_of_values(pd.Series(values, dtype="string")) is kind


def test_findings_can_be_filtered_by_severity(export: SyntheticExport) -> None:
    export.csv_path("sleep_stage").unlink()
    edit_lines(export.csv_path("sleep"), 0, ",12", ",13")
    report = compare_with_contracts(export.root, synthetic_contracts())
    assert [f.code for f in report.by_severity(Severity.ERROR)] == ["table_missing"]
    assert [f.code for f in report.by_severity(Severity.WARNING)] == ["schema_version_changed"]
    assert report.by_severity(Severity.INFO) == ()
