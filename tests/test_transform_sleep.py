"""Tests for the sleep domain."""

from __future__ import annotations

import pandas as pd
import pytest

from healthlab.reading.errors import TableMissingError
from healthlab.transform.common import KEPT, TransformError
from healthlab.transform.sleep import SESSION_COLUMNS, STAGE_COLUMNS, night_date_of, transform_sleep
from tests.support.fake_source import FakeSource, raw, timed


def fragment(
    ident: str, start: str, end: str, minutes: str | None, **cells: str | None
) -> dict[str, str | None]:
    """Build a row of Samsung's sleep table."""
    base = {"sleep_duration": minutes, "integrated_id": None, "combined_id": None}
    return timed(ident, start, end, **{**base, **cells})


def stage(ident: str, sleep_id: str, start: str, end: str, code: str) -> dict[str, str | None]:
    """Build a row of Samsung's sleep stage table."""
    return timed(ident, start, end, sleep_id=sleep_id, stage=code)


NIGHT = fragment(
    "night",
    "2026-01-02 02:30:00.000",
    "2026-01-02 09:30:00.000",
    "420",
    sleep_score="80",
    efficiency="92",
    sleep_cycle="4",
    physical_recovery="70",
    mental_recovery="75",
    movement_awakening="12",
    sleep_latency="600000",
    total_light_duration="200",
    total_rem_duration="90",
)
NAP = fragment("nap", "2026-01-02 18:00:00.000", "2026-01-02 19:00:00.000", "60")
STAGES = [
    stage("s1", "night", "2026-01-02 02:30:00.000", "2026-01-02 03:00:00.000", "40002"),
    stage("s2", "night", "2026-01-02 03:00:00.000", "2026-01-02 04:30:00.000", "40003"),
]


def source_with(
    sleep: list[dict[str, str | None]], stages: list[dict[str, str | None]]
) -> FakeSource:
    """Build an export holding the two tables the sleep domain needs."""
    return FakeSource(tables={"sleep": raw(sleep), "sleep_stage": raw(stages)})


def test_a_night_and_a_nap_become_two_sessions() -> None:
    result = transform_sleep(source_with([NAP, NIGHT], STAGES))
    sessions = result.tables["sleep_session"]
    assert list(sessions.columns) == SESSION_COLUMNS
    assert sessions["samsung_id"].tolist() == ["night", "nap"]
    assert sessions["is_night"].tolist() == [True, False]
    night = sessions.iloc[0]
    assert night["start_at"] == pd.Timestamp("2026-01-01 23:30")
    assert night["end_at"] == pd.Timestamp("2026-01-02 06:30")
    assert night["night_date"] == pd.Timestamp("2026-01-01")
    assert night["utc_offset_min"] == -180
    assert (night["duration_min"], night["fragment_count"]) == (420, 1)
    assert (night["score"], night["efficiency_pct"], night["cycles"]) == (80, 92, 4)
    assert (night["latency_min"], night["light_min"], night["rem_min"]) == (10, 200, 90)
    assert sessions.iloc[1]["night_date"] == pd.Timestamp("2026-01-02")
    assert pd.isna(sessions.iloc[1]["score"])
    assert result.issues == []


def test_stages_are_attached_to_their_session_with_their_duration() -> None:
    stages = transform_sleep(source_with([NIGHT], STAGES)).tables["sleep_stage"]
    assert list(stages.columns) == STAGE_COLUMNS
    assert stages["session_id"].tolist() == ["night", "night"]
    assert stages["stage_code"].tolist() == [40002, 40003]
    assert stages["duration_min"].tolist() == [30, 90]
    assert stages["start_at"][0] == pd.Timestamp("2026-01-01 23:30")


def test_a_partial_fragment_and_its_stages_are_dropped_without_issue() -> None:
    partial = fragment(
        "partial",
        "2026-01-02 02:30:00.000",
        "2026-01-02 05:00:00.000",
        "150",
        integrated_id="night",
    )
    extra = stage("s3", "partial", "2026-01-02 02:30:00.000", "2026-01-02 03:00:00.000", "40002")
    result = transform_sleep(source_with([NIGHT, partial], [*STAGES, extra]))
    assert result.tables["sleep_session"]["samsung_id"].tolist() == ["night"]
    assert result.tables["sleep_stage"]["samsung_id"].tolist() == ["s1", "s2"]
    assert result.issues == []


def test_fragments_grouped_by_samsung_form_one_session_scored_by_sleep_combined() -> None:
    first = fragment(
        "f1",
        "2026-01-02 02:00:00.000",
        "2026-01-02 05:00:00.000",
        "180",
        combined_id="group",
        sleep_score="50",
    )
    second = fragment(
        "f2",
        "2026-01-02 06:00:00.000",
        "2026-01-02 08:00:00.000",
        "120",
        combined_id="group",
        sleep_score="40",
    )
    combined = raw(
        [
            {
                "datauuid": "group",
                "sleep_score": "77",
                "sleep_latency": "300000",
                "total_light_duration": "150",
                "total_rem_duration": "60",
            },
            {
                "datauuid": "unrelated",
                "sleep_score": "1",
                "sleep_latency": None,
                "total_light_duration": None,
                "total_rem_duration": None,
            },
        ]
    )
    stages = [stage("s1", "f2", "2026-01-02 06:00:00.000", "2026-01-02 06:30:00.000", "40004")]
    source = source_with([second, first, NAP], stages)
    source.tables["sleep_combined"] = combined
    result = transform_sleep(source)
    sessions = result.tables["sleep_session"]
    assert sessions["samsung_id"].tolist() == ["group", "nap"]
    group = sessions.iloc[0]
    assert group["start_at"] == pd.Timestamp("2026-01-01 23:00")
    assert group["end_at"] == pd.Timestamp("2026-01-02 05:00")
    assert (group["duration_min"], group["fragment_count"]) == (300, 2)
    assert (group["score"], group["latency_min"], group["light_min"]) == (77, 5, 150)
    assert bool(group["is_night"])
    assert result.tables["sleep_stage"]["session_id"].tolist() == ["group"]


def test_a_group_without_combined_scores_takes_them_from_its_longest_fragment() -> None:
    first = fragment(
        "f1",
        "2026-01-02 02:00:00.000",
        "2026-01-02 05:00:00.000",
        "180",
        combined_id="group",
        sleep_score="50",
    )
    second = fragment(
        "f2",
        "2026-01-02 06:00:00.000",
        "2026-01-02 08:00:00.000",
        "120",
        combined_id="group",
        sleep_score="40",
    )
    sessions = transform_sleep(source_with([first, second], STAGES)).tables["sleep_session"]
    assert sessions["score"].tolist() == [50]


def test_rows_without_duration_or_with_an_impossible_one_are_rejected() -> None:
    no_duration = fragment("empty", "2026-01-03 02:00:00.000", "2026-01-03 05:00:00.000", None)
    too_long = fragment("long", "2026-01-04 02:00:00.000", "2026-01-06 05:00:00.000", "3000")
    result = transform_sleep(source_with([NIGHT, no_duration, too_long], STAGES))
    assert result.tables["sleep_session"]["samsung_id"].tolist() == ["night"]
    assert [(issue.key, issue.rule) for issue in result.issues] == [
        ("empty", "missing_duration"),
        ("long", "duration_out_of_range"),
    ]


def test_an_unknown_stage_code_is_kept_with_a_notice() -> None:
    odd = stage("s9", "night", "2026-01-02 04:30:00.000", "2026-01-02 05:00:00.000", "40009")
    result = transform_sleep(source_with([NIGHT], [*STAGES, odd]))
    assert result.tables["sleep_stage"]["stage_code"].tolist() == [40002, 40003, 40009]
    assert [(i.table, i.key, i.rule, i.value, i.action) for i in result.issues] == [
        ("sleep_stage", "s9", "unknown_stage_code", "40009", KEPT)
    ]


def test_the_night_date_is_the_evening_the_night_follows() -> None:
    starts = pd.Series(pd.to_datetime(["2026-01-03 02:00", "2026-01-02 23:30", "2026-01-03 15:00"]))
    assert night_date_of(starts).tolist() == [
        pd.Timestamp("2026-01-02"),
        pd.Timestamp("2026-01-02"),
        pd.Timestamp("2026-01-03"),
    ]


def test_missing_tables_and_columns_stop_the_domain() -> None:
    with pytest.raises(TableMissingError):
        transform_sleep(FakeSource(tables={"sleep": raw([NIGHT])}))
    without_duration = {key: value for key, value in NIGHT.items() if key != "sleep_duration"}
    with pytest.raises(TransformError, match="sleep_duration"):
        transform_sleep(source_with([without_duration], STAGES))
