"""Tests for the questions the screens ask."""

from __future__ import annotations

from collections.abc import Iterator
from datetime import date, datetime

import pandas as pd
import pytest

from misalud.annotations.store import set_tag
from misalud.derived.rebuild import rebuild_derived
from misalud.queries.common import NightScope, Period, UnknownMetricError, plain
from misalud.queries.database import data_period, import_history, issue_summary, table_sizes
from misalud.queries.days import DAY_METRICS, days_by_month, list_days
from misalud.queries.nights import (
    NIGHT_METRICS,
    list_nights,
    nights_by_month,
    nights_by_weekday,
    nights_csv,
    overview,
    oxygen_summary,
    relate,
    rolling_median,
    sustained_low_by_weekday,
    tag_comparison,
    worst_oxygen_nights,
)
from misalud.storage.database import Connection, open_database
from misalud.storage.merge import ImportInfo, apply_merge
from misalud.storage.schema import DETAIL_TABLES
from misalud.transform.common import ValidationIssue
from tests.support.sample_db import build_sample

MIDDLE = Period(start=date(2026, 1, 6), end=date(2026, 1, 8))


@pytest.fixture
def db() -> Iterator[Connection]:
    """The sample database with its calculated tables built."""
    with build_sample() as connection:
        rebuild_derived(connection)
        yield connection


def test_values_become_plain_data() -> None:
    assert plain(date(2026, 1, 5)) == "2026-01-05"
    assert plain(datetime(2026, 1, 5, 23, 30)) == "2026-01-05T23:30:00"
    assert plain(float("nan")) is None
    assert plain(7.5) == 7.5
    assert plain("text") == "text"
    assert plain(None) is None


def test_a_period_filters_by_either_end() -> None:
    assert Period().condition("day") == ("TRUE", [])
    assert Period(start=date(2026, 1, 6)).condition("day") == (
        "TRUE AND day >= ?",
        [date(2026, 1, 6)],
    )
    assert MIDDLE.condition("day") == (
        "TRUE AND day >= ? AND day <= ?",
        [date(2026, 1, 6), date(2026, 1, 8)],
    )


def test_the_metric_lists_name_real_columns(db: Connection) -> None:
    night_columns = {row[0] for row in db.execute("DESCRIBE night").fetchall()}
    day_columns = {row[0] for row in db.execute("DESCRIBE day").fetchall()}
    assert set(NIGHT_METRICS) <= night_columns
    assert set(DAY_METRICS) <= day_columns


def test_nights_are_listed_in_order_with_plain_values(db: Connection) -> None:
    nights = list_nights(db)
    assert [night["night_date"] for night in nights] == ["2026-01-05", "2026-01-06", "2026-01-09"]
    assert nights[0]["start_at"] == "2026-01-05T23:30:00"
    assert [night["has_valid_oxygen"] for night in nights] == [True, False, True]
    assert [night["session_id"] for night in list_nights(db, MIDDLE)] == ["B"]


def test_the_oxygen_summary_counts_only_nights_with_enough_recording(db: Connection) -> None:
    assert oxygen_summary(db) == {
        "nights": 3,
        "nights_with_oxygen": 2,
        "nights_below_90": 1,
        "nights_sustained_low": 1,
        "median_low_minutes": 5.0,
        "average_spo2": 95.0,
        "lowest_spo2": 84.0,
        "lowest_spo2_date": "2026-01-05",
    }
    short = oxygen_summary(db, MIDDLE)
    assert (short["nights"], short["nights_with_oxygen"], short["lowest_spo2"]) == (1, 0, None)


def test_the_worst_nights_are_those_with_time_under_90(db: Connection) -> None:
    worst = worst_oxygen_nights(db)
    assert [(night["night_date"], night["low_minutes"]) for night in worst] == [
        ("2026-01-05", 10),
        ("2026-01-09", 0),
    ]
    by_reading = worst_oxygen_nights(db, order_by="spo2_min", limit=1)
    assert [night["spo2_min"] for night in by_reading] == [84]
    by_time = worst_oxygen_nights(db, order_by="below_85_minutes")
    assert [night["below_85_minutes"] for night in by_time] == [10, 0]
    assert worst_oxygen_nights(db, limit=0) == []
    assert worst_oxygen_nights(db, MIDDLE) == []
    with pytest.raises(UnknownMetricError):
        worst_oxygen_nights(db, order_by="night_date")


def test_monthly_averages_flag_months_with_few_nights(db: Connection) -> None:
    months = nights_by_month(db, ["hours", "low_minutes", "spo2_min"])
    assert len(months) == 1
    month = months[0]
    assert (month["month"], month["nights"], month["enough_nights"]) == ("2026-01-01", 3, False)
    assert round(month["hours"], 3) == round((7 + 6.5 + 7) / 3, 3)
    # Night B has a two-hour recording, so its oxygen is left out of the averages.
    assert (month["low_minutes"], month["spo2_min"]) == (5.0, 88.5)
    assert nights_by_month(db, []) == [{"month": "2026-01-01", "nights": 3, "enough_nights": False}]


def test_weekday_figures_use_the_day_the_night_began(db: Connection) -> None:
    assert nights_by_weekday(db, "low_minutes") == [
        {"weekday": 1, "nights": 1, "average": 10.0, "median": 10.0},
        {"weekday": 2, "nights": 0, "average": None, "median": None},
        {"weekday": 5, "nights": 1, "average": 0.0, "median": 0.0},
    ]
    assert [row["nights"] for row in nights_by_weekday(db, "hours", MIDDLE)] == [1]


def test_two_metrics_are_related_night_by_night(db: Connection) -> None:
    result = relate(db, "hours", "bedtime_hour")
    assert result["points"] == [
        {"night_date": "2026-01-05", "x": 7.0, "y": 23.5, "tagged": False},
        {"night_date": "2026-01-06", "x": 6.5, "y": 24.5, "tagged": False},
        {"night_date": "2026-01-09", "x": 7.0, "y": 22.0, "tagged": False},
    ]
    assert (result["nights"], result["enough_nights"]) == (3, False)
    assert result["spearman"] == pytest.approx(-0.8660254)


def test_a_relation_needs_three_nights_and_a_metric_that_varies(db: Connection) -> None:
    few = relate(db, "hours", "spo2_min")
    assert (few["nights"], few["spearman"]) == (2, None)
    constant = relate(db, "score", "hours")
    assert (constant["nights"], constant["spearman"]) == (3, None)
    assert relate(db, "hours", "movement_awakening")["points"] == []


def test_enough_nights_make_a_relation_reliable(db: Connection) -> None:
    frame = pd.DataFrame(
        {
            "night_date": pd.date_range("2026-02-01", periods=10).date,
            "hours": [float(value) for value in range(10)],
            "score": [float(value * 2) for value in range(10)],
        }
    )
    db.register("extra", frame)
    db.execute("INSERT INTO night BY NAME SELECT * FROM extra")
    result = relate(db, "hours", "score", Period(start=date(2026, 2, 1)))
    assert (result["nights"], result["enough_nights"]) == (10, True)
    assert result["spearman"] == pytest.approx(1.0)


def test_a_column_that_is_not_a_metric_is_refused(db: Connection) -> None:
    with pytest.raises(UnknownMetricError, match="unknown metrics: session_id"):
        nights_by_month(db, ["hours", "session_id"])
    with pytest.raises(UnknownMetricError):
        nights_by_weekday(db, "1; DROP TABLE night")
    with pytest.raises(UnknownMetricError):
        relate(db, "hours", "start_at")
    with pytest.raises(UnknownMetricError, match="unknown metrics: hours"):
        days_by_month(db, ["hours"])


def test_days_are_listed_and_averaged_by_month(db: Connection) -> None:
    days = list_days(db)
    assert [day["day"] for day in days] == ["2026-01-05", "2026-01-06", "2026-01-07", "2026-01-09"]
    assert days[1]["previous_night_date"] == "2026-01-05"
    assert [day["day"] for day in list_days(db, MIDDLE)] == ["2026-01-06", "2026-01-07"]
    assert days_by_month(db, ["steps", "exercise_min"]) == [
        {"month": "2026-01-01", "days": 4, "steps": 7000.0, "exercise_min": 33.75}
    ]


def test_the_database_panel_shows_what_is_stored(db: Connection) -> None:
    sizes = {row["table"]: row for row in table_sizes(db)}
    assert set(sizes) == set(DETAIL_TABLES)
    assert sizes["sleep_session"] == {
        "table": "sleep_session",
        "records": 5,
        "first_date": "2026-01-05",
        "last_date": "2026-01-09",
    }
    assert sizes["weight"] == {
        "table": "weight",
        "records": 0,
        "first_date": None,
        "last_date": None,
    }
    assert data_period(db) == {
        "first_night": "2026-01-05",
        "last_night": "2026-01-09",
        "nights": 3,
        "first_day": "2026-01-05",
        "last_day": "2026-01-09",
        "days": 4,
    }


def test_the_import_history_lists_the_most_recent_first() -> None:
    with open_database(None) as connection:
        assert import_history(connection) == []
        frame = pd.DataFrame(
            {
                "samsung_id": pd.Series(["a"], dtype="string"),
                "day": pd.to_datetime(["2026-01-05"]),
                "steps": [9000.0],
                "distance_m": [1.0],
                "calorie_kcal": [1.0],
            }
        )
        issues = [ValidationIssue("steps_day", "x", "date_before_2020", "1970-01-01")]
        issues += [
            ValidationIssue("steps_day", "y", "date_before_2020", "1970-01-02"),
            ValidationIssue("steps_interval", "z", "detail_file_empty", "z.json", "kept"),
        ]
        first = ImportInfo("first.zip", datetime(2026, 1, 6, 20, 0), "7013005")
        apply_merge(
            connection,
            {"steps_day": frame},
            info=first,
            issues=issues,
            failures={"hrv": "gone"},
            now=datetime(2026, 1, 7, 9, 0),
        )
        assert issue_summary(connection) == [
            {"table": "steps_day", "rule": "date_before_2020", "action": "rejected", "records": 2},
            {
                "table": "steps_interval",
                "rule": "detail_file_empty",
                "action": "kept",
                "records": 1,
            },
        ]
        apply_merge(connection, {}, info=ImportInfo("second.zip", datetime(2026, 2, 1)))
        assert issue_summary(connection) == []
        history = import_history(connection)
        assert [row["file_name"] for row in history] == ["second.zip", "first.zip"]
        assert history[0]["new_count"] == 0
        assert history[1] == {
            "import_id": 1,
            "imported_at": "2026-01-07T09:00:00",
            "file_name": "first.zip",
            "samsung_app_version": "7013005",
            "exported_at": "2026-01-06T20:00:00",
            "first_date": "2026-01-05",
            "last_date": "2026-01-05",
            "new_count": 1,
            "updated_count": 0,
            "unchanged_count": 0,
            "kept_count": 0,
            "superseded_count": 0,
            "rejected_count": 2,
            "failed_domains": 1,
        }


def test_a_scope_can_keep_only_weekend_or_weekday_nights(db: Connection) -> None:
    weekend = NightScope(nights="weekend")
    assert [night["session_id"] for night in list_nights(db, weekend)] == ["C"]
    weekdays = NightScope(start=date(2026, 1, 6), nights="weekdays")
    assert [night["session_id"] for night in list_nights(db, weekdays)] == ["B"]
    assert NightScope().condition("night_date") == ("TRUE", [])
    assert oxygen_summary(db, weekend)["nights_below_90"] == 0


def test_the_overview_joins_oxygen_sleep_and_heart(db: Connection) -> None:
    result = overview(db)
    assert (result["nights"], result["nights_sustained_low"]) == (3, 1)
    assert (result["first_night"], result["last_night"]) == ("2026-01-05", "2026-01-09")
    assert round(result["average_hours"], 3) == round(20.5 / 3, 3)
    # Only night A has stages: 200 + 80 + 120 minutes asleep.
    assert round(result["average_asleep_hours"], 3) == round(400 / 60, 3)
    assert (result["median_hrv_ms"], result["average_night_hr"]) == (40, 57.5)
    empty = overview(db, Period(start=date(2027, 1, 1)))
    assert (empty["nights"], empty["first_night"], empty["average_hours"]) == (0, None, None)


def test_sustained_drops_are_counted_by_weekday(db: Connection) -> None:
    assert sustained_low_by_weekday(db) == {
        "weekdays": [
            {"weekday": 1, "nights": 1, "sustained": 1, "share_pct": 100.0},
            {"weekday": 5, "nights": 1, "sustained": 0, "share_pct": 0.0},
        ],
        "overall_share_pct": 50.0,
    }
    assert sustained_low_by_weekday(db, MIDDLE) == {"weekdays": [], "overall_share_pct": None}


def test_the_rolling_median_follows_the_most_recent_nights(db: Connection) -> None:
    assert rolling_median(db, "hours", window=2) == [
        {"night_date": "2026-01-05", "value": 7.0},
        {"night_date": "2026-01-06", "value": 6.75},
        {"night_date": "2026-01-09", "value": 6.75},
    ]
    # Night B has no valid oxygen, so the window skips it.
    assert [point["night_date"] for point in rolling_median(db, "spo2_min")] == [
        "2026-01-05",
        "2026-01-09",
    ]
    assert rolling_median(db, "movement_awakening") == []
    with pytest.raises(UnknownMetricError):
        rolling_median(db, "session_id")


def test_nights_can_be_exported_as_csv(db: Connection) -> None:
    lines = nights_csv(db).splitlines()
    assert len(lines) == 4
    header = lines[0].split(",")
    assert header[:2] == ["night_date", "session_id"]
    assert header[-1] == "has_valid_oxygen"
    assert lines[1].startswith("2026-01-05,A,2026-01-05T23:30:00,")
    assert nights_csv(db, Period(start=date(2027, 1, 1))) == ""


def test_a_scope_can_keep_the_nights_with_or_without_a_tag(db: Connection) -> None:
    set_tag(db, date(2026, 1, 5), 1, True)
    set_tag(db, date(2026, 1, 9), 1, True)
    set_tag(db, date(2026, 1, 6), 2, True)
    with_alcohol = NightScope(tag_id=1)
    assert [night["session_id"] for night in list_nights(db, with_alcohol)] == ["A", "C"]
    without = NightScope(tag_id=1, tagged=False)
    assert [night["session_id"] for night in list_nights(db, without)] == ["B"]
    both = NightScope(start=date(2026, 1, 6), nights="weekend", tag_id=1)
    assert both.condition("night_date") == (
        "TRUE AND night_date >= ? AND is_weekend_night"
        " AND night_date IN (SELECT day FROM annotation WHERE tag_id = ?)",
        [date(2026, 1, 6), 1],
    )
    assert [night["session_id"] for night in list_nights(db, both)] == ["C"]
    assert oxygen_summary(db, with_alcohol)["nights"] == 2
    assert nights_by_month(db, ["hours"], with_alcohol)[0]["nights"] == 2
    assert [n["session_id"] for n in worst_oxygen_nights(db, with_alcohol, limit=1)] == ["A"]


def test_a_relation_can_flag_the_nights_of_a_tag(db: Connection) -> None:
    set_tag(db, date(2026, 1, 6), 3, True)
    result = relate(db, "hours", "bedtime_hour", highlight_tag_id=3)
    assert [point["tagged"] for point in result["points"]] == [False, True, False]
    assert result["spearman"] == pytest.approx(-0.8660254)


def test_nights_with_a_tag_are_compared_with_nights_without_it(db: Connection) -> None:
    set_tag(db, date(2026, 1, 5), 1, True)
    result = tag_comparison(db, 1)
    assert result["with"] == {
        "nights": 1,
        "nights_with_oxygen": 1,
        "median_low_minutes": 10.0,
        "average_low_minutes": 10.0,
        "average_night_hr": 60.0,
        "median_hrv_ms": 40.0,
        "enough_nights": False,
    }
    without = result["without"]
    assert (without["nights"], without["nights_with_oxygen"]) == (2, 1)
    assert (without["median_low_minutes"], without["average_night_hr"]) == (0.0, 55.0)
    assert without["median_hrv_ms"] is None
    weekend = tag_comparison(db, 1, NightScope(nights="weekend", tag_id=2))
    assert (weekend["with"]["nights"], weekend["without"]["nights"]) == (0, 1)
    assert tag_comparison(db, 1, MIDDLE)["without"]["nights"] == 1


def test_a_group_of_ten_nights_is_enough_to_compare(db: Connection) -> None:
    frame = pd.DataFrame(
        {
            "night_date": pd.date_range("2026-02-01", periods=10).date,
            "night_hr_avg": [60.0] * 10,
        }
    )
    db.register("extra", frame)
    db.execute("INSERT INTO night BY NAME SELECT * FROM extra")
    result = tag_comparison(db, 1)
    assert (result["without"]["nights"], result["without"]["enough_nights"]) == (13, True)
