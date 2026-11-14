"""Tests for the synthetic Samsung Health export used by the other tests.

The generator is test infrastructure, but the merge tests of later stages depend on
it behaving like a real export. These tests pin that behaviour down.
"""

from __future__ import annotations

import csv
import json
import re
from pathlib import Path

import pytest

from misalud.reading.contracts import load_contracts
from tests.support import synthetic_export as synth
from tests.support.synthetic_export import SyntheticExport, build_export

FILE_PATTERN = re.compile(r"^com\.samsung\.(shealth|health)\.(.+)\.(\d{14})\.csv$")


def read_table(export: SyntheticExport, table: str) -> list[dict[str, str]]:
    """Read a synthetic CSV the way the importer will: skip metadata, strip prefixes."""
    with export.csv_path(table).open(encoding="utf-8-sig", newline="") as handle:
        handle.readline()
        reader = csv.reader(handle)
        header = [name.rsplit(".", 1)[-1] for name in next(reader)]
        return [dict(zip(header, row, strict=False)) for row in reader]


@pytest.fixture
def export(tmp_path: Path) -> SyntheticExport:
    """A four-day export: three nights and a partial export day."""
    return build_export(tmp_path, n_days=4)


def test_file_names_follow_the_samsung_pattern(export: SyntheticExport) -> None:
    names = sorted(path.name for path in export.root.glob("*.csv"))
    assert len(names) == len(synth.TABLES)
    for name in names:
        match = FILE_PATTERN.match(name)
        assert match, name
        assert match.group(2) in synth.TABLES
        assert match.group(3) == export.stamp


def test_files_start_with_a_byte_order_mark_and_metadata_line(export: SyntheticExport) -> None:
    for table, spec in synth.TABLES.items():
        raw = export.csv_path(table).read_bytes()
        assert raw.startswith(b"\xef\xbb\xbf"), table
        first_line = raw.decode("utf-8-sig").splitlines()[0]
        assert (
            first_line
            == f"com.samsung.{spec.namespace}.{table},{synth.APP_VERSION},{spec.schema_version}"
        )


def test_data_rows_end_with_a_trailing_comma_and_the_header_does_not(
    export: SyntheticExport,
) -> None:
    lines = export.csv_path("sleep").read_text(encoding="utf-8-sig").splitlines()
    assert not lines[1].endswith(",")
    assert all(line.endswith(",") for line in lines[2:])
    assert len(lines) > 2


def test_tables_agree_with_the_real_contracts(export: SyntheticExport) -> None:
    contracts = load_contracts()
    for table, spec in synth.TABLES.items():
        contract = contracts[table]
        assert spec.schema_version == contract.schema_version, table
        short_names = [name.rsplit(".", 1)[-1] for name in spec.header]
        assert len(short_names) == len(set(short_names)), table
        unknown = set(short_names) - set(contract.columns)
        assert unknown == set(), f"{table}: {unknown}"
        assert contract.key in short_names, table


def test_headers_use_the_real_mix_of_bare_and_prefixed_names() -> None:
    sleep_header = synth.TABLES["sleep"].header
    assert "sleep_score" in sleep_header
    assert "com.samsung.health.sleep.start_time" in sleep_header
    assert all("." not in name for name in synth.TABLES["sleep_snoring"].header)


def test_sessions_are_three_nights_and_one_nap(export: SyntheticExport) -> None:
    durations = sorted(int(row["sleep_duration"]) for row in read_table(export, "sleep"))
    assert durations == [synth.NAP_MINUTES, *[synth.NIGHT_MINUTES] * 3]


def test_nights_start_at_2330_local_time_with_their_own_offset(export: SyntheticExport) -> None:
    nights = [r for r in read_table(export, "sleep") if int(r["sleep_duration"]) > 120]
    by_offset = {row["time_offset"]: row["start_time"] for row in nights}
    assert set(by_offset) == {"UTC-0300", "UTC-0400"}
    assert by_offset["UTC-0400"] == "2026-01-03 03:30:00.000"
    assert [r["start_time"] for r in nights if r["time_offset"] == "UTC-0300"] == [
        "2026-01-02 02:30:00.000",
        "2026-01-04 02:30:00.000",
    ]


def test_stages_point_to_their_session_and_fill_it(export: SyntheticExport) -> None:
    sessions = {row["datauuid"]: int(row["sleep_duration"]) for row in read_table(export, "sleep")}
    stages = read_table(export, "sleep_stage")
    assert {row["sleep_id"] for row in stages} == set(sessions)
    codes = {int(row["stage"]) for row in stages}
    assert codes == {synth.STAGE_AWAKE, synth.STAGE_LIGHT, synth.STAGE_DEEP, synth.STAGE_REM}
    night_id = synth.record_id("sleep", "night:0")
    assert len([row for row in stages if row["sleep_id"] == night_id]) == len(synth.NIGHT_STAGES)


def test_light_and_rem_totals_match_the_stage_minutes(export: SyntheticExport) -> None:
    night = next(r for r in read_table(export, "sleep") if int(r["sleep_duration"]) > 120)
    light = sum(minutes for code, minutes in synth.NIGHT_STAGES if code == synth.STAGE_LIGHT)
    rem = sum(minutes for code, minutes in synth.NIGHT_STAGES if code == synth.STAGE_REM)
    assert int(night["total_light_duration"]) == light
    assert int(night["total_rem_duration"]) == rem


def test_oxygen_has_one_record_per_night_plus_a_spot_measurement(export: SyntheticExport) -> None:
    rows = read_table(export, "tracker.oxygen_saturation")
    assert sorted(row["tag_id"] for row in rows) == ["31000", "31301", "31301", "31301"]
    low = [row for row in rows if row["tag_id"] == "31301" and float(row["low_duration"]) > 0]
    assert len(low) == 1
    assert low[0]["datauuid"] == synth.record_id(
        "tracker.oxygen_saturation", f"night:{synth.LOW_OXYGEN_NIGHT}"
    )
    assert float(low[0]["min"]) < 90


def test_oxygen_detail_has_ten_minute_intervals_consistent_with_the_summary(
    export: SyntheticExport,
) -> None:
    for row in read_table(export, "tracker.oxygen_saturation"):
        if row["tag_id"] != "31301":
            assert row["binning"] == ""
            continue
        bins = json.loads(
            export.json_path("tracker.oxygen_saturation", row["binning"]).read_text("utf-8")
        )
        assert len(bins) == synth.NIGHT_MINUTES // 10
        assert all(b["end_time"] - b["start_time"] == 599_000 for b in bins)
        assert min(b["spo2_min"] for b in bins) == float(row["min"])
        below = sum(1 for b in bins if b["spo2_min"] < 90)
        assert below * 600 == float(row["low_duration"])


def test_every_referenced_detail_file_exists(export: SyntheticExport) -> None:
    references = {
        "tracker.oxygen_saturation": "binning",
        "tracker.heart_rate": "binning_data",
        "step_daily_trend": "binning_data",
    }
    for table, column in references.items():
        names = [row[column] for row in read_table(export, table) if row[column]]
        assert names, table
        for name in names:
            path = export.json_path(table, name)
            assert path.is_file(), path
            assert path.parent.name == name[0]


def test_heart_rate_detail_has_one_bin_per_minute(export: SyntheticExport) -> None:
    rows = read_table(export, "tracker.heart_rate")
    assert len(rows) == 3 * 2
    bins = json.loads(
        export.json_path("tracker.heart_rate", rows[0]["binning_data"]).read_text("utf-8")
    )
    assert len(bins) == 60
    assert bins[1]["start_time"] - bins[0]["start_time"] == 60_000


def test_snoring_includes_a_row_dated_1970_only_when_asked(tmp_path: Path) -> None:
    with_invalid = read_table(build_export(tmp_path / "a", n_days=3), "sleep_snoring")
    without = read_table(
        build_export(tmp_path / "b", n_days=3, with_invalid_rows=False), "sleep_snoring"
    )
    assert len(with_invalid) == len(without) + 1
    assert sum(row["start_time"].startswith("1970") for row in with_invalid) == 1
    assert not any(row["start_time"].startswith("1970") for row in without)


def test_each_day_has_three_step_rows_and_bins_add_up_to_the_total(
    export: SyntheticExport,
) -> None:
    rows = read_table(export, "step_daily_trend")
    assert len(rows) == 3 * export.n_days
    assert {row["source_type"] for row in rows} == {"-2", "109", "0"}
    for row in rows:
        bins = json.loads(
            export.json_path("step_daily_trend", row["binning_data"]).read_text("utf-8")
        )
        assert len(bins) == 144
        assert sum(b["count"] for b in bins) == int(row["count"])


def test_the_export_day_is_partial_unless_complete_is_requested(tmp_path: Path) -> None:
    def last_total(export: SyntheticExport) -> int:
        totals = [r for r in read_table(export, "step_daily_trend") if r["source_type"] == "-2"]
        return int(max(totals, key=lambda r: r["day_time"])["count"])

    assert last_total(build_export(tmp_path / "a", n_days=4)) == synth.PARTIAL_DAY_STEPS
    complete = build_export(tmp_path / "b", n_days=4, last_day_complete=True)
    assert last_total(complete) == synth.day_steps(3)


def test_a_later_export_keeps_ids_adds_records_and_completes_the_old_export_day(
    tmp_path: Path,
) -> None:
    older = build_export(tmp_path / "older", n_days=4)
    newer = build_export(tmp_path / "newer", n_days=6)
    for table in synth.TABLES:
        old_ids = {row["datauuid"] for row in read_table(older, table)}
        new_ids = {row["datauuid"] for row in read_table(newer, table)}
        assert old_ids < new_ids, table

    def steps(export: SyntheticExport) -> dict[str, str]:
        return {row["datauuid"]: row["count"] for row in read_table(export, "step_daily_trend")}

    old_steps, new_steps = steps(older), steps(newer)
    changed = {ident for ident in old_steps if old_steps[ident] != new_steps[ident]}
    export_day_ids = {synth.record_id("step_daily_trend", f"day:3:{s}") for s in (-2, 109, 0)}
    assert changed == export_day_ids

    def sessions(export: SyntheticExport) -> dict[str, dict[str, str]]:
        return {row["datauuid"]: row for row in read_table(export, "sleep")}

    old_sleep, new_sleep = sessions(older), sessions(newer)
    assert all(new_sleep[ident] == row for ident, row in old_sleep.items())


def test_building_twice_gives_identical_files(tmp_path: Path) -> None:
    first = build_export(tmp_path / "a", n_days=4)
    second = build_export(tmp_path / "b", n_days=4)
    for table in synth.TABLES:
        assert first.csv_path(table).read_bytes() == second.csv_path(table).read_bytes()


def test_fewer_than_two_days_is_rejected(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="at least 2"):
        build_export(tmp_path, n_days=1)
