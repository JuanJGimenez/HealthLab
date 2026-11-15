"""Oxygen domain: the overnight summary and its 10-minute intervals.

Samsung stores two kinds of rows in the oxygen table, told apart by ``tag_id``:
overnight records (31301) and manual spot measurements (31000). Only overnight
records feed MiSalud.
"""

from __future__ import annotations

from typing import Final

import pandas as pd

from misalud.config import VALID_RANGES
from misalud.transform.common import (
    DomainResult,
    Source,
    drop_out_of_range_points,
    expand_details,
    number_column,
    prepare_timed,
    reject_out_of_range,
    require_columns,
)

OVERNIGHT_TAG: Final = "31301"

NIGHT_COLUMNS: Final = [
    "samsung_id",
    "start_at",
    "end_at",
    "utc_offset_min",
    "spo2_avg",
    "spo2_min",
    "spo2_max",
    "low_seconds",
    "coverage_pct",
]

INTERVAL_COLUMNS: Final = [
    "night_samsung_id",
    "start_utc",
    "start_at",
    "end_at",
    "spo2_avg",
    "spo2_min",
    "spo2_max",
    "is_irregular",
]


def transform_oxygen(source: Source) -> DomainResult:
    """Build ``spo2_night`` and ``spo2_interval`` from an export.

    Args:
        source: The export.

    Returns:
        The two tables and the issues found.

    Raises:
        TableMissingError: If the export lacks the oxygen table.
        TransformError: If a required column is missing.
    """
    result = DomainResult()
    raw = source.read("tracker.oxygen_saturation")
    require_columns(raw, "tracker.oxygen_saturation", ["tag_id", "spo2", "min", "max", "binning"])
    overnight = raw[raw["tag_id"] == OVERNIGHT_TAG]
    nights = prepare_timed(
        overnight,
        samsung_table="tracker.oxygen_saturation",
        table="spo2_night",
        exported_at=source.exported_at,
        issues=result.issues,
    )
    nights["spo2_avg"] = number_column(nights, "spo2")
    nights["spo2_min"] = number_column(nights, "min")
    nights["spo2_max"] = number_column(nights, "max")
    nights["low_seconds"] = number_column(nights, "low_duration")
    nights["coverage_pct"] = number_column(nights, "coverage_rate")
    nights = reject_out_of_range(
        nights,
        ["spo2_avg", "spo2_min", "spo2_max"],
        VALID_RANGES["spo2_pct"],
        table="spo2_night",
        rule="spo2_out_of_range",
        issues=result.issues,
    )

    points = expand_details(
        source,
        nights,
        samsung_table="tracker.oxygen_saturation",
        table="spo2_interval",
        file_column="binning",
        fields={
            "spo2": "spo2_avg",
            "spo2_min": "spo2_min",
            "spo2_max": "spo2_max",
            "isIrregular": "irregular",
        },
        issues=result.issues,
        with_end=True,
    )
    for column in ("spo2_avg", "spo2_min", "spo2_max"):
        points = drop_out_of_range_points(
            points,
            column,
            VALID_RANGES["spo2_pct"],
            table="spo2_interval",
            rule="spo2_out_of_range",
            issues=result.issues,
        )
    points["is_irregular"] = points["irregular"].map({0.0: False, 1.0: True}).astype("boolean")
    points = points.rename(columns={"parent_id": "night_samsung_id"})

    result.tables["spo2_night"] = nights.sort_values("start_at")[NIGHT_COLUMNS].reset_index(
        drop=True
    )
    result.tables["spo2_interval"] = pd.DataFrame(points[INTERVAL_COLUMNS]).reset_index(drop=True)
    return result
