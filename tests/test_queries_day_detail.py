"""Tests for the data of the "one day" screen, the typical day and short-window notices."""

from __future__ import annotations

import dataclasses
from collections.abc import Iterator
from datetime import date

import pytest

from misalud.derived.rebuild import rebuild_derived
from misalud.queries.common import Period, UnknownMetricError
from misalud.queries.coverage import short_window_notices
from misalud.queries.day_detail import DAY_TRACKS, day_detail, hourly_profile
from misalud.queries.nights import RELATE_METRICS, relate
from misalud.reading.contracts import load_contracts
from misalud.storage.database import Connection
from tests.support.sample_db import at, build_sample, insert, pulse


@pytest.fixture
def db() -> Iterator[Connection]:
    """The sample database plus step intervals and a Saturday pulse reading."""
    with build_sample() as connection:
        for interval, steps in [(60, 500), (61, 0), (108, 900)]:
            insert(
                connection,
                "steps_interval",
                day=at("2026-01-05 00:00"),
                interval=interval,
                start_at=at(f"2026-01-05 {interval // 6:02d}:{interval % 6 * 10:02d}"),
                steps=steps,
            )
        pulse(connection, "2026-01-10 15:00", 80)
        rebuild_derived(connection)
        yield connection


def test_a_day_has_five_tracks() -> None:
    assert list(DAY_TRACKS) == ["pulse", "stress", "steps", "exercise", "sleep"]


def test_a_day_comes_with_its_figures_and_neighbours(db: Connection) -> None:
    detail = day_detail(db, date(2026, 1, 5))
    assert detail is not None
    assert (detail["day"]["steps"], detail["day"]["next_night_date"]) == (9000, "2026-01-05")
    assert (detail["previous"], detail["next"]) == (None, "2026-01-06")
    later = day_detail(db, date(2026, 1, 7))
    assert later is not None
    assert (later["previous"], later["next"]) == ("2026-01-06", "2026-01-09")
    assert day_detail(db, date(2026, 1, 8)) is None


def test_the_tracks_of_a_day_run_from_midnight_to_midnight(db: Connection) -> None:
    detail = day_detail(db, date(2026, 1, 5))
    assert detail is not None
    tracks = detail["tracks"]
    assert tracks["pulse"] == [{"at": "2026-01-05T23:30:00", "value": 60}]
    assert tracks["stress"] == [
        {"at": "2026-01-05T10:00:00", "value": 20},
        {"at": "2026-01-05T16:00:00", "value": 40},
    ]
    assert tracks["steps"] == [
        {"from": "2026-01-05T10:00:00", "to": "2026-01-05T10:10:00", "value": 500},
        {"from": "2026-01-05T18:00:00", "to": "2026-01-05T18:10:00", "value": 900},
    ]
    assert tracks["exercise"] == [
        {
            "from": "2026-01-05T18:00:00",
            "to": "2026-01-05T19:00:00",
            "label": "walking",
            "minutes": 60,
        },
        {
            "from": "2026-01-05T19:30:00",
            "to": "2026-01-05T20:15:00",
            "label": "CrossFit",
            "minutes": 45,
        },
    ]
    # The night begins at 23:30: only its first half hour belongs to this day.
    assert tracks["sleep"] == [
        {"from": "2026-01-05T23:30:00", "to": "2026-01-06T00:00:00", "is_night": True}
    ]


def test_a_day_shows_the_end_of_one_night_and_later_sleep(db: Connection) -> None:
    detail = day_detail(db, date(2026, 1, 6))
    assert detail is not None
    assert [(span["from"][11:16], span["to"][11:16]) for span in detail["tracks"]["sleep"]] == [
        ("00:00", "06:30"),
        ("07:30", "10:00"),
    ]
    assert [point["value"] for point in detail["tracks"]["pulse"]] == [50, 70, 100]
    assert detail["tracks"]["exercise"][0]["label"] == "type 99999"
    assert detail["tracks"]["steps"] == []


def test_the_typical_day_averages_by_hour_apart_for_weekends(db: Connection) -> None:
    profile = hourly_profile(db)
    assert profile["pulse"] == [
        {"hour": 2, "weekdays": 50.0, "weekend": None},
        {"hour": 6, "weekdays": 85.0, "weekend": None},
        {"hour": 12, "weekdays": None, "weekend": 80.0},
        {"hour": 21, "weekdays": 120.0, "weekend": None},
        {"hour": 22, "weekdays": 55.0, "weekend": None},
        {"hour": 23, "weekdays": 60.0, "weekend": None},
    ]
    assert profile["stress"] == [
        {"hour": 10, "weekdays": 20.0, "weekend": None},
        {"hour": 16, "weekdays": 40.0, "weekend": None},
    ]
    recent = hourly_profile(db, Period(start=date(2026, 1, 9)))
    assert [row["hour"] for row in recent["pulse"]] == [12, 21, 22]
    assert recent["stress"] == []


def test_a_measure_of_the_day_can_be_related_with_the_night_that_follows(db: Connection) -> None:
    assert "day.energy_score" in RELATE_METRICS
    active = relate(db, "day.active_min", "hours")
    assert active["points"] == [{"night_date": "2026-01-05", "x": 100.0, "y": 7.0, "tagged": False}]
    pulse_and_oxygen = relate(db, "day.hr_avg", "low_minutes")
    assert [(point["x"], point["y"]) for point in pulse_and_oxygen["points"]] == [
        (60.0, 10.0),
        (87.5, 0.0),
    ]
    with pytest.raises(UnknownMetricError, match=r"unknown metrics: day\.steps"):
        relate(db, "day.steps", "hours")


def test_no_table_in_use_has_a_short_window_today(db: Connection) -> None:
    assert short_window_notices(db) == []


def test_a_short_window_table_gives_a_notice_when_the_period_is_not_covered(
    db: Connection,
) -> None:
    real = load_contracts()
    contracts = {
        "stress": dataclasses.replace(real["stress"], rolling_window_days=30),
        "weight": dataclasses.replace(real["weight"], rolling_window_days=60),
        "sleep": real["sleep"],
        "odd": dataclasses.replace(real["stress"], rolling_window_days=7, feeds=("night",)),
    }
    stress = {
        "table": "stress",
        "window_days": 30,
        "covered_from": "2026-01-05",
        "covered_to": "2026-01-05",
    }
    weight = {"table": "weight", "window_days": 60, "covered_from": None, "covered_to": None}
    assert short_window_notices(db, contracts=contracts) == [stress, weight]
    earlier = Period(start=date(2026, 1, 1))
    assert short_window_notices(db, earlier, contracts) == [stress, weight]
    covered = Period(start=date(2026, 1, 5))
    assert short_window_notices(db, covered, contracts) == [weight]
