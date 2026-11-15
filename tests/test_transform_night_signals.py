"""Tests for skin temperature, breathing and snoring."""

from __future__ import annotations

import pandas as pd

from misalud.transform.common import KEPT, REJECTED
from misalud.transform.night_signals import (
    to_boolean,
    transform_respiratory_rate,
    transform_skin_temperature,
    transform_snoring,
)
from tests.support.fake_source import FakeSource, epoch_ms, raw, timed


def test_booleans_are_read_from_words_and_digits() -> None:
    values = pd.Series(["True", "false", "1", "0", "maybe", None], dtype="string")
    result = to_boolean(values)
    assert result.tolist()[:4] == [True, False, True, False]
    assert result.isna().tolist() == [False, False, False, False, True, True]


def test_skin_temperature_gives_a_night_summary_and_a_minute_series() -> None:
    rows = [
        timed(
            "night",
            temperature="34.5",
            baseline="34.2",
            min="33.0",
            max="35.5",
            lower_bound="33.5",
            upper_bound="35.0",
            binning_data="night.json",
        ),
        timed("cold", temperature="10.0", binning_data="cold.json"),
    ]
    source = FakeSource(
        tables={"skin_temperature": raw(rows)},
        details={
            ("skin_temperature", "night.json"): [
                {
                    "start_time": epoch_ms("2026-01-02 02:30"),
                    "mean": 34.0,
                    "min": 33.9,
                    "max": 34.1,
                },
                {
                    "start_time": epoch_ms("2026-01-02 02:31"),
                    "mean": 80.0,
                    "min": 80.0,
                    "max": 80.0,
                },
            ]
        },
    )
    result = transform_skin_temperature(source)
    nights = result.tables["skin_temperature"]
    assert nights["samsung_id"].tolist() == ["night"]
    assert nights.iloc[0][["temperature_c", "baseline_c", "min_c", "max_c"]].tolist() == [
        34.5,
        34.2,
        33.0,
        35.5,
    ]
    minutes = result.tables["skin_temperature_minute"]
    assert minutes["night_samsung_id"].tolist() == ["night"]
    assert minutes["mean_c"].tolist() == [34.0]
    assert minutes["start_at"][0] == pd.Timestamp("2026-01-01 23:30")
    assert [(i.table, i.key, i.rule, i.action) for i in result.issues] == [
        ("skin_temperature", "cold", "temperature_out_of_range", REJECTED),
        ("skin_temperature_minute", "night", "temperature_out_of_range", REJECTED),
    ]


def test_skin_temperature_without_a_detail_column_gives_an_empty_series() -> None:
    result = transform_skin_temperature(
        FakeSource(tables={"skin_temperature": raw([timed("night", temperature="34.5")])})
    )
    assert len(result.tables["skin_temperature"]) == 1
    assert result.tables["skin_temperature_minute"].empty
    assert result.issues == []


def test_respiratory_rate_stores_zero_as_no_measurement() -> None:
    rows = [
        timed(
            "night",
            average="14.5",
            lower_limit="12",
            upper_limit="18",
            is_outlier="False",
            binning_data="night.json",
        ),
        timed(
            "unmeasured",
            start="2026-01-03 02:30:00.000",
            end="2026-01-03 09:30:00.000",
            average="0.0",
            is_outlier="True",
        ),
        timed("absurd", average="90"),
    ]
    source = FakeSource(
        tables={"respiratory_rate": raw(rows)},
        details={
            ("respiratory_rate", "night.json"): [
                {"start_time": epoch_ms("2026-01-02 02:30"), "respiratory_rate": 14.0},
                {"start_time": epoch_ms("2026-01-02 02:31"), "respiratory_rate": 0.0},
                {"start_time": epoch_ms("2026-01-02 02:32"), "respiratory_rate": 70.0},
            ]
        },
    )
    result = transform_respiratory_rate(source)
    nights = result.tables["respiratory_rate"]
    assert nights["samsung_id"].tolist() == ["night", "unmeasured"]
    assert nights["rate_avg"].tolist()[0] == 14.5
    assert pd.isna(nights["rate_avg"][1])
    assert nights["is_outlier"].tolist() == [False, True]
    assert (nights["lower_limit"][0], nights["upper_limit"][0]) == (12, 18)
    minutes = result.tables["respiratory_rate_minute"]
    assert minutes["rate"].tolist()[0] == 14.0
    assert minutes["rate"].isna().tolist() == [False, True]
    assert [(i.table, i.key, i.rule, i.action) for i in result.issues] == [
        ("respiratory_rate", "unmeasured", "no_measurement", KEPT),
        ("respiratory_rate", "absurd", "rate_out_of_range", REJECTED),
        ("respiratory_rate_minute", "night", "rate_out_of_range", REJECTED),
    ]


def test_snoring_events_get_their_duration_in_seconds_and_1970_rows_are_rejected() -> None:
    rows = [
        timed(
            "late", start="2026-01-02 05:00:00.000", end="2026-01-02 05:00:30.000", duration="30000"
        ),
        timed(
            "early",
            start="2026-01-02 03:00:00.000",
            end="2026-01-02 03:00:12.500",
            duration="12500",
        ),
        timed("zero", start="1970-01-01 00:00:00.000", end="1970-01-01 00:00:00.000", duration="0"),
    ]
    result = transform_snoring(FakeSource(tables={"sleep_snoring": raw(rows)}))
    events = result.tables["snoring_event"]
    assert events["samsung_id"].tolist() == ["early", "late"]
    assert events["duration_s"].tolist() == [12.5, 30.0]
    assert [(i.key, i.rule) for i in result.issues] == [("zero", "date_before_2020")]
