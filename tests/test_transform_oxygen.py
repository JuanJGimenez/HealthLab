"""Tests for the oxygen domain."""

from __future__ import annotations

import pandas as pd
import pytest

from misalud.transform.common import KEPT, TransformError
from misalud.transform.oxygen import INTERVAL_COLUMNS, NIGHT_COLUMNS, transform_oxygen
from tests.support.fake_source import FakeSource, epoch_ms, raw, timed

TABLE = "tracker.oxygen_saturation"


def oxygen(ident: str, tag: str = "31301", **cells: str | None) -> dict[str, str | None]:
    """Build a row of Samsung's oxygen table."""
    base = {
        "tag_id": tag,
        "spo2": "94.5",
        "min": "88",
        "max": "99",
        "low_duration": "600",
        "coverage_rate": "97",
        "binning": f"{ident}.json",
    }
    return {**timed(ident), **base, **cells}


def interval(start: str, low: float, irregular: int | None = 0) -> dict[str, float | None]:
    """Build one 10-minute interval of a detail file."""
    begin = epoch_ms(start)
    return {
        "start_time": begin,
        "end_time": begin + 599_000,
        "spo2": low + 3,
        "spo2_min": low,
        "spo2_max": low + 6,
        "isIrregular": irregular,
    }


def test_overnight_records_become_nights_and_spot_measurements_are_left_out() -> None:
    source = FakeSource(
        tables={TABLE: raw([oxygen("night"), oxygen("spot", tag="31000", binning=None)])},
        details={
            (TABLE, "night.json"): [
                interval("2026-01-02 02:30", 91),
                interval("2026-01-02 02:40", 88, irregular=1),
                interval("2026-01-02 02:50", 92, irregular=None),
            ]
        },
    )
    result = transform_oxygen(source)
    nights = result.tables["spo2_night"]
    assert list(nights.columns) == NIGHT_COLUMNS
    assert nights["samsung_id"].tolist() == ["night"]
    row = nights.iloc[0]
    assert (row["spo2_avg"], row["spo2_min"], row["spo2_max"]) == (94.5, 88, 99)
    assert (row["low_seconds"], row["coverage_pct"]) == (600, 97)
    assert row["start_at"] == pd.Timestamp("2026-01-01 23:30")

    intervals = result.tables["spo2_interval"]
    assert list(intervals.columns) == INTERVAL_COLUMNS
    assert intervals["night_samsung_id"].tolist() == ["night"] * 3
    assert intervals["spo2_min"].tolist() == [91, 88, 92]
    assert intervals["start_at"][0] == pd.Timestamp("2026-01-01 23:30")
    assert intervals["start_utc"][0] == pd.Timestamp("2026-01-02 02:30")
    assert intervals["end_at"][0] == pd.Timestamp("2026-01-01 23:39:59")
    assert intervals["is_irregular"].tolist()[:2] == [False, True]
    assert pd.isna(intervals["is_irregular"][2])
    assert result.issues == []


def test_impossible_values_are_rejected_in_nights_and_intervals() -> None:
    source = FakeSource(
        tables={TABLE: raw([oxygen("good"), oxygen("bad", min="12")])},
        details={
            (TABLE, "good.json"): [
                interval("2026-01-02 02:30", 91),
                interval("2026-01-02 02:40", 40),
            ],
            (TABLE, "bad.json"): [interval("2026-01-02 02:30", 91)],
        },
    )
    result = transform_oxygen(source)
    assert result.tables["spo2_night"]["samsung_id"].tolist() == ["good"]
    assert result.tables["spo2_interval"]["spo2_min"].tolist() == [91]
    # The 40 % interval fails on its average, 43 %, the first column checked.
    assert [(i.table, i.key, i.rule, i.value) for i in result.issues] == [
        ("spo2_night", "bad", "spo2_out_of_range", "12.0"),
        ("spo2_interval", "good", "spo2_out_of_range", "1"),
    ]


def test_a_night_without_its_detail_file_keeps_its_summary() -> None:
    result = transform_oxygen(FakeSource(tables={TABLE: raw([oxygen("night")])}))
    assert len(result.tables["spo2_night"]) == 1
    assert result.tables["spo2_interval"].empty
    assert list(result.tables["spo2_interval"].columns) == INTERVAL_COLUMNS
    assert [(i.rule, i.action) for i in result.issues] == [("detail_file_unreadable", KEPT)]


def test_a_missing_required_column_stops_the_domain() -> None:
    row = {key: value for key, value in oxygen("night").items() if key != "binning"}
    with pytest.raises(TransformError, match="binning"):
        transform_oxygen(FakeSource(tables={TABLE: raw([row])}))
