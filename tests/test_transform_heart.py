"""Tests for the heart domain."""

from __future__ import annotations

import pandas as pd

from healthlab.transform.heart import (
    transform_ecg,
    transform_heart_rate,
    transform_hrv,
    transform_stress,
)
from tests.support.fake_source import FakeSource, epoch_ms, raw, timed

HR = "tracker.heart_rate"


def beat(moment: str, rate: float) -> dict[str, float]:
    """Build one per-minute heart rate measurement."""
    return {
        "start_time": epoch_ms(moment),
        "heart_rate": rate,
        "heart_rate_min": rate - 2,
        "heart_rate_max": rate + 2,
    }


def test_heart_rate_becomes_one_row_per_minute_in_time_order() -> None:
    rows = [
        timed(
            "h2",
            start="2026-01-02 04:00:00.000",
            end="2026-01-02 04:59:00.000",
            binning_data="h2.json",
        ),
        timed(
            "h1",
            start="2026-01-02 03:00:00.000",
            end="2026-01-02 04:00:00.000",
            binning_data="h1.json",
        ),
        timed("spot", binning_data=None),
    ]
    source = FakeSource(
        tables={HR: raw(rows)},
        details={
            (HR, "h1.json"): [beat("2026-01-02 03:00", 60), beat("2026-01-02 04:00", 61)],
            (HR, "h2.json"): [beat("2026-01-02 04:00", 62), beat("2026-01-02 04:01", 500)],
        },
    )
    result = transform_heart_rate(source)
    minutes = result.tables["heart_rate_minute"]
    assert list(minutes.columns) == [
        "start_utc",
        "start_at",
        "heart_rate",
        "heart_rate_min",
        "heart_rate_max",
    ]
    assert minutes["start_at"].tolist() == [
        pd.Timestamp("2026-01-02 00:00"),
        pd.Timestamp("2026-01-02 01:00"),
    ]
    # 04:00 UTC is in both hourly records; the first one in file order (h2) loses.
    assert minutes["heart_rate"].tolist() == [60, 61]
    assert [(i.key, i.rule, i.value) for i in result.issues] == [
        ("h2", "heart_rate_out_of_range", "1")
    ]


def test_the_same_local_minute_in_two_time_zones_is_two_measurements() -> None:
    rows = [
        timed(
            "east",
            start="2026-01-02 03:00:00.000",
            end="2026-01-02 04:00:00.000",
            offset="UTC-0300",
            binning_data="east.json",
        ),
        timed(
            "west",
            start="2026-01-02 04:00:00.000",
            end="2026-01-02 05:00:00.000",
            offset="UTC-0400",
            binning_data="west.json",
        ),
    ]
    source = FakeSource(
        tables={HR: raw(rows)},
        details={
            (HR, "east.json"): [beat("2026-01-02 03:00", 60)],
            (HR, "west.json"): [beat("2026-01-02 04:00", 104)],
        },
    )
    minutes = transform_heart_rate(source).tables["heart_rate_minute"]
    assert minutes["start_at"].tolist() == [pd.Timestamp("2026-01-02 00:00")] * 2
    assert minutes["heart_rate"].tolist() == [60, 104]


def test_hrv_windows_keep_their_start_and_end() -> None:
    begin = epoch_ms("2026-01-02 03:00")
    source = FakeSource(
        tables={"hrv": raw([timed("h", binning_data="h.json")])},
        details={
            ("hrv", "h.json"): [
                {"start_time": begin, "end_time": begin + 300_000, "rmssd": 35.5, "sdnn": 40.0},
                {"start_time": begin, "end_time": begin + 300_000, "rmssd": 36.5, "sdnn": 41.0},
            ]
        },
    )
    windows = transform_hrv(source).tables["hrv_window"]
    assert list(windows.columns) == ["start_utc", "start_at", "end_at", "rmssd_ms", "sdnn_ms"]
    assert windows["rmssd_ms"].tolist() == [36.5]
    assert windows["end_at"][0] - windows["start_at"][0] == pd.Timedelta(minutes=5)


def test_stress_measurements_are_ordered_by_time() -> None:
    rows = [
        timed(
            "b",
            start="2026-01-02 15:00:00.000",
            end="2026-01-02 15:01:00.000",
            score="40",
            min="30",
            max="50",
        ),
        timed(
            "a",
            start="2026-01-02 14:00:00.000",
            end="2026-01-02 14:01:00.000",
            score="20",
            min="10",
            max="25",
        ),
    ]
    stress = transform_stress(FakeSource(tables={"stress": raw(rows)})).tables["stress"]
    assert stress["samsung_id"].tolist() == ["a", "b"]
    assert stress[["score", "score_min", "score_max"]].iloc[0].tolist() == [20, 10, 25]


def test_ecg_records_name_their_trace_file_without_loading_it() -> None:
    row = {
        "datauuid": "e",
        "start_time": "2026-01-02 14:00:00.000",
        "time_offset": "UTC-0300",
        "end_time": "2026-01-02 14:00:30.000",
        "mean_heart_rate": "71.5",
        "classification": "1",
        "sample_frequency": "500",
        "sample_count": "15000",
        "chart_data": "e.chart_data.json",
    }
    ecg = transform_ecg(FakeSource(tables={"ecg": raw([row])})).tables["ecg"]
    record = ecg.iloc[0]
    assert record["start_at"] == pd.Timestamp("2026-01-02 11:00")
    assert record["mean_hr"] == 71.5
    assert (record["classification_code"], record["sample_frequency_hz"]) == (1, 500)
    assert (record["sample_count"], record["trace_file"]) == (15000, "e.chart_data.json")
