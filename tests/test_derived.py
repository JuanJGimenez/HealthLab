"""Tests for the calculated tables, ``night`` and ``day``."""

from __future__ import annotations

from collections.abc import Iterator
from datetime import date, datetime
from typing import Any

import pytest

from healthlab.derived import rebuild
from healthlab.derived.rebuild import DerivedCounts, ensure_derived, rebuild_derived
from healthlab.storage.database import Connection, open_database
from tests.support.sample_db import build_sample, insert, session


@pytest.fixture
def db() -> Iterator[Connection]:
    """The sample database with its calculated tables built."""
    with build_sample() as connection:
        rebuild_derived(connection)
        yield connection


def night(db: Connection, night_date: str) -> dict[str, Any]:
    """Return one row of ``night`` as a dictionary."""
    cursor = db.execute("SELECT * FROM night WHERE night_date = ?", [night_date])
    names = [column[0] for column in cursor.description]
    return dict(zip(names, cursor.fetchall()[0], strict=True))


def day(db: Connection, when: str) -> dict[str, Any]:
    """Return one row of ``day`` as a dictionary."""
    cursor = db.execute("SELECT * FROM day WHERE day = ?", [when])
    names = [column[0] for column in cursor.description]
    return dict(zip(names, cursor.fetchall()[0], strict=True))


def test_only_long_sessions_are_nights_one_per_date(db: Connection) -> None:
    rows = db.execute("SELECT night_date, session_id FROM night ORDER BY 1").fetchall()
    assert rows == [(date(2026, 1, 5), "A"), (date(2026, 1, 6), "B"), (date(2026, 1, 9), "C")]


def test_a_night_carries_its_sleep_figures(db: Connection) -> None:
    a = night(db, "2026-01-05")
    assert a["start_at"] == datetime(2026, 1, 5, 23, 30)
    assert a["end_at"] == datetime(2026, 1, 6, 6, 30)
    assert (a["hours"], a["fragment_count"], a["score"], a["efficiency_pct"]) == (7.0, 1, 80, 90)
    assert a["extra_sleep_min"] == 150
    assert (a["awake_min"], a["light_min"], a["deep_min"], a["rem_min"]) == (20, 200, 80, 120)
    assert (a["bedtime_hour"], a["weekday"], a["is_weekend_night"]) == (23.5, 1, False)
    assert round(a["asleep_hours"], 3) == round(400 / 60, 3)


def test_a_night_that_starts_after_midnight_has_a_bedtime_above_24(db: Connection) -> None:
    b = night(db, "2026-01-06")
    assert (b["bedtime_hour"], b["weekday"], b["extra_sleep_min"]) == (24.5, 2, 0)
    assert b["light_min"] is None
    c = night(db, "2026-01-09")
    assert (c["weekday"], c["is_weekend_night"]) == (5, True)


def test_oxygen_comes_from_the_longest_record_inside_the_window(db: Connection) -> None:
    a = night(db, "2026-01-05")
    assert (a["spo2_avg"], a["spo2_min"], a["low_minutes"]) == (94, 84, 10)
    assert (a["below_85_minutes"], a["spo2_interval_min"]) == (10, 10)
    assert a["spo2_recorded_hours"] == 6.67
    b = night(db, "2026-01-06")
    assert (b["spo2_min"], b["spo2_recorded_hours"]) == (91, 2.0)
    assert (b["below_85_minutes"], b["spo2_interval_min"]) == (0, None)


def test_the_other_signals_are_attached_by_time(db: Connection) -> None:
    a = night(db, "2026-01-05")
    assert (a["skin_temp_c"], a["skin_temp_vs_baseline_c"]) == (34.5, 0.5)
    assert a["respiratory_rate_avg"] == 14.2
    assert (a["snoring_min"], a["snoring_events"]) == (2.0, 2)
    assert (a["hrv_rmssd_ms"], a["hrv_sdnn_ms"]) == (40, 60)
    assert (a["night_hr_avg"], a["night_hr_min"]) == (60, 50)
    b = night(db, "2026-01-06")
    for column in ("skin_temp_c", "respiratory_rate_avg", "snoring_min", "snoring_events"):
        assert b[column] is None, column
    assert (b["hrv_rmssd_ms"], b["night_hr_avg"], b["below_85_minutes"]) == (None, None, 0)


def test_a_night_in_another_time_zone_is_matched_in_utc(db: Connection) -> None:
    c = night(db, "2026-01-09")
    # 01:30 UTC is 21:30 local, half an hour before sleep: it must not count.
    assert (c["night_hr_avg"], c["night_hr_min"]) == (55, 55)
    assert (c["spo2_min"], c["spo2_recorded_hours"], c["below_85_minutes"]) == (93, 6.92, 0)


def test_a_night_carries_the_context_of_its_day(db: Connection) -> None:
    a = night(db, "2026-01-05")
    assert (a["exercise_min"], a["exercise_count"]) == (105, 2)
    assert a["exercise_types"] == "CrossFit, walking"
    assert (a["steps"], a["stress_avg"]) == (9000, 30)
    assert night(db, "2026-01-06")["exercise_types"] == "type 99999"
    c = night(db, "2026-01-09")
    assert (c["exercise_min"], c["exercise_types"], c["steps"], c["stress_avg"]) == (
        None,
        None,
        None,
        None,
    )


def test_every_day_with_records_gets_a_row_linked_to_its_nights(db: Connection) -> None:
    rows = db.execute(
        "SELECT day, previous_night_date, next_night_date FROM day ORDER BY day"
    ).fetchall()
    assert rows == [
        (date(2026, 1, 5), None, date(2026, 1, 5)),
        (date(2026, 1, 6), date(2026, 1, 5), date(2026, 1, 6)),
        (date(2026, 1, 7), date(2026, 1, 6), None),
        (date(2026, 1, 9), None, date(2026, 1, 9)),
    ]


def test_a_day_gathers_activity_exercise_pulse_stress_and_energy(db: Connection) -> None:
    five = day(db, "2026-01-05")
    assert (five["steps"], five["active_min"], five["distance_m"]) == (9000, 100, 7000)
    assert (five["floors"], five["active_calorie_kcal"]) == (3, 400)
    assert (five["exercise_min"], five["exercise_count"]) == (105, 2)
    assert five["exercise_types"] == "CrossFit, walking"
    assert (five["hr_avg"], five["hr_min"], five["hr_max"]) == (60, 60, 60)
    assert (five["stress_avg"], five["stress_count"], five["energy_score"]) == (30, 2, None)
    six = day(db, "2026-01-06")
    assert (six["hr_min"], six["hr_max"], six["energy_score"]) == (50, 100, 85)
    assert round(six["hr_avg"], 2) == 73.33
    assert (six["steps"], six["stress_avg"], six["stress_count"]) == (None, None, 0)
    seven = day(db, "2026-01-07")
    assert (seven["steps"], seven["exercise_min"], seven["exercise_count"]) == (5000, 0, 0)
    assert day(db, "2026-01-09")["hr_avg"] == 87.5


def test_rebuilding_follows_the_detail_tables(db: Connection) -> None:
    assert rebuild_derived(db) == DerivedCounts(nights=3, days=4)
    session(db, "D", "2026-01-10 23:00", "2026-01-11 06:00")
    insert(db, "steps_day", samsung_id="steps10", day=datetime(2026, 1, 10), steps=1234)
    assert rebuild_derived(db) == DerivedCounts(nights=4, days=5)
    assert night(db, "2026-01-10")["steps"] == 1234


def test_an_empty_database_gives_empty_calculated_tables() -> None:
    with open_database(None) as connection:
        assert rebuild_derived(connection) == DerivedCounts(nights=0, days=0)


def test_a_failed_rebuild_keeps_the_previous_tables(
    db: Connection, monkeypatch: pytest.MonkeyPatch
) -> None:
    session(db, "D", "2026-01-10 23:00", "2026-01-11 06:00")

    def broken(_: Connection) -> int:
        raise RuntimeError("boom")

    monkeypatch.setattr(rebuild, "rebuild_day", broken)
    with pytest.raises(RuntimeError, match="boom"):
        rebuild_derived(db)
    assert db.execute("SELECT count(*) FROM night").fetchall() == [(3,)]


def test_calculated_tables_are_rebuilt_only_when_missing_or_out_of_date(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with build_sample() as connection:
        assert ensure_derived(connection) is True
        assert ensure_derived(connection) is False
        assert connection.execute("SELECT count(*) FROM night").fetchall() == [(3,)]
        newer = rebuild.DERIVED_VERSION + 1
        monkeypatch.setattr(rebuild, "DERIVED_VERSION", newer)
        assert ensure_derived(connection) is True
        assert connection.execute("SELECT version FROM derived_version").fetchall() == [(newer,)]
        assert ensure_derived(connection) is False
