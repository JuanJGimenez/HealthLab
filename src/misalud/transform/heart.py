"""Heart domain: per-minute heart rate, variability windows, stress and ECG records."""

from __future__ import annotations

from misalud.config import VALID_RANGES
from misalud.transform.common import (
    DomainResult,
    Source,
    drop_out_of_range_points,
    expand_details,
    number_column,
    prepare_timed,
    require_columns,
    text_column,
    unique_by_utc_start,
)


def transform_heart_rate(source: Source) -> DomainResult:
    """Build ``heart_rate_minute`` from an export.

    Each row of Samsung's table covers about an hour and names a file with one
    measurement per minute. Rows without a file are manual spot readings and are
    not part of the series.

    Args:
        source: The export.

    Returns:
        One row per minute and the issues found.

    Raises:
        TableMissingError: If the export lacks the table.
        TransformError: If a required column is missing.
    """
    result = DomainResult()
    raw = source.read("tracker.heart_rate")
    require_columns(raw, "tracker.heart_rate", ["binning_data"])
    hours = prepare_timed(
        raw,
        samsung_table="tracker.heart_rate",
        table="heart_rate_minute",
        exported_at=source.exported_at,
        issues=result.issues,
    )
    points = expand_details(
        source,
        hours,
        samsung_table="tracker.heart_rate",
        table="heart_rate_minute",
        file_column="binning_data",
        fields={
            "heart_rate": "heart_rate",
            "heart_rate_min": "heart_rate_min",
            "heart_rate_max": "heart_rate_max",
        },
        issues=result.issues,
    )
    points = drop_out_of_range_points(
        points,
        "heart_rate",
        VALID_RANGES["heart_rate_bpm"],
        table="heart_rate_minute",
        rule="heart_rate_out_of_range",
        issues=result.issues,
    )
    result.tables["heart_rate_minute"] = unique_by_utc_start(points)
    return result


def transform_hrv(source: Source) -> DomainResult:
    """Build ``hrv_window`` from an export.

    Args:
        source: The export.

    Returns:
        One row per variability window and the issues found.

    Raises:
        TableMissingError: If the export lacks the table.
        TransformError: If a required column is missing.
    """
    result = DomainResult()
    raw = source.read("hrv")
    require_columns(raw, "hrv", ["binning_data"])
    hours = prepare_timed(
        raw,
        samsung_table="hrv",
        table="hrv_window",
        exported_at=source.exported_at,
        issues=result.issues,
    )
    points = expand_details(
        source,
        hours,
        samsung_table="hrv",
        table="hrv_window",
        file_column="binning_data",
        fields={"rmssd": "rmssd_ms", "sdnn": "sdnn_ms"},
        issues=result.issues,
        with_end=True,
    )
    result.tables["hrv_window"] = unique_by_utc_start(points)
    return result


def transform_stress(source: Source) -> DomainResult:
    """Build ``stress`` from an export.

    Args:
        source: The export.

    Returns:
        One row per stress measurement and the issues found.

    Raises:
        TableMissingError: If the export lacks the table.
        TransformError: If a required column is missing.
    """
    result = DomainResult()
    raw = source.read("stress")
    require_columns(raw, "stress", ["score"])
    rows = prepare_timed(
        raw,
        samsung_table="stress",
        table="stress",
        exported_at=source.exported_at,
        issues=result.issues,
    )
    rows["score"] = number_column(rows, "score")
    rows["score_min"] = number_column(rows, "min")
    rows["score_max"] = number_column(rows, "max")
    columns = [
        "samsung_id",
        "start_at",
        "end_at",
        "utc_offset_min",
        "score",
        "score_min",
        "score_max",
    ]
    result.tables["stress"] = rows.sort_values("start_at")[columns].reset_index(drop=True)
    return result


def transform_ecg(source: Source) -> DomainResult:
    """Build ``ecg`` from an export.

    Args:
        source: The export.

    Returns:
        One row per electrocardiogram and the issues found. ``trace_file`` names
        the file with the full trace; the trace itself is not loaded here.

    Raises:
        TableMissingError: If the export lacks the table.
        TransformError: If a required column is missing.
    """
    result = DomainResult()
    raw = source.read("ecg")
    rows = prepare_timed(
        raw, samsung_table="ecg", table="ecg", exported_at=source.exported_at, issues=result.issues
    )
    rows["mean_hr"] = number_column(rows, "mean_heart_rate")
    rows["classification_code"] = number_column(rows, "classification").astype("Int64")
    rows["sample_frequency_hz"] = number_column(rows, "sample_frequency").astype("Int64")
    rows["sample_count"] = number_column(rows, "sample_count").astype("Int64")
    rows["trace_file"] = text_column(rows, "chart_data")
    columns = [
        "samsung_id",
        "start_at",
        "utc_offset_min",
        "mean_hr",
        "classification_code",
        "sample_frequency_hz",
        "sample_count",
        "trace_file",
    ]
    result.tables["ecg"] = rows.sort_values("start_at")[columns].reset_index(drop=True)
    return result
