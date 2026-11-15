"""Gather everything the report shows, as plain data.

Keeping the figures apart from the page lets the tests check every number
without reading a PDF.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from misalud.queries import nights as night_queries
from misalud.queries import report as report_queries
from misalud.queries.common import Period, Record
from misalud.storage.database import Connection


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
    """

    period: Period
    language: str
    generated_at: datetime
    watch_model: str | None = None
    personal: PersonalData | None = None


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
    """

    options: ReportOptions
    summary: Record
    series: list[Record]
    top_nights: list[Record]
    weekdays: Record
    tag_patterns: list[Record]


def gather_report(connection: Connection, options: ReportOptions) -> ReportContent:
    """Read the figures of the report from the database.

    Args:
        connection: An open connection.
        options: What the user asked for.

    Returns:
        The content, ready to be laid out.
    """
    period = options.period
    return ReportContent(
        options=options,
        summary=report_queries.report_summary(connection, period),
        series=report_queries.low_minutes_series(connection, period),
        top_nights=report_queries.top_nights(connection, period),
        weekdays=night_queries.sustained_low_by_weekday(connection, period),
        tag_patterns=report_queries.tag_patterns(connection, period),
    )
