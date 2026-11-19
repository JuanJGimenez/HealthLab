"""Sleep domain: sessions and their stages.

Samsung writes one row per sleep fragment. Two columns say how fragments relate:

* ``integrated_id`` marks a partial fragment that Samsung already merged into
  another row. Such rows are duplicates of time already counted and are dropped.
* ``combined_id`` groups the fragments of one interrupted night. They become a
  single session whose scores come from the ``sleep_combined`` table.
"""

from __future__ import annotations

from typing import Final

import pandas as pd

from healthlab.config import THRESHOLDS, VALID_RANGES
from healthlab.transform.common import (
    KEPT,
    DomainResult,
    Source,
    ValidationIssue,
    number_column,
    prepare_timed,
    reject_out_of_range,
    report,
    require_columns,
    text_column,
    to_number,
)

KNOWN_STAGES: Final = frozenset({40001, 40002, 40003, 40004})
"""Stage codes listed in the data dictionary."""

SCORE_COLUMNS: Final = {
    "sleep_score": "score",
    "efficiency": "efficiency_pct",
    "sleep_cycle": "cycles",
    "physical_recovery": "physical_recovery",
    "mental_recovery": "mental_recovery",
    "movement_awakening": "movement_awakening",
}
"""Samsung columns that describe a whole session, mapped to their HealthLab names."""

SESSION_COLUMNS: Final = [
    "samsung_id",
    "start_at",
    "end_at",
    "utc_offset_min",
    "night_date",
    "duration_min",
    "fragment_count",
    "is_night",
    "score",
    "efficiency_pct",
    "latency_min",
    "cycles",
    "light_min",
    "rem_min",
    "physical_recovery",
    "mental_recovery",
    "movement_awakening",
]

STAGE_COLUMNS: Final = [
    "samsung_id",
    "session_id",
    "start_at",
    "end_at",
    "stage_code",
    "duration_min",
]


def night_date_of(start_at: pd.Series[pd.Timestamp]) -> pd.Series[pd.Timestamp]:
    """Return the date a night belongs to: the local day of sleep onset minus 12 hours.

    A night that starts at 02:00 on Saturday belongs to Friday, the evening it
    follows. A nap at 15:00 belongs to its own day.

    Args:
        start_at: Sleep onset in local time.

    Returns:
        The date, as midnight of that day.
    """
    return (start_at - pd.Timedelta(hours=12)).dt.normalize()


def _fragments(source: Source, issues: list[ValidationIssue]) -> pd.DataFrame:
    """Read the sleep fragments that count: valid, with a duration and not partial.

    Args:
        source: The export.
        issues: List the issues are appended to.

    Returns:
        One row per fragment with its group id and numeric measures.
    """
    raw = source.read("sleep")
    require_columns(raw, "sleep", ["sleep_duration"])
    frame = prepare_timed(
        raw,
        samsung_table="sleep",
        table="sleep_session",
        exported_at=source.exported_at,
        issues=issues,
    )
    frame = frame[text_column(frame, "integrated_id").isna()].reset_index(drop=True)
    frame["duration_min"] = to_number(frame["sleep_duration"])
    no_duration = frame["duration_min"].isna()
    report(
        issues,
        frame,
        no_duration,
        table="sleep_session",
        rule="missing_duration",
        value=frame["start_time"],
    )
    frame = frame[~no_duration].reset_index(drop=True)
    frame = reject_out_of_range(
        frame,
        ["duration_min"],
        VALID_RANGES["sleep_duration_min"],
        table="sleep_session",
        rule="duration_out_of_range",
        issues=issues,
    )
    frame["group_id"] = text_column(frame, "combined_id").fillna(frame["samsung_id"])
    for samsung_name, name in SCORE_COLUMNS.items():
        frame[name] = number_column(frame, samsung_name)
    frame["latency_min"] = number_column(frame, "sleep_latency") / 60_000
    frame["light_min"] = number_column(frame, "total_light_duration")
    frame["rem_min"] = number_column(frame, "total_rem_duration")
    return frame


def _combined_scores(source: Source) -> pd.DataFrame:
    """Read the scores Samsung computed for nights made of several fragments.

    Args:
        source: The export.

    Returns:
        One row per combined night, indexed by its id; empty when the export has
        no ``sleep_combined`` table.
    """
    if not source.has("sleep_combined"):
        return pd.DataFrame()
    raw = source.read("sleep_combined")
    require_columns(raw, "sleep_combined", ["datauuid"])
    scores = pd.DataFrame(index=pd.Index(raw["datauuid"], name="group_id"))
    for samsung_name, name in SCORE_COLUMNS.items():
        scores[name] = number_column(raw, samsung_name).to_numpy()
    scores["latency_min"] = (number_column(raw, "sleep_latency") / 60_000).to_numpy()
    scores["light_min"] = number_column(raw, "total_light_duration").to_numpy()
    scores["rem_min"] = number_column(raw, "total_rem_duration").to_numpy()
    return scores[~scores.index.duplicated(keep="last")]


def _sessions(fragments: pd.DataFrame, combined: pd.DataFrame) -> pd.DataFrame:
    """Group fragments into sessions.

    A session spans from its first fragment's start to its last fragment's end
    and lasts the sum of its fragments. Its scores come from ``sleep_combined``
    when Samsung grouped it, and from its longest fragment otherwise.

    Args:
        fragments: Output of ``_fragments``.
        combined: Output of ``_combined_scores``.

    Returns:
        One row per session, with the columns of ``sleep_session``.
    """
    measures = [*SCORE_COLUMNS.values(), "latency_min", "light_min", "rem_min"]
    ordered = fragments.sort_values(["group_id", "start_at"])
    groups = ordered.groupby("group_id", sort=True)
    sessions = groups.agg(
        start_at=("start_at", "min"),
        end_at=("end_at", "max"),
        utc_offset_min=("utc_offset_min", "first"),
        duration_min=("duration_min", "sum"),
        fragment_count=("duration_min", "size"),
    )
    longest = fragments.sort_values("duration_min").drop_duplicates("group_id", keep="last")
    sessions = sessions.join(longest.set_index("group_id")[measures])
    grouped_by_samsung = sessions.index.intersection(combined.index)
    if len(grouped_by_samsung):
        sessions.loc[grouped_by_samsung, measures] = combined.loc[grouped_by_samsung, measures]
    sessions = sessions.reset_index(names="samsung_id")
    sessions["night_date"] = night_date_of(sessions["start_at"])
    sessions["is_night"] = sessions["duration_min"] > THRESHOLDS.night_min_duration_min
    return sessions.sort_values("start_at")[SESSION_COLUMNS].reset_index(drop=True)


def _stages(source: Source, fragments: pd.DataFrame, issues: list[ValidationIssue]) -> pd.DataFrame:
    """Read the stages of the fragments that count and attach them to their session.

    Stages of dropped fragments are left out without an issue: they repeat time
    another fragment already covers.

    Args:
        source: The export.
        fragments: Output of ``_fragments``.
        issues: List the issues are appended to.

    Returns:
        One row per stage, with the columns of ``sleep_stage``.
    """
    raw = source.read("sleep_stage")
    require_columns(raw, "sleep_stage", ["sleep_id", "stage"])
    frame = prepare_timed(
        raw,
        samsung_table="sleep_stage",
        table="sleep_stage",
        exported_at=source.exported_at,
        issues=issues,
    )
    session_of = fragments.set_index("samsung_id")["group_id"]
    frame["session_id"] = frame["sleep_id"].map(session_of)
    frame = frame[frame["session_id"].notna()].reset_index(drop=True)
    code = to_number(frame["stage"])
    unknown = ~code.isin(KNOWN_STAGES)
    report(
        issues,
        frame,
        unknown,
        table="sleep_stage",
        rule="unknown_stage_code",
        value=frame["stage"],
        action=KEPT,
    )
    frame["stage_code"] = code.astype("Int64")
    frame["duration_min"] = (frame["end_at"] - frame["start_at"]).dt.total_seconds() / 60
    return frame.sort_values(["session_id", "start_at"])[STAGE_COLUMNS].reset_index(drop=True)


def transform_sleep(source: Source) -> DomainResult:
    """Build ``sleep_session`` and ``sleep_stage`` from an export.

    Args:
        source: The export.

    Returns:
        The two tables and the issues found.

    Raises:
        TableMissingError: If the export lacks ``sleep`` or ``sleep_stage``.
        TransformError: If a required column is missing.
    """
    result = DomainResult()
    fragments = _fragments(source, result.issues)
    result.tables["sleep_session"] = _sessions(fragments, _combined_scores(source))
    result.tables["sleep_stage"] = _stages(source, fragments, result.issues)
    return result
