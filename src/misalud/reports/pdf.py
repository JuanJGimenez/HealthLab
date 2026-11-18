"""Lay the report out on A4 pages and save it as a PDF.

Page one is always the summary: header, key figures and the night-by-night
chart. The ten hardest nights, the patterns and the method notes follow. The
optional blocks and the nights shown in detail come last, as annexes.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import date
from pathlib import Path
from typing import Any

from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import (
    KeepTogether,
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

import misalud
from misalud.config import THRESHOLDS
from misalud.queries.night_detail import NightDetail
from misalud.reports.charts import GRID, INK, MUTED, category_chart, timeline_chart
from misalud.reports.content import BLOCKS, PersonalData, ReportContent
from misalud.reports.plots import line_chart, points_chart, stacked_chart, tracks_chart
from misalud.reports.texts import ReportTexts, load_report_texts

MARGIN = 18 * mm
CONTENT_WIDTH = A4[0] - 2 * MARGIN
FONT, BOLD = "Helvetica", "Helvetica-Bold"

TITLE = ParagraphStyle("title", fontName=BOLD, fontSize=16, leading=20, textColor=INK)
HEADING = ParagraphStyle(
    "heading", fontName=BOLD, fontSize=11, leading=14, textColor=INK, spaceBefore=10, spaceAfter=4
)
BODY = ParagraphStyle(
    "body", fontName=FONT, fontSize=9, leading=12, textColor=INK, alignment=TA_LEFT
)
SMALL = ParagraphStyle("small", parent=BODY, fontSize=8, leading=10.5, textColor=MUTED)
CELL = ParagraphStyle("cell", parent=BODY, fontSize=8.5, leading=11)
CELL_BOLD = ParagraphStyle("cell_bold", parent=CELL, fontName=BOLD)

TABLE_STYLE = TableStyle(
    [
        ("LINEBELOW", (0, 0), (-1, -1), 0.4, GRID),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ("LEFTPADDING", (0, 0), (-1, -1), 2),
        ("RIGHTPADDING", (0, 0), (-1, -1), 4),
    ]
)


def clock(hour: float | None, texts: ReportTexts) -> str:
    """Write a bedtime stored as an hour above 12 (24.5 is half past midnight)."""
    if hour is None:
        return texts.words["none"]
    minutes = round(hour * 60) % 1440
    return f"{minutes // 60:02d}:{minutes % 60:02d}"


def _count(texts: ReportTexts, count: int, total: int) -> str:
    """Write a count with its share of a total."""
    share = texts.number(100 * count / total) if total else texts.words["none"]
    return texts.text("count.of", count=count, total=total, pct=share)


def _person(person: PersonalData, texts: ReportTexts) -> str:
    """Write the personal data on one line, leaving out what is missing."""
    parts = [
        person.name,
        texts.text("person.age", age=person.age) if person.age is not None else None,
        person.sex,
        texts.text("person.height", value=texts.number(person.height_cm))
        if person.height_cm is not None
        else None,
        texts.text("person.weight", value=texts.number(person.weight_kg, 1))
        if person.weight_kg is not None
        else None,
    ]
    return " · ".join(part for part in parts if part)


def _pairs(rows: list[tuple[str, str]], label_width: float = 0.62) -> Table:
    """Build a two-column table of labels and values."""
    data = [[Paragraph(label, CELL), Paragraph(value, CELL_BOLD)] for label, value in rows]
    table = Table(data, colWidths=[CONTENT_WIDTH * label_width, CONTENT_WIDTH * (1 - label_width)])
    table.setStyle(TABLE_STYLE)
    return table


def _header(content: ReportContent, texts: ReportTexts) -> list[Any]:
    """Build the title and the lines that say what the report covers."""
    summary, options = content.summary, content.options
    rows = [
        (
            texts.words["header.period"],
            texts.text(
                "header.period.value",
                first=texts.day(summary["first_night"]),
                last=texts.day(summary["last_night"]),
            ),
        ),
        (texts.words["header.nights"], texts.number(summary["nights"])),
    ]
    if options.watch_model:
        rows.append((texts.words["header.watch"], options.watch_model))
    rows.append((texts.words["header.generated"], texts.day(options.generated_at.date())))
    if options.personal is not None and _person(options.personal, texts):
        rows.append((texts.words["header.person"], _person(options.personal, texts)))
    return [
        Paragraph(texts.words["title"], TITLE),
        Paragraph(texts.words["subtitle"], SMALL),
        Spacer(1, 6),
        _pairs(rows, label_width=0.3),
    ]


def _summary(content: ReportContent, texts: ReportTexts) -> list[Any]:
    """Build the table of key figures."""
    s = content.summary
    valid = s["nights_with_oxygen"]
    most = (
        texts.text(
            "summary.max_low.value",
            minutes=texts.number(s["max_low_minutes"], 1),
            date=texts.day(s["max_low_date"]),
        )
        if s["max_low_minutes"]
        else texts.words["none"]
    )
    unit = texts.words
    rows = [
        (unit["summary.nights_with_oxygen"], _count(texts, valid, s["nights"])),
        (unit["summary.average_spo2"], f"{texts.number(s['average_spo2'], 1)} %"),
        (unit["summary.nights_below_90"], _count(texts, s["nights_below_90"], valid)),
        (unit["summary.nights_5_min"], _count(texts, s["nights_5_min"], valid)),
        (unit["summary.nights_10_min"], _count(texts, s["nights_10_min"], valid)),
        (unit["summary.max_low"], most),
        (unit["summary.pulse"], f"{texts.number(s['average_night_hr'])} {unit['unit.bpm']}"),
        (
            unit["summary.asleep"],
            f"{texts.number(s['average_asleep_hours'], 1)} {unit['unit.hours']}",
        ),
        (
            unit["summary.snoring"],
            texts.text(
                "summary.snoring.value",
                nights=s["snoring_nights"],
                minutes=texts.number(s["median_snoring_min"]),
            ),
        ),
    ]
    return [Paragraph(unit["summary.title"], HEADING), _pairs(rows)]


def _evolution(content: ReportContent, texts: ReportTexts) -> list[Any]:
    """Build the night-by-night chart."""
    points = [
        (date.fromisoformat(point["night_date"]), float(point["low_minutes"] or 0))
        for point in content.series
    ]
    chart = timeline_chart(
        points,
        width=CONTENT_WIDTH,
        height=150,
        unit=texts.words["unit.minutes"],
        threshold=THRESHOLDS.sustained_low_min,
        month_names=texts.words["months"].split(","),
    )
    return [
        Paragraph(texts.words["evolution.title"], HEADING),
        Paragraph(texts.words["evolution.caption"], SMALL),
        Spacer(1, 4),
        chart,
    ]


def _top_nights(content: ReportContent, texts: ReportTexts) -> list[Any]:
    """Build the table of the ten hardest nights."""
    words = texts.words
    flow: list[Any] = [
        Paragraph(words["top.title"], HEADING),
        Paragraph(words["top.caption"], SMALL),
    ]
    if not content.top_nights:
        return [*flow, Spacer(1, 4), Paragraph(words["top.none"], BODY)]
    keys = ("date", "minutes", "spo2_min", "pulse", "snoring", "bedtime", "tags")
    rows = [[Paragraph(words[f"top.{key}"], CELL_BOLD) for key in keys]]
    for night in content.top_nights:
        cells = [
            f"{texts.day(night['night_date'])} · {texts.weekday(night['weekday'])}",
            texts.number(night["low_minutes"], 1),
            texts.number(night["spo2_min"]),
            texts.number(night["night_hr_avg"]),
            texts.number(night["snoring_min"]),
            clock(night["bedtime_hour"], texts),
            ", ".join(texts.tag(tag) for tag in night["tags"]) or words["none"],
        ]
        rows.append([Paragraph(cell, CELL) for cell in cells])
    shares = (0.21, 0.11, 0.1, 0.08, 0.12, 0.1, 0.28)
    table = Table(rows, colWidths=[CONTENT_WIDTH * share for share in shares], repeatRows=1)
    table.setStyle(TABLE_STYLE)
    table.setStyle(TableStyle([("LINEBELOW", (0, 0), (-1, 0), 0.8, colors.black)]))
    return [*flow, Spacer(1, 4), table]


def _patterns(content: ReportContent, texts: ReportTexts) -> list[Any]:
    """Build the weekday chart and the with-and-without table of each tag."""
    words = texts.words
    by_day = {row["weekday"]: row["share_pct"] for row in content.weekdays["weekdays"]}
    chart = category_chart(
        [texts.weekday(day) for day in range(1, 8)],
        [by_day.get(day) for day in range(1, 8)],
        width=CONTENT_WIDTH,
        height=130,
        unit="%",
    )
    flow: list[Any] = [
        Paragraph(words["patterns.title"], HEADING),
        Paragraph(words["patterns.weekday.title"], CELL_BOLD),
        Paragraph(words["patterns.weekday.caption"], SMALL),
        Spacer(1, 4),
        chart,
        Spacer(1, 8),
        Paragraph(words["patterns.tags.title"], CELL_BOLD),
        Paragraph(words["patterns.tags.caption"], SMALL),
        Spacer(1, 4),
    ]
    if not content.tag_patterns:
        return [*flow, Paragraph(words["patterns.tags.none"], BODY)]
    rows = [[Paragraph(words[f"patterns.{key}"], CELL_BOLD) for key in ("tag", "with", "without")]]
    for pattern in content.tag_patterns:
        cells = [
            texts.tag(pattern),
            _count(texts, pattern["with_sustained"], pattern["with_nights"]),
            _count(texts, pattern["without_sustained"], pattern["without_nights"]),
        ]
        rows.append([Paragraph(cell, CELL) for cell in cells])
    table = Table(rows, colWidths=[CONTENT_WIDTH * share for share in (0.4, 0.3, 0.3)])
    table.setStyle(TABLE_STYLE)
    return [*flow, table]


def _method(texts: ReportTexts) -> list[Any]:
    """Build the method notes."""
    notes = [
        Paragraph(texts.words[f"method.{key}"], SMALL)
        for key in ("night", "oxygen", "limits", "scores")
    ]
    spaced: list[Any] = [Paragraph(texts.words["method.title"], HEADING)]
    for note in notes:
        spaced += [note, Spacer(1, 3)]
    return spaced


def _month_label(month: str, texts: ReportTexts) -> str:
    """Write the first day of a month as a short month and a two-digit year."""
    when = date.fromisoformat(month)
    return f"{texts.month(when.month)} {when.year % 100:02d}"


def _month_values(months: list[dict[str, Any]], key: str) -> list[float | None]:
    """Return a monthly series, blank for months with too few nights to chart."""
    return [None if month.get("enough_nights") is False else month[key] for month in months]


def _date_ticks(days: list[date], texts: ReportTexts) -> list[tuple[float, str]]:
    """Return positions and labels of about eight months along a date axis."""
    if not days:
        return []
    first, last = days[0], days[-1]
    months = (last.year - first.year) * 12 + last.month - first.month + 1
    every = max(-(-months // 8), 1)
    ticks = []
    for index in range(0, months, every):
        year, month = divmod(first.month - 1 + index, 12)
        tick = date(first.year + year, month + 1, 1)
        if tick >= first:
            ticks.append((float(tick.toordinal()), _month_label(tick.isoformat(), texts)))
    return ticks


def _titled(title: str, *flow: Any) -> KeepTogether:
    """Keep a small title together with what it introduces."""
    return KeepTogether([Paragraph(title, CELL_BOLD), Spacer(1, 3), *flow, Spacer(1, 8)])


def _trend(
    nights: list[dict[str, Any]],
    trend: list[dict[str, Any]],
    key: str,
    unit: str,
    texts: ReportTexts,
) -> Any:
    """Build a chart with one point per night and its rolling median."""
    dots = [
        (float(date.fromisoformat(night["night_date"]).toordinal()), float(night[key]))
        for night in nights
        if night[key] is not None
    ]
    line = [
        (float(date.fromisoformat(point["night_date"]).toordinal()), float(point["value"]))
        for point in trend
    ]
    days = [date.fromordinal(int(x)) for x, _ in dots]
    return points_chart(
        dots,
        width=CONTENT_WIDTH,
        height=120,
        unit=unit,
        line=line,
        x_ticks=_date_ticks(days, texts),
    )


def _heart_block(data: dict[str, Any], texts: ReportTexts) -> list[Any]:
    """Build the heart block: figures, two trends and the electrocardiograms."""
    words, overview = texts.words, data["overview"]
    flow: list[Any] = [
        Paragraph(words["heart.title"], HEADING),
        _pairs(
            [
                (
                    words["heart.pulse"],
                    f"{texts.number(overview['average_night_hr'])} {words['unit.bpm']}",
                ),
                (
                    words["heart.hrv"],
                    f"{texts.number(overview['median_hrv_ms'])} {words['unit.ms']}",
                ),
            ]
        ),
        Spacer(1, 8),
        _titled(
            words["heart.pulse.chart"],
            _trend(data["nights"], data["pulse_trend"], "night_hr_avg", words["unit.bpm"], texts),
        ),
        _titled(
            words["heart.hrv.chart"],
            _trend(data["nights"], data["hrv_trend"], "hrv_rmssd_ms", words["unit.ms"], texts),
        ),
        Paragraph(words["heart.ecg.title"], CELL_BOLD),
        Spacer(1, 3),
    ]
    if not data["ecg"]:
        return [*flow, Paragraph(words["heart.ecg.none"], BODY)]
    rows = [[Paragraph(words[f"ecg.{key}"], CELL_BOLD) for key in ("date", "pulse", "code")]]
    for record in data["ecg"]:
        moment = record["start_at"]
        cells = [
            f"{texts.day(moment[:10])}, {moment[11:16]}",
            f"{texts.number(record['mean_hr'])} {words['unit.bpm']}",
            texts.number(record["classification_code"]),
        ]
        rows.append([Paragraph(cell, CELL) for cell in cells])
    table = Table(
        rows, colWidths=[CONTENT_WIDTH * share for share in (0.4, 0.25, 0.35)], repeatRows=1
    )
    table.setStyle(TABLE_STYLE)
    return [*flow, table]


def _sleep_block(data: dict[str, Any], texts: ReportTexts) -> list[Any]:
    """Build the sleep block: figures, hours by month and stages by month."""
    words, averages, months = texts.words, data["averages"], data["months"]
    labels = [_month_label(month["month"], texts) for month in months]
    stages = texts.text(
        "sleep.stages.value",
        **{key: texts.number(averages[f"{key}_min"]) for key in ("deep", "rem", "light", "awake")},
    )
    return [
        Paragraph(words["sleep.title"], HEADING),
        _pairs(
            [
                (
                    words["sleep.asleep"],
                    f"{texts.number(averages['asleep_hours'], 1)} {words['unit.hours']}",
                ),
                (words["sleep.efficiency"], f"{texts.number(averages['efficiency_pct'])} %"),
                (words["sleep.stages"], stages),
            ]
        ),
        Spacer(1, 8),
        _titled(
            words["sleep.hours.chart"],
            line_chart(
                labels,
                [
                    (words["sleep.in_bed"], _month_values(months, "hours")),
                    (words["sleep.asleep.short"], _month_values(months, "asleep_hours")),
                ],
                width=CONTENT_WIDTH,
                height=120,
                unit=words["unit.hours"],
            ),
        ),
        _titled(
            words["sleep.stages.chart"],
            stacked_chart(
                labels,
                [
                    (words[f"stage.{key}"], _month_values(months, f"{key}_min"))
                    for key in ("deep", "rem", "light")
                ],
                width=CONTENT_WIDTH,
                height=130,
                unit=words["unit.minutes"],
            ),
            Paragraph(words["sleep.months.note"], SMALL),
        ),
    ]


def _snoring_block(data: dict[str, Any], texts: ReportTexts) -> list[Any]:
    """Build the snoring block: figures and the night-by-night chart."""
    words, stats = texts.words, data["stats"]
    points = [
        (date.fromisoformat(point["night_date"]), float(point["snoring_min"]))
        for point in data["series"]
    ]
    chart = timeline_chart(
        points,
        width=CONTENT_WIDTH,
        height=130,
        unit=words["unit.minutes"],
        threshold=0,
        month_names=words["months"].split(","),
    )
    minutes = words["unit.minutes"]
    return [
        Paragraph(words["snoring.title"], HEADING),
        _pairs(
            [
                (words["snoring.nights"], texts.number(stats["nights"])),
                (words["snoring.median"], f"{texts.number(stats['median'])} {minutes}"),
                (words["snoring.max"], f"{texts.number(stats['maximum'])} {minutes}"),
            ]
        ),
        Spacer(1, 8),
        _titled(words["snoring.chart"], chart),
    ]


def _activity_block(data: dict[str, Any], texts: ReportTexts) -> list[Any]:
    """Build the activity block: figures, steps by month and pulse by hour."""
    words, averages = texts.words, data["averages"]
    by_hour = {row["hour"]: row for row in data["hourly"]}
    hours = [f"{hour:02d}" for hour in range(24)]
    minutes = words["unit.minutes"]
    return [
        Paragraph(words["activity.title"], HEADING),
        _pairs(
            [
                (words["activity.steps"], texts.number(averages["steps"])),
                (words["activity.active"], f"{texts.number(averages['active_min'])} {minutes}"),
                (words["activity.exercise"], f"{texts.number(averages['exercise_min'])} {minutes}"),
            ]
        ),
        Spacer(1, 8),
        _titled(
            words["activity.steps.chart"],
            line_chart(
                [_month_label(month["month"], texts) for month in data["months"]],
                [(words["activity.steps"], [month["steps"] for month in data["months"]])],
                width=CONTENT_WIDTH,
                height=120,
                unit=words["unit.steps"],
            ),
        ),
        _titled(
            words["activity.hourly.chart"],
            line_chart(
                hours,
                [
                    (words[f"hourly.{key}"], [by_hour.get(hour, {}).get(key) for hour in range(24)])
                    for key in ("weekdays", "weekend")
                ],
                width=CONTENT_WIDTH,
                height=120,
                unit=words["unit.bpm"],
            ),
        ),
    ]


def _day_night_block(data: list[dict[str, Any]], texts: ReportTexts) -> list[Any]:
    """Build the day-and-night block: one scatter per relation, with its correlation."""
    words = texts.words
    flow: list[Any] = [
        Paragraph(words["daynight.title"], HEADING),
        Paragraph(words["daynight.caption"], SMALL),
        Spacer(1, 6),
    ]
    if not data:
        return [*flow, Paragraph(words["daynight.empty"], BODY)]
    for relation in data:
        cross = relation["cross"]
        dots = [(float(point["x"]), float(point["y"])) for point in relation["points"]]
        stat = (
            texts.text("daynight.none", n=relation["nights"])
            if relation["spearman"] is None
            else texts.text(
                "daynight.stat", value=texts.number(relation["spearman"], 2), n=relation["nights"]
            )
        )
        flow.append(
            _titled(
                texts.text("daynight.cross", x=cross.x_label, y=cross.y_label),
                points_chart(
                    dots, width=CONTENT_WIDTH, height=170, unit=cross.y_label, x_title=cross.x_label
                ),
                Paragraph(stat, BODY),
            )
        )
    return flow


def _annotations_block(data: list[dict[str, Any]], texts: ReportTexts) -> list[Any]:
    """Build the annotations block: nights and minutes under 90 % with and without each tag."""
    words = texts.words
    flow: list[Any] = [
        Paragraph(words["tags.title"], HEADING),
        Paragraph(words["tags.caption"], SMALL),
        Spacer(1, 4),
    ]
    if not data:
        return [*flow, Paragraph(words["tags.none"], BODY)]
    keys = ("tag", "with_nights", "without_nights", "with_low", "without_low")
    rows = [[Paragraph(words[f"tags.{key}"], CELL_BOLD) for key in keys]]
    few = False
    for row in data:
        short = not (row["with"]["enough_nights"] and row["without"]["enough_nights"])
        few = few or short
        cells = [
            texts.tag(row["tag"]) + (" *" if short else ""),
            texts.number(row["with"]["nights"]),
            texts.number(row["without"]["nights"]),
            texts.number(row["with"]["median_low_minutes"], 1),
            texts.number(row["without"]["median_low_minutes"], 1),
        ]
        rows.append([Paragraph(cell, CELL) for cell in cells])
    table = Table(
        rows,
        colWidths=[CONTENT_WIDTH * share for share in (0.3, 0.14, 0.14, 0.21, 0.21)],
        repeatRows=1,
    )
    table.setStyle(TABLE_STYLE)
    return [*flow, table, *([Spacer(1, 4), Paragraph(words["tags.few"], SMALL)] if few else [])]


BLOCK_BUILDERS: dict[str, Callable[[Any, ReportTexts], list[Any]]] = {
    "heart": _heart_block,
    "sleep": _sleep_block,
    "snoring": _snoring_block,
    "activity": _activity_block,
    "day_night": _day_night_block,
    "annotations": _annotations_block,
}


def _detail(detail: NightDetail, texts: ReportTexts) -> list[Any]:
    """Build the page of one night shown track by track."""
    words, night = texts.words, detail["night"]
    valid = night["has_valid_oxygen"]
    facts = texts.text(
        "detail.facts",
        hours=texts.number(night["asleep_hours"], 1),
        low=texts.number(night["low_minutes"] if valid else None, 1),
        lowest=texts.number(night["spo2_min"] if valid else None),
        pulse=texts.number(night["night_hr_avg"]),
        start=night["start_at"][11:16],
        end=night["end_at"][11:16],
    )
    names = [
        *(words[f"track.{key}"] for key in ("stages", "oxygen", "pulse", "snoring")),
        *(words[f"stage.{key}"] for key in ("deep", "light", "rem", "awake")),
        words["no_data"],
    ]
    title = f"{texts.day(night['night_date'])} · {texts.weekday(night['weekday'])}"
    return [
        Paragraph(texts.text("detail.title", date=title), HEADING),
        Paragraph(facts, BODY),
        Paragraph(words["detail.caption"], SMALL),
        Spacer(1, 8),
        tracks_chart(detail, names, width=CONTENT_WIDTH),
    ]


def _annexes(content: ReportContent, texts: ReportTexts) -> list[Any]:
    """Build the optional blocks and the detail nights, each starting a page."""
    flow: list[Any] = []
    for name in BLOCKS:
        if name in content.blocks:
            flow += [PageBreak(), *BLOCK_BUILDERS[name](content.blocks[name], texts)]
    for detail in content.details:
        flow += [PageBreak(), *_detail(detail, texts)]
    return flow


def render_pdf(content: ReportContent, target: Path) -> int:
    """Write the report to a PDF file.

    Args:
        content: Figures gathered by ``gather_report``.
        target: File to write; replaced if it exists.

    Returns:
        The number of pages written.
    """
    texts = load_report_texts(content.options.language)
    pages = 0

    def footer(canvas: Any, document: Any) -> None:
        nonlocal pages
        pages = document.page
        canvas.saveState()
        canvas.setFont(FONT, 7)
        canvas.setFillColor(MUTED)
        line = texts.text("footer", version=misalud.__version__, page=document.page)
        canvas.drawString(MARGIN, 10 * mm, line)
        canvas.restoreState()

    document = SimpleDocTemplate(
        str(target),
        pagesize=A4,
        leftMargin=MARGIN,
        rightMargin=MARGIN,
        topMargin=MARGIN,
        bottomMargin=MARGIN,
        title=texts.words["title"],
        author="MiSalud",
    )
    story = [
        *_header(content, texts),
        *_summary(content, texts),
        *_evolution(content, texts),
        PageBreak(),
        *_top_nights(content, texts),
        *_patterns(content, texts),
        *_method(texts),
        *_annexes(content, texts),
    ]
    document.build(story, onFirstPage=footer, onLaterPages=footer)
    return pages
