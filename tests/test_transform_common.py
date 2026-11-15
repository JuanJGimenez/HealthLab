"""Tests for the building blocks shared by the domain transformers."""

from __future__ import annotations

import pandas as pd
import pytest

from misalud.config import ValueRange
from misalud.transform.common import (
    KEPT,
    REJECTED,
    TransformError,
    ValidationIssue,
    drop_out_of_range_points,
    epoch_ms_to_local,
    expand_details,
    number_column,
    offset_minutes,
    parse_day,
    parse_utc,
    prepare_daily,
    prepare_timed,
    reject_out_of_range,
    require_columns,
    text_column,
    to_number,
    unique_by_utc_start,
)
from tests.support.fake_source import EXPORTED_AT, FakeSource, epoch_ms, raw, timed


def rules(issues: list[ValidationIssue]) -> list[tuple[str, str, str]]:
    """Return issues as ``(key, rule, action)``, to compare them in one assertion."""
    return [(issue.key, issue.rule, issue.action) for issue in issues]


def test_required_columns_pass_when_present_and_fail_naming_the_missing_ones() -> None:
    frame = raw([{"a": "1", "b": "2"}])
    require_columns(frame, "sleep", ["a", "b"])
    with pytest.raises(TransformError, match="sleep: missing required columns: c, d"):
        require_columns(frame, "sleep", ["a", "d", "c"])


def test_an_absent_optional_column_reads_as_all_missing() -> None:
    frame = raw([{"a": "1"}, {"a": "x"}])
    assert text_column(frame, "a").tolist() == ["1", "x"]
    assert text_column(frame, "b").isna().all()
    assert number_column(frame, "a").tolist()[0] == 1.0
    assert number_column(frame, "a").isna().tolist() == [False, True]
    assert number_column(frame, "b").isna().all()


def test_text_that_is_not_a_number_becomes_missing() -> None:
    numbers = to_number(pd.Series(["1", "2.5", "abc", None], dtype="string"))
    assert numbers.tolist()[:2] == [1.0, 2.5]
    assert numbers.isna().tolist() == [False, False, True, True]
    assert str(numbers.dtype) == "float64"


def test_moments_are_parsed_and_other_text_becomes_missing() -> None:
    moments = parse_utc(pd.Series(["2026-01-02 02:30:00.000", "yesterday", None], dtype="string"))
    assert moments[0] == pd.Timestamp("2026-01-02 02:30:00")
    assert moments.isna().tolist() == [False, True, True]


@pytest.mark.parametrize(
    ("text", "minutes"),
    [("UTC-0300", -180.0), ("UTC+0530", 330.0), ("UTC+0000", 0.0), ("UTC-0400", -240.0)],
)
def test_offsets_become_minutes_east_of_utc(text: str, minutes: float) -> None:
    assert offset_minutes(pd.Series([text], dtype="string")).tolist() == [minutes]


def test_text_that_is_not_an_offset_becomes_missing() -> None:
    assert offset_minutes(pd.Series(["-0300", None, "UTC-03"], dtype="string")).isna().all()


def test_epoch_milliseconds_become_local_moments() -> None:
    local = epoch_ms_to_local([epoch_ms("2026-01-02 02:30:00")], -180)
    assert local.tolist() == [pd.Timestamp("2026-01-01 23:30:00")]


def test_days_are_read_at_midnight() -> None:
    days = parse_day(pd.Series(["2026-01-02 00:00:00.000", "soon"], dtype="string"))
    assert days[0] == pd.Timestamp("2026-01-02")
    assert pd.isna(days[1])


def test_a_timed_table_gets_its_id_local_times_and_offset() -> None:
    issues: list[ValidationIssue] = []
    frame = prepare_timed(
        raw([timed("a"), timed("b", offset="UTC-0400")]),
        samsung_table="sleep",
        table="sleep_session",
        exported_at=EXPORTED_AT,
        issues=issues,
    )
    assert issues == []
    assert frame["samsung_id"].tolist() == ["a", "b"]
    assert frame["utc_offset_min"].tolist() == [-180.0, -240.0]
    assert frame["start_at"].tolist() == [
        pd.Timestamp("2026-01-01 23:30:00"),
        pd.Timestamp("2026-01-01 22:30:00"),
    ]
    assert frame["end_at"][0] == pd.Timestamp("2026-01-02 06:30:00")


def test_bad_timed_rows_are_rejected_and_each_one_is_reported() -> None:
    issues: list[ValidationIssue] = []
    frame = prepare_timed(
        raw(
            [
                timed("good"),
                timed(None),
                timed("no-offset", offset=None),
                timed("bad-start", start="garbage"),
                timed("bad-end", end=None),
                timed("old", start="1970-01-01 00:00:00.000", end="1970-01-01 00:00:05.000"),
                timed("future", start="2026-01-20 00:00:00.000", end="2026-01-20 01:00:00.000"),
                timed("just-after", start="2026-01-11 12:00:00.000", end="2026-01-11 13:00:00.000"),
            ]
        ),
        samsung_table="sleep",
        table="sleep_session",
        exported_at=EXPORTED_AT,
        issues=issues,
    )
    assert frame["samsung_id"].tolist() == ["good", "just-after"]
    assert rules(issues) == [
        ("?", "missing_id", REJECTED),
        ("no-offset", "unreadable_time", REJECTED),
        ("bad-start", "unreadable_time", REJECTED),
        ("bad-end", "unreadable_time", REJECTED),
        ("old", "date_before_2020", REJECTED),
        ("future", "date_after_export", REJECTED),
    ]
    assert issues[4] == ValidationIssue(
        "sleep_session", "old", "date_before_2020", "1970-01-01 00:00:00.000"
    )


def test_a_timed_table_without_end_time_is_accepted_when_asked() -> None:
    issues: list[ValidationIssue] = []
    rows = raw(
        [{"datauuid": "a", "start_time": "2026-01-02 02:30:00.000", "time_offset": "UTC-0300"}]
    )
    frame = prepare_timed(
        rows,
        samsung_table="weight",
        table="weight",
        exported_at=EXPORTED_AT,
        issues=issues,
        with_end=False,
    )
    assert "end_at" not in frame.columns
    assert len(frame) == 1
    with pytest.raises(TransformError, match="end_time"):
        prepare_timed(
            rows, samsung_table="weight", table="weight", exported_at=EXPORTED_AT, issues=issues
        )


def test_rows_out_of_range_are_rejected_and_missing_values_pass() -> None:
    issues: list[ValidationIssue] = []
    frame = pd.DataFrame(
        {
            "samsung_id": ["a", "b", "c", "d"],
            "x": [95.0, 20.0, None, 100.0],
            "y": [90.0, 90.0, 90.0, 101.0],
        }
    )
    kept = reject_out_of_range(
        frame, ["x", "y"], ValueRange(60, 100), table="t", rule="out", issues=issues
    )
    assert kept["samsung_id"].tolist() == ["a", "c"]
    assert issues == [
        ValidationIssue("t", "b", "out", "20.0"),
        ValidationIssue("t", "d", "out", "101.0"),
    ]


def parents(*rows: tuple[str, float, str | None]) -> pd.DataFrame:
    """Build parent rows for ``expand_details``."""
    return pd.DataFrame(rows, columns=["samsung_id", "utc_offset_min", "file"])


def test_detail_files_become_one_row_per_measurement() -> None:
    source = FakeSource(
        details={
            ("hr", "a.json"): [
                {
                    "start_time": epoch_ms("2026-01-02 03:00"),
                    "end_time": epoch_ms("2026-01-02 03:01"),
                    "v": 60,
                },
                {"start_time": epoch_ms("2026-01-02 03:01"), "v": "x"},
                {"v": 99},
            ],
            ("hr", "b.json"): [{"start_time": epoch_ms("2026-01-02 08:00"), "v": 70, "w": 1}],
        }
    )
    issues: list[ValidationIssue] = []
    points = expand_details(
        source,
        parents(("a", -180.0, "a.json"), ("b", -240.0, "b.json"), ("c", -180.0, None)),
        samsung_table="hr",
        table="heart_rate_minute",
        file_column="file",
        fields={"v": "value", "w": "extra"},
        issues=issues,
        with_end=True,
    )
    assert issues == []
    assert points["parent_id"].tolist() == ["a", "a", "b"]
    assert points["start_utc"].tolist() == [
        pd.Timestamp("2026-01-02 03:00"),
        pd.Timestamp("2026-01-02 03:01"),
        pd.Timestamp("2026-01-02 08:00"),
    ]
    assert points["start_at"].tolist() == [
        pd.Timestamp("2026-01-02 00:00"),
        pd.Timestamp("2026-01-02 00:01"),
        pd.Timestamp("2026-01-02 04:00"),
    ]
    assert points["end_at"][0] == pd.Timestamp("2026-01-02 00:01")
    assert pd.isna(points["end_at"][1])
    assert points["value"].tolist()[0] == 60.0
    assert points["value"].isna().tolist() == [False, True, False]
    assert points["extra"].isna().tolist() == [True, True, False]


def test_unusable_detail_files_are_reported_and_skipped() -> None:
    source = FakeSource(details={("hr", "empty.json"): [], ("hr", "odd.json"): {"a": 1}})
    issues: list[ValidationIssue] = []
    points = expand_details(
        source,
        parents(("a", -180.0, "gone.json"), ("b", -180.0, "empty.json"), ("c", -180.0, "odd.json")),
        samsung_table="hr",
        table="heart_rate_minute",
        file_column="file",
        fields={"v": "value"},
        issues=issues,
    )
    assert points.empty
    assert list(points.columns) == ["parent_id", "start_utc", "start_at", "value"]
    assert str(points["start_at"].dtype).startswith("datetime64")
    assert rules(issues) == [
        ("a", "detail_file_unreadable", KEPT),
        ("b", "detail_file_empty", KEPT),
        ("c", "detail_file_empty", KEPT),
    ]


def test_an_empty_result_with_end_times_keeps_its_columns() -> None:
    points = expand_details(
        FakeSource(),
        parents(),
        samsung_table="hr",
        table="t",
        file_column="file",
        fields={},
        issues=[],
        with_end=True,
    )
    assert list(points.columns) == ["parent_id", "start_utc", "start_at", "end_at"]


def test_points_out_of_range_are_dropped_with_one_issue_per_parent() -> None:
    points = pd.DataFrame(
        {"parent_id": ["a", "a", "a", "b", "b"], "v": [10.0, 300.0, 250.0, None, 5.0]}
    )
    issues: list[ValidationIssue] = []
    kept = drop_out_of_range_points(
        points, "v", ValueRange(30, 220), table="t", rule="out", issues=issues
    )
    assert kept["v"].isna().tolist() == [True]
    assert sorted(issues, key=lambda issue: issue.key) == [
        ValidationIssue("t", "a", "out", "3"),
        ValidationIssue("t", "b", "out", "1"),
    ]


def day_row(ident: str | None, day: str) -> dict[str, str | None]:
    """Build a row of a daily table."""
    return {"datauuid": ident, "day_time": day}


def test_a_daily_table_gets_one_row_per_day_in_order() -> None:
    issues: list[ValidationIssue] = []
    frame = prepare_daily(
        raw(
            [
                day_row("second", "2026-01-02 00:00:00.000"),
                day_row("first-old", "2026-01-01 00:00:00.000"),
                day_row("first-new", "2026-01-01 00:00:00.000"),
                day_row(None, "2026-01-03 00:00:00.000"),
                day_row("unreadable", "someday"),
                day_row("old", "1970-01-01 00:00:00.000"),
                day_row("future", "2026-03-01 00:00:00.000"),
            ]
        ),
        samsung_table="vitality_score",
        table="vitality_day",
        exported_at=EXPORTED_AT,
        issues=issues,
    )
    assert frame["samsung_id"].tolist() == ["first-new", "second"]
    assert frame["day"].tolist() == [pd.Timestamp("2026-01-01"), pd.Timestamp("2026-01-02")]
    assert rules(issues) == [
        ("?", "missing_id", REJECTED),
        ("unreadable", "unreadable_day", REJECTED),
        ("old", "date_before_2020", REJECTED),
        ("future", "date_after_export", REJECTED),
        ("first-old", "duplicate_day", REJECTED),
    ]


def test_a_daily_table_without_its_day_column_cannot_be_transformed() -> None:
    with pytest.raises(TransformError, match="day_time"):
        prepare_daily(
            raw([{"datauuid": "a"}]),
            samsung_table="vitality_score",
            table="vitality_day",
            exported_at=EXPORTED_AT,
            issues=[],
        )


def test_repeated_measurements_are_told_apart_by_utc_moment_not_local_time() -> None:
    # The wearer flew west: 23:00 local happened twice, an hour apart in UTC.
    points = pd.DataFrame(
        {
            "parent_id": ["a", "b", "c"],
            "start_utc": pd.to_datetime(
                ["2026-01-02 03:00", "2026-01-02 02:00", "2026-01-02 03:00"]
            ),
            "start_at": pd.to_datetime(
                ["2026-01-01 23:00", "2026-01-01 23:00", "2026-01-01 23:00"]
            ),
            "v": [1.0, 2.0, 3.0],
        }
    )
    unique = unique_by_utc_start(points)
    assert unique["v"].tolist() == [2.0, 3.0]
    assert "parent_id" not in unique.columns
