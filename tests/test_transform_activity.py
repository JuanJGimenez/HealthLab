"""Tests for the activity domain."""

from __future__ import annotations

import pandas as pd

from misalud.transform.activity import (
    transform_activity_summary,
    transform_custom_exercises,
    transform_exercise,
    transform_movement,
    transform_steps,
    transform_vitality,
    transform_weight,
)
from misalud.transform.common import KEPT, REJECTED
from tests.support.fake_source import FakeSource, epoch_ms, raw, timed

STEPS = "step_daily_trend"


def test_exercise_sessions_get_minutes_and_named_measures() -> None:
    row = timed(
        "x",
        start="2026-01-02 21:00:00.000",
        end="2026-01-02 22:00:00.000",
        exercise_type="15002",
        duration="3600000",
        calorie="450.5",
        distance="0",
        mean_heart_rate="140",
        max_heart_rate="178",
        min_heart_rate="95",
        mean_speed=None,
        vo2_max="41.2",
        custom_id=None,
    )
    exercise = transform_exercise(FakeSource(tables={"exercise": raw([row])})).tables["exercise"]
    record = exercise.iloc[0]
    assert record["start_at"] == pd.Timestamp("2026-01-02 18:00")
    assert (record["duration_min"], record["type_code"]) == (60, 15002)
    assert (record["calorie_kcal"], record["mean_hr"], record["max_hr"]) == (450.5, 140, 178)
    assert record["vo2_max"] == 41.2
    assert pd.isna(record["mean_speed_mps"])
    assert pd.isna(record["custom_id"])


def test_weight_measurements_have_a_single_moment() -> None:
    row = {
        "datauuid": "w",
        "start_time": "2026-01-02 11:00:00.000",
        "time_offset": "UTC-0300",
        "weight": "90.0",
        "height": "173",
        "body_fat": "24.5",
    }
    weight = transform_weight(FakeSource(tables={"weight": raw([row])})).tables["weight"]
    record = weight.iloc[0]
    assert record["measured_at"] == pd.Timestamp("2026-01-02 08:00")
    assert (record["weight_kg"], record["height_cm"], record["body_fat_pct"]) == (90, 173, 24.5)
    assert pd.isna(record["skeletal_muscle_mass_kg"])
    assert "end_at" not in weight.columns


def step_row(
    ident: str, day: str, source_type: str, count: str, file: str | None
) -> dict[str, str | None]:
    """Build a row of Samsung's daily step table."""
    return {
        "datauuid": ident,
        "day_time": f"{day} 00:00:00.000",
        "source_type": source_type,
        "count": count,
        "distance": "800.5",
        "calorie": "40.25",
        "binning_data": file,
    }


def bins(counts: dict[int, int], size: int = 144) -> list[dict[str, float]]:
    """Build a day's detail file with steps in the given positions."""
    return [{"count": counts.get(i, 0), "distance": 0.5, "calorie": 0.1} for i in range(size)]


def test_only_the_day_total_row_counts_and_intervals_are_placed_by_position() -> None:
    rows = [
        step_row("total", "2026-01-02", "-2", "1000", "total.json"),
        step_row("watch", "2026-01-02", "109", "900", "watch.json"),
        step_row("phone", "2026-01-02", "0", "300", "phone.json"),
    ]
    source = FakeSource(
        tables={STEPS: raw(rows)},
        details={(STEPS, "total.json"): bins({0: 100, 51: 900})},
    )
    result = transform_steps(source)
    days = result.tables["steps_day"]
    assert list(days.columns) == ["samsung_id", "day", "steps", "distance_m", "calorie_kcal"]
    assert days["samsung_id"].tolist() == ["total"]
    assert days.iloc[0][["steps", "distance_m", "calorie_kcal"]].tolist() == [1000, 800.5, 40.25]
    intervals = result.tables["steps_interval"]
    assert len(intervals) == 144
    assert intervals["steps"].sum() == 1000
    busy = intervals[intervals["steps"] == 900].iloc[0]
    assert busy["interval"] == 51
    assert busy["start_at"] == pd.Timestamp("2026-01-02 08:30")
    assert busy["day"] == pd.Timestamp("2026-01-02")
    assert result.issues == []


def test_a_day_with_an_unusable_detail_file_keeps_its_total() -> None:
    rows = [
        step_row("gone", "2026-01-01", "-2", "10", "gone.json"),
        step_row("short", "2026-01-02", "-2", "20", "short.json"),
        step_row("odd", "2026-01-03", "-2", "30", "odd.json"),
        step_row("none", "2026-01-04", "-2", "40", None),
        step_row("sparse", "2026-01-05", "-2", "50", "sparse.json"),
    ]
    source = FakeSource(
        tables={STEPS: raw(rows)},
        details={
            (STEPS, "short.json"): bins({}, size=10),
            (STEPS, "odd.json"): {"count": 1},
            (STEPS, "sparse.json"): [{"count": 50}] + [{}] * 143,
        },
    )
    result = transform_steps(source)
    assert result.tables["steps_day"]["steps"].tolist() == [10, 20, 30, 40, 50]
    intervals = result.tables["steps_interval"]
    assert intervals["day"].unique().tolist() == [pd.Timestamp("2026-01-05")]
    assert intervals["steps"].sum() == 50
    assert intervals["distance_m"].isna().all()
    assert [(i.key, i.rule, i.value, i.action) for i in result.issues] == [
        ("gone", "detail_file_unreadable", "gone.json", KEPT),
        ("short", "unexpected_interval_count", "10", KEPT),
        ("odd", "unexpected_interval_count", "not a list", KEPT),
    ]


def test_days_without_any_intervals_give_an_empty_typed_table() -> None:
    source = FakeSource(tables={STEPS: raw([step_row("a", "2026-01-01", "-2", "10", None)])})
    intervals = transform_steps(source).tables["steps_interval"]
    assert intervals.empty
    assert list(intervals.columns) == [
        "day",
        "interval",
        "start_at",
        "steps",
        "distance_m",
        "calorie_kcal",
    ]
    assert str(intervals["start_at"].dtype) == "datetime64[ns]"


def test_the_daily_activity_summary_converts_milliseconds_to_minutes() -> None:
    row = {
        "datauuid": "d",
        "day_time": "2026-01-02 00:00:00.000",
        "step_count": "9500",
        "active_time": "5400000",
        "walk_time": "3600000",
        "run_time": "600000",
        "exercise_time": "3000000",
        "distance": "7200.5",
        "calorie": "510.2",
        "floor_count": "8",
    }
    source = FakeSource(tables={"activity.day_summary": raw([row])})
    record = transform_activity_summary(source).tables["activity_day"].iloc[0]
    assert record["day"] == pd.Timestamp("2026-01-02")
    assert record[["steps", "active_min", "walk_min", "run_min", "exercise_min"]].tolist() == [
        9500,
        90,
        60,
        10,
        50,
    ]
    assert record[["distance_m", "active_calorie_kcal", "floors"]].tolist() == [7200.5, 510.2, 8]


def test_the_energy_score_is_one_row_per_day() -> None:
    rows: list[dict[str, str | None]] = [
        {
            "datauuid": "v2",
            "day_time": "2026-01-03 00:00:00.000",
            "total_score": "81",
            "shr_value": "52",
            "shrv_value": "38.5",
        },
        {
            "datauuid": "v1",
            "day_time": "2026-01-02 00:00:00.000",
            "total_score": "74",
            "shr_value": None,
            "shrv_value": None,
        },
    ]
    vitality = transform_vitality(FakeSource(tables={"vitality_score": raw(rows)})).tables[
        "vitality_day"
    ]
    assert vitality["samsung_id"].tolist() == ["v1", "v2"]
    assert vitality["energy_score"].tolist() == [74, 81]
    assert vitality.iloc[1][["sleeping_hr", "sleeping_hrv_ms"]].tolist() == [52, 38.5]


def test_movement_becomes_one_row_per_minute() -> None:
    source = FakeSource(
        tables={"movement": raw([timed("m", binning_data="m.json")])},
        details={
            ("movement", "m.json"): [
                {"start_time": epoch_ms("2026-01-02 02:31"), "activity_level": 3},
                {"start_time": epoch_ms("2026-01-02 02:30"), "activity_level": 1},
            ]
        },
    )
    movement = transform_movement(source).tables["movement_minute"]
    assert list(movement.columns) == ["start_utc", "start_at", "activity_level"]
    assert movement["activity_level"].tolist() == [1, 3]
    assert movement["start_at"][0] == pd.Timestamp("2026-01-01 23:30")


def test_custom_exercise_types_give_a_name_to_each_custom_id() -> None:
    rows: list[dict[str, str | None]] = [
        {"custom_id": "b_2", "custom_name": "Yoga", "create_time": "2025-04-01 10:00:00.000"},
        {"custom_id": "a_1", "custom_name": "Crossfit", "create_time": "2025-03-30 10:00:00.000"},
        {"custom_id": "a_1", "custom_name": "CrossFit", "create_time": "2025-03-31 10:00:00.000"},
        {"custom_id": None, "custom_name": "Lost", "create_time": "2025-04-02 10:00:00.000"},
        {"custom_id": "c_3", "custom_name": None, "create_time": "2025-04-03 10:00:00.000"},
    ]
    result = transform_custom_exercises(FakeSource(tables={"exercise.custom_exercise": raw(rows)}))
    types = result.tables["exercise_custom_type"]
    assert types["custom_id"].tolist() == ["a_1", "b_2"]
    assert types["name"].tolist() == ["CrossFit", "Yoga"]
    assert types["created_at"][0] == pd.Timestamp("2025-03-31 10:00")
    assert [(i.key, i.rule, i.action) for i in result.issues] == [
        ("?", "missing_id_or_name", REJECTED),
        ("c_3", "missing_id_or_name", REJECTED),
    ]
