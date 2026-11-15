"""Signals the watch records during sleep: skin temperature, breathing and snoring.

Samsung does not link these records to a sleep session. They are stored as they
come; the ``derived`` layer attaches them to a night by time window.
"""

from __future__ import annotations

from typing import Final

import pandas as pd

from misalud.config import VALID_RANGES
from misalud.transform.common import (
    KEPT,
    DomainResult,
    Source,
    drop_out_of_range_points,
    expand_details,
    number_column,
    prepare_timed,
    reject_out_of_range,
    reject_repeated_spans,
    report,
    require_columns,
    text_column,
    unique_within_parent,
)

TRUE_TEXTS: Final = frozenset({"true", "1"})
FALSE_TEXTS: Final = frozenset({"false", "0"})


def to_boolean(values: pd.Series[str]) -> pd.Series[bool]:
    """Convert ``True``/``False`` or ``1``/``0`` text to booleans; anything else is missing.

    Args:
        values: A column read as text.

    Returns:
        The column as nullable booleans.
    """
    lowered = values.str.lower()
    result = pd.Series(pd.NA, index=values.index, dtype="boolean")
    result[lowered.isin(TRUE_TEXTS)] = True
    result[lowered.isin(FALSE_TEXTS)] = False
    return result


def transform_skin_temperature(source: Source) -> DomainResult:
    """Build ``skin_temperature`` and ``skin_temperature_minute`` from an export.

    Args:
        source: The export.

    Returns:
        The night summary, its per-minute series and the issues found.

    Raises:
        TableMissingError: If the export lacks the table.
        TransformError: If a required column is missing.
    """
    result = DomainResult()
    raw = source.read("skin_temperature")
    require_columns(raw, "skin_temperature", ["temperature"])
    nights = prepare_timed(
        raw,
        samsung_table="skin_temperature",
        table="skin_temperature",
        exported_at=source.exported_at,
        issues=result.issues,
    )
    nights = reject_repeated_spans(nights, table="skin_temperature", issues=result.issues)
    names = {
        "temperature": "temperature_c",
        "baseline": "baseline_c",
        "min": "min_c",
        "max": "max_c",
        "lower_bound": "lower_bound_c",
        "upper_bound": "upper_bound_c",
    }
    for samsung_name, name in names.items():
        nights[name] = number_column(nights, samsung_name)
    nights = reject_out_of_range(
        nights,
        ["temperature_c"],
        VALID_RANGES["skin_temperature_c"],
        table="skin_temperature",
        rule="temperature_out_of_range",
        issues=result.issues,
    )
    points = expand_details(
        source,
        nights.assign(binning_data=text_column(nights, "binning_data")),
        samsung_table="skin_temperature",
        table="skin_temperature_minute",
        file_column="binning_data",
        fields={"mean": "mean_c", "min": "min_c", "max": "max_c"},
        issues=result.issues,
    )
    points = drop_out_of_range_points(
        points,
        "mean_c",
        VALID_RANGES["skin_temperature_c"],
        table="skin_temperature_minute",
        rule="temperature_out_of_range",
        issues=result.issues,
    )
    points = unique_within_parent(points).rename(columns={"parent_id": "night_samsung_id"})
    columns = ["samsung_id", "start_at", "end_at", "utc_offset_min", *names.values()]
    result.tables["skin_temperature"] = nights.sort_values("start_at")[columns].reset_index(
        drop=True
    )
    result.tables["skin_temperature_minute"] = points
    return result


def transform_respiratory_rate(source: Source) -> DomainResult:
    """Build ``respiratory_rate`` and ``respiratory_rate_minute`` from an export.

    Samsung writes 0 when it has no measurement, both in the night average and in
    the per-minute series. Those values are stored as missing; a night whose
    average is 0 is kept, with a notice, because its other columns still hold.

    Args:
        source: The export.

    Returns:
        The night summary, its per-minute series and the issues found.

    Raises:
        TableMissingError: If the export lacks the table.
        TransformError: If a required column is missing.
    """
    result = DomainResult()
    raw = source.read("respiratory_rate")
    require_columns(raw, "respiratory_rate", ["average"])
    nights = prepare_timed(
        raw,
        samsung_table="respiratory_rate",
        table="respiratory_rate",
        exported_at=source.exported_at,
        issues=result.issues,
    )
    nights = reject_repeated_spans(nights, table="respiratory_rate", issues=result.issues)
    nights["rate_avg"] = number_column(nights, "average")
    nights["lower_limit"] = number_column(nights, "lower_limit")
    nights["upper_limit"] = number_column(nights, "upper_limit")
    nights["is_outlier"] = to_boolean(text_column(nights, "is_outlier"))
    no_measurement = nights["rate_avg"] == 0
    report(
        result.issues,
        nights,
        no_measurement,
        table="respiratory_rate",
        rule="no_measurement",
        value=nights["average"],
        action=KEPT,
    )
    nights["rate_avg"] = nights["rate_avg"].where(~no_measurement)
    nights = reject_out_of_range(
        nights,
        ["rate_avg"],
        VALID_RANGES["respiratory_rate_bpm"],
        table="respiratory_rate",
        rule="rate_out_of_range",
        issues=result.issues,
    )
    points = expand_details(
        source,
        nights.assign(binning_data=text_column(nights, "binning_data")),
        samsung_table="respiratory_rate",
        table="respiratory_rate_minute",
        file_column="binning_data",
        fields={"respiratory_rate": "rate"},
        issues=result.issues,
    )
    points["rate"] = points["rate"].where(points["rate"] != 0)
    points = drop_out_of_range_points(
        points,
        "rate",
        VALID_RANGES["respiratory_rate_bpm"],
        table="respiratory_rate_minute",
        rule="rate_out_of_range",
        issues=result.issues,
    )
    points = unique_within_parent(points).rename(columns={"parent_id": "night_samsung_id"})
    columns = [
        "samsung_id",
        "start_at",
        "end_at",
        "utc_offset_min",
        "rate_avg",
        "lower_limit",
        "upper_limit",
        "is_outlier",
    ]
    result.tables["respiratory_rate"] = nights.sort_values("start_at")[columns].reset_index(
        drop=True
    )
    result.tables["respiratory_rate_minute"] = points
    return result


def transform_snoring(source: Source) -> DomainResult:
    """Build ``snoring_event`` from an export.

    Args:
        source: The export.

    Returns:
        One row per snoring event and the issues found. The real export carries a
        few events dated 1970, which are rejected.

    Raises:
        TableMissingError: If the export lacks the table.
        TransformError: If a required column is missing.
    """
    result = DomainResult()
    raw = source.read("sleep_snoring")
    require_columns(raw, "sleep_snoring", ["duration"])
    events = prepare_timed(
        raw,
        samsung_table="sleep_snoring",
        table="snoring_event",
        exported_at=source.exported_at,
        issues=result.issues,
    )
    events["duration_s"] = number_column(events, "duration") / 1000
    columns = ["samsung_id", "start_at", "end_at", "utc_offset_min", "duration_s"]
    result.tables["snoring_event"] = events.sort_values("start_at")[columns].reset_index(drop=True)
    return result
