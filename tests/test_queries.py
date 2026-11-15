"""Tests for the questions the screens ask."""

from __future__ import annotations

from collections.abc import Iterator
from datetime import date, datetime

import pandas as pd
import pytest

from misalud.derived.rebuild import rebuild_derived
from misalud.queries.common import Period, UnknownMetricError, plain
from misalud.queries.database import data_period, import_history, table_sizes
from misalud.queries.days import DAY_METRICS, days_by_month, list_days
from misalud.queries.nights import (
    NIGHT_METRICS,
    list_nights,
    nights_by_month,
    nights_by_weekday,
    oxygen_summary,
    relate,
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
    assert [(night["night_date"], night["low_minutes"]) for night in worst] == [("2026-01-05", 10)]
    assert worst_oxygen_nights(db, limit=0) == []
    assert worst_oxygen_nights(db, MIDDLE) == []


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
        {"night_date": "2026-01-05", "x": 7.0, "y": 23.5},
        {"night_date": "2026-01-06", "x": 6.5, "y": 24.5},
        {"night_date": "2026-01-09", "x": 7.0, "y": 22.0},
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
        first = ImportInfo("first.zip", datetime(2026, 1, 6, 20, 0), "7013005")
        apply_merge(
            connection,
            {"steps_day": frame},
            info=first,
            issues=issues,
            failures={"hrv": "gone"},
            now=datetime(2026, 1, 7, 9, 0),
        )
        apply_merge(connection, {}, info=ImportInfo("second.zip", datetime(2026, 2, 1)))
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
            "rejected_count": 1,
            "failed_domains": 1,
        }
