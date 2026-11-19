"""Tests for the data of the "one night" screen."""

from __future__ import annotations

from collections.abc import Iterator
from datetime import date

import pytest

from healthlab.derived.rebuild import rebuild_derived
from healthlab.queries.night_detail import (
    COMPARED_METRICS,
    DEFAULT_TRACKS,
    TRACKS,
    low_spans,
    night_detail,
    night_differences,
)
from healthlab.storage.database import Connection
from tests.support.sample_db import at, build_sample, insert


@pytest.fixture
def db() -> Iterator[Connection]:
    """The sample database with a few per-minute rows for night A."""
    with build_sample() as connection:
        for minute, (rate, temperature, level) in enumerate([(14.0, 34.1, 3), (15.0, 34.2, 0)]):
            moment = at(f"2026-01-06 03:0{minute}")
            insert(
                connection,
                "respiratory_rate_minute",
                night_samsung_id="breathA",
                start_utc=moment,
                rate=rate,
            )
            insert(
                connection,
                "skin_temperature_minute",
                night_samsung_id="skinA",
                start_utc=moment,
                mean_c=temperature,
            )
            insert(connection, "movement_minute", start_utc=moment, activity_level=level)
        rebuild_derived(connection)
        yield connection


def test_there_are_eight_tracks_and_four_are_shown_by_default() -> None:
    assert list(TRACKS) == [
        "stages",
        "oxygen",
        "pulse",
        "variability",
        "snoring",
        "breathing",
        "skin_temperature",
        "movement",
    ]
    assert set(DEFAULT_TRACKS) <= set(TRACKS)


def test_a_night_comes_with_its_figures_and_neighbours(db: Connection) -> None:
    detail = night_detail(db, date(2026, 1, 5))
    assert detail is not None
    assert detail["night"]["session_id"] == "A"
    assert detail["night"]["utc_offset_min"] == -180
    assert detail["night"]["has_valid_oxygen"] is True
    assert (detail["night"]["spo2_id"], detail["night"]["skin_baseline_c"]) == ("oxA", 34.0)
    assert (detail["previous"], detail["next"]) == (None, "2026-01-06")
    middle = night_detail(db, date(2026, 1, 6))
    assert middle is not None
    assert (middle["previous"], middle["next"]) == ("2026-01-05", "2026-01-09")
    assert middle["night"]["has_valid_oxygen"] is False
    assert night_detail(db, date(2026, 1, 7)) is None


def test_every_track_is_given_in_the_local_time_of_the_night(db: Connection) -> None:
    detail = night_detail(db, date(2026, 1, 5))
    assert detail is not None
    tracks = detail["tracks"]
    assert tracks["stages"][0] == {
        "from": "2026-01-05T23:30:00",
        "to": "2026-01-05T23:50:00",
        "code": 40001,
    }
    assert [stage["code"] for stage in tracks["stages"]] == [40001, 40002, 40003, 40004]
    assert tracks["oxygen"] == [
        {
            "from": f"2026-01-06T00:{m:02d}:00",
            "to": f"2026-01-06T00:{m + 10}:00",
            "average": None,
            "lowest": low,
            "is_low": is_low,
        }
        for m, low, is_low in [(0, 92, False), (10, 89, True), (20, 84, True), (30, 88, True)]
    ]
    assert tracks["pulse"] == [
        {"at": "2026-01-05T23:30:00", "value": 60},
        {"at": "2026-01-06T02:00:00", "value": 50},
        {"at": "2026-01-06T06:30:00", "value": 70},
    ]
    assert [point["value"] for point in tracks["variability"]] == [30, 50, 40]
    assert tracks["snoring"] == [
        {"from": "2026-01-06T01:00:00", "to": "2026-01-06T01:00:00", "seconds": 30},
        {"from": "2026-01-06T02:00:00", "to": "2026-01-06T02:00:00", "seconds": 90},
    ]
    assert tracks["breathing"] == [
        {"at": "2026-01-06T00:00:00", "value": 14.0},
        {"at": "2026-01-06T00:01:00", "value": 15.0},
    ]
    assert [point["value"] for point in tracks["skin_temperature"]] == [34.1, 34.2]
    assert [point["value"] for point in tracks["movement"]] == [3, 0]


def test_a_night_without_a_signal_gets_an_empty_track(db: Connection) -> None:
    detail = night_detail(db, date(2026, 1, 6))
    assert detail is not None
    assert {name: len(points) for name, points in detail["tracks"].items()} == dict.fromkeys(
        TRACKS, 0
    )


def test_a_night_in_another_time_zone_uses_its_own_clock(db: Connection) -> None:
    detail = night_detail(db, date(2026, 1, 9))
    assert detail is not None
    assert detail["tracks"]["pulse"] == [{"at": "2026-01-09T22:00:00", "value": 55}]
    assert detail["tracks"]["oxygen"][0]["lowest"] == 93


def test_consecutive_low_intervals_are_joined_into_stretches(db: Connection) -> None:
    detail = night_detail(db, date(2026, 1, 5))
    assert detail is not None
    assert detail["low_spans"] == [{"from": "2026-01-06T00:10:00", "to": "2026-01-06T00:40:00"}]
    intervals = [
        {"from": "01:00", "to": "01:01", "is_low": True},
        {"from": "01:01", "to": "01:02", "is_low": True},
        {"from": "01:02", "to": "01:03", "is_low": False},
        {"from": "01:03", "to": "01:04", "is_low": True},
    ]
    assert low_spans(intervals) == [
        {"from": "01:00", "to": "01:02"},
        {"from": "01:03", "to": "01:04"},
    ]
    assert low_spans([]) == []


def test_two_nights_are_compared_figure_by_figure(db: Connection) -> None:
    first = night_detail(db, date(2026, 1, 5))
    second = night_detail(db, date(2026, 1, 9))
    short = night_detail(db, date(2026, 1, 6))
    assert first is not None and second is not None and short is not None
    differences = night_differences(first["night"], second["night"])
    assert list(differences) == list(COMPARED_METRICS)
    assert (differences["low_minutes"], differences["spo2_min"]) == (-10, 9)
    assert differences["night_hr_avg"] == -5
    assert differences["score"] == 0
    # Night C has no stages, variability or snoring; night B has a short oxygen recording.
    assert (differences["asleep_hours"], differences["hrv_rmssd_ms"]) == (None, None)
    assert differences["snoring_min"] is None
    against_short = night_differences(first["night"], short["night"])
    assert (against_short["low_minutes"], against_short["spo2_min"]) == (None, None)
