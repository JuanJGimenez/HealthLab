"""The two charts of the report, drawn as plain vector shapes.

They are deliberately simple: black on white, readable when printed in grey.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from datetime import date

from reportlab.graphics.shapes import Drawing, Line, Rect, String
from reportlab.lib.colors import HexColor

INK = HexColor("#1b1b1b")
MUTED = HexColor("#6b6a65")
GRID = HexColor("#dddcd6")
BAR = HexColor("#2a78d6")
FONT = "Helvetica"
LEFT, RIGHT, TOP, BOTTOM = 30, 8, 10, 20


DIVISIONS = {1: 5, 2: 4, 3: 3, 4: 4, 5: 5, 10: 5}
"""Grid lines that give round labels for each leading figure of the axis top."""


def nice_axis(value: float) -> tuple[float, int]:
    """Return a round top for an axis and how many equal parts to divide it into.

    Args:
        value: Largest value to show.

    Returns:
        The top (1, 2, 3, 4, 5 or 10 times a power of ten, at or above
        ``value``; 1 for zero or less) and the number of divisions that makes
        every grid label a round number.
    """
    if value <= 0:
        return 1.0, DIVISIONS[1]
    power = 10.0 ** math.floor(math.log10(value))
    leading = next(step for step in DIVISIONS if value <= step * power)
    return leading * power, DIVISIONS[leading]


def _frame(drawing: Drawing, width: float, height: float, largest: float, unit: str) -> float:
    """Draw the horizontal grid and the value labels of a chart; return the axis top."""
    top, divisions = nice_axis(largest)
    plot_height = height - TOP - BOTTOM
    for step in range(divisions + 1):
        level = top * step / divisions
        y = BOTTOM + plot_height * step / divisions
        drawing.add(Line(LEFT, y, width - RIGHT, y, strokeColor=GRID, strokeWidth=0.5))
        label = f"{level:g}"
        drawing.add(
            String(
                LEFT - 4,
                y - 2.5,
                label,
                fontName=FONT,
                fontSize=7,
                fillColor=MUTED,
                textAnchor="end",
            )
        )
    drawing.add(String(2, height - 8, unit, fontName=FONT, fontSize=7, fillColor=MUTED))
    return top


def timeline_chart(
    points: Sequence[tuple[date, float]],
    *,
    width: float,
    height: float,
    unit: str,
    threshold: float,
    month_names: Sequence[str],
) -> Drawing:
    """Draw one thin bar per night along a time axis.

    Args:
        points: Date and value of each night, in order.
        width: Width of the drawing, in points.
        height: Height of the drawing, in points.
        unit: Unit written above the value axis.
        threshold: Value marked with a horizontal line.
        month_names: Short names of the twelve months.

    Returns:
        The drawing; an empty frame when there are no points.
    """
    drawing = Drawing(width, height)
    top = _frame(drawing, width, height, max([threshold, *(value for _, value in points)]), unit)
    plot_width, plot_height = width - LEFT - RIGHT, height - TOP - BOTTOM
    if not points:
        return drawing
    first, last = points[0][0], points[-1][0]
    span = max((last - first).days, 1)

    def x_of(day: date) -> float:
        return LEFT + plot_width * (day - first).days / span

    bar_width = max(min(plot_width / (span + 1) * 0.8, 4.0), 0.4)
    for day, value in points:
        if value > 0:
            bar_height = plot_height * min(value, top) / top
            drawing.add(
                Rect(
                    x_of(day) - bar_width / 2,
                    BOTTOM,
                    bar_width,
                    bar_height,
                    fillColor=BAR,
                    strokeColor=None,
                )
            )
    y = BOTTOM + plot_height * threshold / top
    drawing.add(
        Line(LEFT, y, width - RIGHT, y, strokeColor=INK, strokeWidth=0.6, strokeDashArray=[3, 2])
    )
    months = (last.year - first.year) * 12 + last.month - first.month + 1
    every = max(math.ceil(months / 8), 1)
    for index in range(0, months, every):
        year, month = divmod(first.month - 1 + index, 12)
        tick = date(first.year + year, month + 1, 1)
        if tick < first:
            continue
        label = f"{month_names[tick.month - 1]} {tick.year % 100:02d}"
        drawing.add(
            Line(x_of(tick), BOTTOM, x_of(tick), BOTTOM - 3, strokeColor=MUTED, strokeWidth=0.5)
        )
        drawing.add(
            String(
                x_of(tick),
                BOTTOM - 11,
                label,
                fontName=FONT,
                fontSize=7,
                fillColor=MUTED,
                textAnchor="middle",
            )
        )
    return drawing


def category_chart(
    labels: Sequence[str],
    values: Sequence[float | None],
    *,
    width: float,
    height: float,
    unit: str,
) -> Drawing:
    """Draw one bar per category with its value written on top.

    Args:
        labels: Name of each category.
        values: Value of each category; ``None`` leaves its place empty.
        width: Width of the drawing, in points.
        height: Height of the drawing, in points.
        unit: Unit written above the value axis and after each value.

    Returns:
        The drawing.
    """
    drawing = Drawing(width, height)
    present = [value for value in values if value is not None]
    top = _frame(drawing, width, height, max(present, default=0.0), unit)
    plot_width, plot_height = width - LEFT - RIGHT, height - TOP - BOTTOM
    slot = plot_width / max(len(labels), 1)
    for index, (label, value) in enumerate(zip(labels, values, strict=True)):
        center = LEFT + slot * (index + 0.5)
        drawing.add(
            String(
                center,
                BOTTOM - 11,
                label,
                fontName=FONT,
                fontSize=7,
                fillColor=MUTED,
                textAnchor="middle",
            )
        )
        if value is None:
            continue
        bar_height = plot_height * value / top
        drawing.add(
            Rect(
                center - slot * 0.25,
                BOTTOM,
                slot * 0.5,
                bar_height,
                fillColor=BAR,
                strokeColor=None,
            )
        )
        drawing.add(
            String(
                center,
                BOTTOM + bar_height + 3,
                f"{value:.0f} {unit}",
                fontName=FONT,
                fontSize=7,
                fillColor=INK,
                textAnchor="middle",
            )
        )
    return drawing
