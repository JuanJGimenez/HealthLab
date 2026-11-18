"""Gather everything the report shows, as plain data.

Keeping the figures apart from the page lets the tests check every number
without reading a PDF.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import date, datetime
from types import MappingProxyType
from typing import Any, Final

from misalud.annotations.store import list_tags
from misalud.queries import days as day_queries
from misalud.queries import nights as night_queries
from misalud.queries import report as report_queries
from misalud.queries.common import Period, Record
from misalud.queries.day_detail import hourly_profile
from misalud.queries.night_detail import NightDetail, night_detail
from misalud.storage.database import Connection

MAX_DETAIL_NIGHTS: Final = 2
"""Nights the report can show track by track."""


@dataclass(frozen=True, slots=True)
class Cross:
    """Two measures to relate in the "day and night" block.

    Attributes:
        x: Metric on the horizontal axis, from ``RELATE_METRICS``.
        y: Metric on the vertical axis.
        x_label: Name of ``x`` in the language of the report.
        y_label: Name of ``y`` in the language of the report.
    """

    x: str
    y: str
    x_label: str
    y_label: str


@dataclass(frozen=True, slots=True)
class PersonalData:
    """What the user chose to print about themselves; any field may be missing.

    Attributes:
        name: Name as the user wrote it.
        age: Age in years on the day the report is made.
        sex: Sex as the user wrote it.
        height_cm: Height in centimetres.
        weight_kg: Weight in kilograms.
    """

    name: str | None = None
    age: int | None = None
    sex: str | None = None
    height_cm: float | None = None
    weight_kg: float | None = None


@dataclass(frozen=True, slots=True)
class ReportOptions:
    """What the user asked the report to cover.

    Attributes:
        period: Dates to include.
        language: ``es`` or ``en``.
        generated_at: Moment printed as the date of the report.
        watch_model: Watch model to print, when the user gave one.
        personal: Personal data to print, or ``None`` to leave it out.
        blocks: Optional blocks to add, names from ``BLOCKS``.
        crosses: Relations to draw in the "day and night" block.
        detail_nights: Up to two nights to show track by track.
    """

    period: Period
    language: str
    generated_at: datetime
    watch_model: str | None = None
    personal: PersonalData | None = None
    blocks: tuple[str, ...] = ()
    crosses: tuple[Cross, ...] = ()
    detail_nights: tuple[date, ...] = ()


@dataclass(frozen=True, slots=True)
class ReportContent:
    """Every figure of the base report.

    Attributes:
        options: What the user asked for.
        summary: One-page summary (``report_summary``).
        series: Minutes under 90 % night by night.
        top_nights: The ten nights with the most time under 90 %.
        weekdays: Share of nights with a sustained drop by weekday.
        tag_patterns: The same share with and without each tag.
        blocks: Figures of each optional block that was asked for, by name.
        details: The nights to show track by track that exist, in the order asked.
    """

    options: ReportOptions
    summary: Record
    series: list[Record]
    top_nights: list[Record]
    weekdays: Record
    tag_patterns: list[Record]
    blocks: dict[str, Any] = field(default_factory=dict)
    details: list[NightDetail] = field(default_factory=list)


def _heart(connection: Connection, options: ReportOptions) -> Any:
    """Night pulse and variability with their trends, and the electrocardiograms."""
    period = options.period
    return {
        "overview": night_queries.overview(connection, period),
        "nights": night_queries.list_nights(connection, period),
        "pulse_trend": night_queries.rolling_median(connection, "night_hr_avg", period),
        "hrv_trend": night_queries.rolling_median(connection, "hrv_rmssd_ms", period),
        "ecg": report_queries.ecg_list(connection, period),
    }


def _sleep(connection: Connection, options: ReportOptions) -> Any:
    """Hours, efficiency and stages: period averages and month by month."""
    stages = ["deep_min", "rem_min", "light_min", "awake_min"]
    return {
        "averages": report_queries.night_averages(
            connection, ["asleep_hours", "efficiency_pct", *stages], options.period
        ),
        "months": night_queries.nights_by_month(
            connection, ["hours", "asleep_hours", *stages[:3]], options.period
        ),
    }


def _snoring(connection: Connection, options: ReportOptions) -> Any:
    """Nights with snoring recorded, median and maximum, and the nightly series."""
    nights = night_queries.list_nights(connection, options.period)
    return {
        "stats": report_queries.night_metric_stats(connection, "snoring_min", options.period),
        "series": [
            {"night_date": night["night_date"], "snoring_min": night["snoring_min"]}
            for night in nights
            if night["snoring_min"] is not None
        ],
    }


def _activity(connection: Connection, options: ReportOptions) -> Any:
    """Steps, active minutes and recorded exercise, steps by month and pulse by hour."""
    days = Period(options.period.start, options.period.end)
    return {
        "averages": report_queries.day_averages(
            connection, ["steps", "active_min", "exercise_min"], days
        ),
        "months": day_queries.days_by_month(connection, ["steps"], days),
        "hourly": hourly_profile(connection, days)["pulse"],
    }


def _day_night(connection: Connection, options: ReportOptions) -> Any:
    """Each relation the user chose, with its points and its correlation."""
    return [
        {"cross": cross, **night_queries.relate(connection, cross.x, cross.y, options.period)}
        for cross in options.crosses
    ]


def _annotations(connection: Connection, options: ReportOptions) -> Any:
    """Nights with and without each tag that has at least one tagged night."""
    rows = []
    for tag in list_tags(connection, include_inactive=True):
        comparison = night_queries.tag_comparison(connection, tag["tag_id"], options.period)
        if comparison["with"]["nights"]:
            rows.append({"tag": tag, **comparison})
    return rows


BLOCKS: Final[MappingProxyType[str, Callable[[Connection, ReportOptions], Any]]] = MappingProxyType(
    {
        "heart": _heart,
        "sleep": _sleep,
        "snoring": _snoring,
        "activity": _activity,
        "day_night": _day_night,
        "annotations": _annotations,
    }
)
"""The optional blocks, by name, in the order they are printed."""


def gather_report(connection: Connection, options: ReportOptions) -> ReportContent:
    """Read the figures of the report from the database.

    Args:
        connection: An open connection.
        options: What the user asked for.

    Returns:
        The content, ready to be laid out.

    Raises:
        ValueError: If a block is unknown or more than two detail nights are asked.
    """
    unknown = sorted(set(options.blocks) - set(BLOCKS))
    if unknown:
        msg = f"unknown report blocks: {', '.join(unknown)}"
        raise ValueError(msg)
    if len(options.detail_nights) > MAX_DETAIL_NIGHTS:
        msg = f"the report shows at most {MAX_DETAIL_NIGHTS} nights in detail"
        raise ValueError(msg)
    period = options.period
    details = [night_detail(connection, day) for day in options.detail_nights]
    return ReportContent(
        options=options,
        summary=report_queries.report_summary(connection, period),
        series=report_queries.low_minutes_series(connection, period),
        top_nights=report_queries.top_nights(connection, period),
        weekdays=night_queries.sustained_low_by_weekday(connection, period),
        tag_patterns=report_queries.tag_patterns(connection, period),
        blocks={
            name: build(connection, options)
            for name, build in BLOCKS.items()
            if name in options.blocks
        },
        details=[detail for detail in details if detail is not None],
    )
