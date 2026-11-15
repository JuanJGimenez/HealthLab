"""Lay the report out on A4 pages and save it as a PDF.

Page one is always the summary: header, key figures and the night-by-night
chart. The ten hardest nights, the patterns and the method notes follow.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Any

from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

import misalud
from misalud.config import THRESHOLDS
from misalud.reports.charts import GRID, INK, MUTED, category_chart, timeline_chart
from misalud.reports.content import PersonalData, ReportContent
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
    ]
    document.build(story, onFirstPage=footer, onLaterPages=footer)
    return pages
