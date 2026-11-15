"""Activity domain: exercise, weight, steps, daily activity, energy score and movement."""

from __future__ import annotations

from typing import Final

import pandas as pd

from misalud.reading.errors import DetailFileError
from misalud.transform.common import (
    KEPT,
    DomainResult,
    Source,
    ValidationIssue,
    expand_details,
    number_column,
    prepare_daily,
    prepare_timed,
    require_columns,
    text_column,
    unique_by_utc_start,
)

DAY_TOTAL_SOURCE: Final = "-2"
"""``source_type`` of the row that holds the total steps of a day."""

INTERVALS_PER_DAY: Final = 144
INTERVAL_MINUTES: Final = 10
MS_PER_MINUTE: Final = 60_000


def transform_exercise(source: Source) -> DomainResult:
    """Build ``exercise`` from an export.

    Args:
        source: The export.

    Returns:
        One row per recorded session and the issues found.

    Raises:
        TableMissingError: If the export lacks the table.
        TransformError: If a required column is missing.
    """
    result = DomainResult()
    raw = source.read("exercise")
    require_columns(raw, "exercise", ["exercise_type", "duration"])
    rows = prepare_timed(
        raw,
        samsung_table="exercise",
        table="exercise",
        exported_at=source.exported_at,
        issues=result.issues,
    )
    rows["duration_min"] = number_column(rows, "duration") / MS_PER_MINUTE
    rows["type_code"] = number_column(rows, "exercise_type").astype("Int64")
    rows["custom_id"] = text_column(rows, "custom_id")
    names = {
        "calorie": "calorie_kcal",
        "distance": "distance_m",
        "mean_heart_rate": "mean_hr",
        "max_heart_rate": "max_hr",
        "min_heart_rate": "min_hr",
        "mean_speed": "mean_speed_mps",
        "vo2_max": "vo2_max",
    }
    for samsung_name, name in names.items():
        rows[name] = number_column(rows, samsung_name)
    columns = [
        "samsung_id",
        "start_at",
        "end_at",
        "utc_offset_min",
        "duration_min",
        "type_code",
        "custom_id",
        *names.values(),
    ]
    result.tables["exercise"] = rows.sort_values("start_at")[columns].reset_index(drop=True)
    return result


def transform_weight(source: Source) -> DomainResult:
    """Build ``weight`` from an export.

    Args:
        source: The export.

    Returns:
        One row per weight measurement and the issues found.

    Raises:
        TableMissingError: If the export lacks the table.
        TransformError: If a required column is missing.
    """
    result = DomainResult()
    raw = source.read("weight")
    require_columns(raw, "weight", ["weight"])
    rows = prepare_timed(
        raw,
        samsung_table="weight",
        table="weight",
        exported_at=source.exported_at,
        issues=result.issues,
        with_end=False,
    )
    rows["measured_at"] = rows["start_at"]
    names = {
        "weight": "weight_kg",
        "height": "height_cm",
        "body_fat": "body_fat_pct",
        "skeletal_muscle_mass": "skeletal_muscle_mass_kg",
        "basal_metabolic_rate": "basal_metabolic_rate_kcal",
    }
    for samsung_name, name in names.items():
        rows[name] = number_column(rows, samsung_name)
    columns = ["samsung_id", "measured_at", "utc_offset_min", *names.values()]
    result.tables["weight"] = rows.sort_values("measured_at")[columns].reset_index(drop=True)
    return result


def _numbers(frame: pd.DataFrame, name: str) -> pd.Series[float]:
    """Return a column of a detail file as numbers, or missing values when absent."""
    if name not in frame.columns:
        return pd.Series(float("nan"), index=frame.index, dtype="float64")
    return pd.to_numeric(frame[name], errors="coerce").astype("float64")


def _step_intervals(
    source: Source, days: pd.DataFrame, issues: list[ValidationIssue]
) -> pd.DataFrame:
    """Read the 10-minute step counts of each day.

    The detail file of a day holds 144 entries in order, without times: entry
    ``i`` covers the 10 minutes that start ``10 * i`` minutes after midnight.

    A day whose file is missing, unreadable or does not hold 144 entries is
    reported and gets no intervals; its daily total is not affected.

    Args:
        source: The export.
        days: Rows with ``samsung_id``, ``day`` and ``binning_data``.
        issues: List the issues are appended to.

    Returns:
        One row per interval with the columns of ``steps_interval``.
    """
    frames = []
    offsets = pd.to_timedelta(
        range(0, INTERVALS_PER_DAY * INTERVAL_MINUTES, INTERVAL_MINUTES), unit="m"
    )
    rows = days.loc[days["binning_data"].notna(), ["samsung_id", "day", "binning_data"]]
    for ident, day, file_name in rows.itertuples(index=False, name=None):
        try:
            content = source.detail("step_daily_trend", file_name)
        except DetailFileError:
            issues.append(
                ValidationIssue("steps_interval", ident, "detail_file_unreadable", file_name, KEPT)
            )
            continue
        if not isinstance(content, list) or len(content) != INTERVALS_PER_DAY:
            size = str(len(content)) if isinstance(content, list) else "not a list"
            issues.append(
                ValidationIssue("steps_interval", ident, "unexpected_interval_count", size, KEPT)
            )
            continue
        frame = pd.DataFrame(content)
        frames.append(
            pd.DataFrame(
                {
                    "day": day,
                    "interval": range(INTERVALS_PER_DAY),
                    "start_at": day + offsets,
                    "steps": _numbers(frame, "count"),
                    "distance_m": _numbers(frame, "distance"),
                    "calorie_kcal": _numbers(frame, "calorie"),
                }
            )
        )
    if not frames:
        columns = ["day", "interval", "start_at", "steps", "distance_m", "calorie_kcal"]
        return pd.DataFrame({name: [] for name in columns}).astype(
            {"day": "datetime64[ns]", "start_at": "datetime64[ns]"}
        )
    return pd.concat(frames, ignore_index=True)


def transform_steps(source: Source) -> DomainResult:
    """Build ``steps_day`` and ``steps_interval`` from an export.

    Samsung writes several rows per day; the one with ``source_type`` -2 is the
    total and the others are partial sources that must not be added to it.

    Args:
        source: The export.

    Returns:
        The daily totals, their 10-minute intervals and the issues found.

    Raises:
        TableMissingError: If the export lacks the table.
        TransformError: If a required column is missing.
    """
    result = DomainResult()
    raw = source.read("step_daily_trend")
    require_columns(raw, "step_daily_trend", ["source_type", "count"])
    totals = raw[raw["source_type"] == DAY_TOTAL_SOURCE]
    days = prepare_daily(
        totals,
        samsung_table="step_daily_trend",
        table="steps_day",
        exported_at=source.exported_at,
        issues=result.issues,
    )
    days["steps"] = number_column(days, "count")
    days["distance_m"] = number_column(days, "distance")
    days["calorie_kcal"] = number_column(days, "calorie")
    days["binning_data"] = text_column(days, "binning_data")
    result.tables["steps_day"] = days[["samsung_id", "day", "steps", "distance_m", "calorie_kcal"]]
    result.tables["steps_interval"] = _step_intervals(source, days, result.issues)
    return result


def transform_activity_summary(source: Source) -> DomainResult:
    """Build ``activity_day`` from an export.

    Args:
        source: The export.

    Returns:
        One row per day and the issues found. Samsung stores durations in
        milliseconds; they are converted to minutes.

    Raises:
        TableMissingError: If the export lacks the table.
        TransformError: If a required column is missing.
    """
    result = DomainResult()
    raw = source.read("activity.day_summary")
    days = prepare_daily(
        raw,
        samsung_table="activity.day_summary",
        table="activity_day",
        exported_at=source.exported_at,
        issues=result.issues,
    )
    days["steps"] = number_column(days, "step_count")
    for samsung_name, name in {
        "active_time": "active_min",
        "walk_time": "walk_min",
        "run_time": "run_min",
        "exercise_time": "exercise_min",
    }.items():
        days[name] = number_column(days, samsung_name) / MS_PER_MINUTE
    days["distance_m"] = number_column(days, "distance")
    days["active_calorie_kcal"] = number_column(days, "calorie")
    days["floors"] = number_column(days, "floor_count")
    columns = [
        "samsung_id",
        "day",
        "steps",
        "active_min",
        "walk_min",
        "run_min",
        "exercise_min",
        "distance_m",
        "active_calorie_kcal",
        "floors",
    ]
    result.tables["activity_day"] = days[columns]
    return result


def transform_vitality(source: Source) -> DomainResult:
    """Build ``vitality_day`` from an export.

    Args:
        source: The export.

    Returns:
        One row per day with Samsung's energy score and the issues found.

    Raises:
        TableMissingError: If the export lacks the table.
        TransformError: If a required column is missing.
    """
    result = DomainResult()
    raw = source.read("vitality_score")
    require_columns(raw, "vitality_score", ["total_score"])
    days = prepare_daily(
        raw,
        samsung_table="vitality_score",
        table="vitality_day",
        exported_at=source.exported_at,
        issues=result.issues,
    )
    days["energy_score"] = number_column(days, "total_score")
    days["sleeping_hr"] = number_column(days, "shr_value")
    days["sleeping_hrv_ms"] = number_column(days, "shrv_value")
    result.tables["vitality_day"] = days[
        ["samsung_id", "day", "energy_score", "sleeping_hr", "sleeping_hrv_ms"]
    ]
    return result


def transform_movement(source: Source) -> DomainResult:
    """Build ``movement_minute`` from an export.

    Args:
        source: The export.

    Returns:
        One row per minute with Samsung's movement level and the issues found.

    Raises:
        TableMissingError: If the export lacks the table.
        TransformError: If a required column is missing.
    """
    result = DomainResult()
    raw = source.read("movement")
    require_columns(raw, "movement", ["binning_data"])
    hours = prepare_timed(
        raw,
        samsung_table="movement",
        table="movement_minute",
        exported_at=source.exported_at,
        issues=result.issues,
    )
    points = expand_details(
        source,
        hours,
        samsung_table="movement",
        table="movement_minute",
        file_column="binning_data",
        fields={"activity_level": "activity_level"},
        issues=result.issues,
    )
    result.tables["movement_minute"] = unique_by_utc_start(points)
    return result
