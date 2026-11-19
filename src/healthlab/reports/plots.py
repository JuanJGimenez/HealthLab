"""Charts of the optional report blocks, built on one small plotting helper.

Like the two base charts, they are plain vector shapes meant for paper: series
differ by line pattern as well as colour, so they survive a grey printer.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from datetime import datetime
from typing import Any

from reportlab.graphics.shapes import Circle, Drawing, Line, PolyLine, Rect, String
from reportlab.lib.colors import HexColor

from healthlab.queries.night_detail import NightDetail
from healthlab.reports.charts import BAR, FONT, GRID, INK, MUTED, nice_axis

ORANGE = HexColor("#eb6834")
GREEN = HexColor("#1baf7a")
SHADE = HexColor("#fbe3d6")
SERIES_COLORS = (BAR, ORANGE, GREEN)
SERIES_DASHES: tuple[list[int] | None, ...] = (None, [4, 2], [1, 2])
STAGE_LEVELS = {40003: 0, 40002: 1, 40004: 2, 40001: 3}
"""Height of each sleep stage on the stage track: deep, light, REM, awake."""


def nice_range(low: float, high: float) -> tuple[float, float, int]:
    """Return round limits for an axis and the number of equal parts between them.

    An axis whose values start near zero starts at zero. Otherwise it starts at
    a round number just under the lowest value, so small changes stay visible.

    Args:
        low: Smallest value to show.
        high: Largest value to show.

    Returns:
        The lower limit, the upper limit and the number of divisions.
    """
    if high <= low:
        high = low + 1
    if 0 <= low < high / 2:
        top, divisions = nice_axis(high)
        return 0.0, top, divisions
    step, _ = nice_axis((high - low) / 4)
    bottom = round(math.floor(low / step) * step, 9)
    top = round(math.ceil(high / step) * step, 9)
    return bottom, top, max(round((top - bottom) / step), 1)


class Plot:
    """A drawing with a value axis, a grid and helpers to place things on it."""

    def __init__(
        self,
        width: float,
        height: float,
        x_range: tuple[float, float],
        y_range: tuple[float, float],
        *,
        left: float = 30,
        top: float = 16,
        bottom: float = 20,
    ) -> None:
        """Create an empty plot.

        Args:
            width: Width of the drawing, in points.
            height: Height of the drawing, in points.
            x_range: Values at the left and right edges.
            y_range: Values at the bottom and top edges.
            left: Space kept for the value labels.
            top: Space kept above the plot.
            bottom: Space kept for the labels under the plot.
        """
        self.drawing = Drawing(width, height)
        self.left, self.bottom = left, bottom
        self.plot_width, self.plot_height = width - left - 8, height - top - bottom
        self.x_low, self.x_high = x_range
        self.y_low, self.y_high = y_range
        self.width, self.height = width, height

    def x(self, value: float) -> float:
        """Return the horizontal position of a value."""
        span = (self.x_high - self.x_low) or 1
        return self.left + self.plot_width * (value - self.x_low) / span

    def y(self, value: float) -> float:
        """Return the vertical position of a value."""
        span = (self.y_high - self.y_low) or 1
        return self.bottom + self.plot_height * (value - self.y_low) / span

    def add(self, shape: Any) -> None:
        """Add a shape to the drawing."""
        self.drawing.add(shape)

    def text(
        self, x: float, y: float, text: str, anchor: str = "middle", color: Any = MUTED
    ) -> None:
        """Write a small label."""
        self.add(String(x, y, text, fontName=FONT, fontSize=7, fillColor=color, textAnchor=anchor))

    def grid(self, divisions: int, unit: str = "", labels: Sequence[str] | None = None) -> None:
        """Draw the horizontal lines with their value labels and the unit above."""
        for step in range(divisions + 1):
            value = self.y_low + (self.y_high - self.y_low) * step / divisions
            self.add(
                Line(
                    self.left,
                    self.y(value),
                    self.left + self.plot_width,
                    self.y(value),
                    strokeColor=GRID,
                    strokeWidth=0.5,
                )
            )
            label = labels[step] if labels else f"{value:g}"
            self.text(self.left - 4, self.y(value) - 2.5, label, "end")
        if unit:
            self.text(2, self.height - 7, unit, "start")

    def x_label(self, value: float, text: str) -> None:
        """Write a label under the plot at a horizontal value."""
        self.text(self.x(value), self.bottom - 11, text)

    def line(
        self, points: Sequence[tuple[float, float]], index: int = 0, width: float = 1.2
    ) -> None:
        """Draw a line through points, in the colour and pattern of a series."""
        if len(points) < 2:
            return
        flat = [coordinate for x, y in points for coordinate in (self.x(x), self.y(y))]
        self.add(
            PolyLine(
                flat,
                strokeColor=SERIES_COLORS[index % 3],
                strokeWidth=width,
                strokeDashArray=SERIES_DASHES[index % 3],
            )
        )

    def legend(self, names: Sequence[str]) -> None:
        """Write the series names at the top right, each with its line sample."""
        x = self.left + self.plot_width
        for index in reversed(range(len(names))):
            width = len(names[index]) * 3.6
            self.text(x, self.height - 8, names[index], "end", INK)
            x -= width + 4
            self.add(
                Line(
                    x - 14,
                    self.height - 5.5,
                    x,
                    self.height - 5.5,
                    strokeColor=SERIES_COLORS[index % 3],
                    strokeWidth=1.2,
                    strokeDashArray=SERIES_DASHES[index % 3],
                )
            )
            x -= 24


def _thin(count: int, most: int = 11) -> int:
    """Return how many categories to skip between labels so they do not collide."""
    return max(math.ceil(count / most), 1)


def line_chart(
    labels: Sequence[str],
    series: Sequence[tuple[str, Sequence[float | None]]],
    *,
    width: float,
    height: float,
    unit: str,
) -> Drawing:
    """Draw one line per series over categories such as months or hours.

    A missing value breaks the line. With more than one series a legend is drawn.

    Args:
        labels: Name of each category.
        series: Name and values of each series; ``None`` marks a missing value.
        width: Width of the drawing, in points.
        height: Height of the drawing, in points.
        unit: Unit written above the value axis.

    Returns:
        The drawing.
    """
    values = [value for _, points in series for value in points if value is not None]
    low, high, divisions = nice_range(min(values, default=0), max(values, default=1))
    plot = Plot(width, height, (0, max(len(labels) - 1, 1)), (low, high))
    plot.grid(divisions, unit)
    for index in range(0, len(labels), _thin(len(labels))):
        plot.x_label(index, labels[index])
    for number, (_, points) in enumerate(series):
        run: list[tuple[float, float]] = []
        for index, value in enumerate([*points, None]):
            if value is None:
                plot.line(run, number)
                if len(run) == 1:
                    plot.add(
                        Circle(
                            plot.x(run[0][0]),
                            plot.y(run[0][1]),
                            1.3,
                            fillColor=SERIES_COLORS[number % 3],
                            strokeColor=None,
                        )
                    )
                run = []
            else:
                run.append((index, value))
    if len(series) > 1:
        plot.legend([name for name, _ in series])
    return plot.drawing


def stacked_chart(
    labels: Sequence[str],
    series: Sequence[tuple[str, Sequence[float | None]]],
    *,
    width: float,
    height: float,
    unit: str,
) -> Drawing:
    """Draw one bar per category, made of one piece per series.

    Args:
        labels: Name of each category.
        series: Name and values of each series, bottom piece first.
        width: Width of the drawing, in points.
        height: Height of the drawing, in points.
        unit: Unit written above the value axis.

    Returns:
        The drawing.
    """
    totals = [sum(points[index] or 0 for _, points in series) for index in range(len(labels))]
    top, divisions = nice_axis(max(totals, default=0))
    plot = Plot(width, height, (-0.5, max(len(labels), 1) - 0.5), (0, top))
    plot.grid(divisions, unit)
    half = plot.plot_width / max(len(labels), 1) * 0.3
    for index, label in enumerate(labels):
        if index % _thin(len(labels)) == 0:
            plot.x_label(index, label)
        base = 0.0
        for number, (_, points) in enumerate(series):
            value = points[index] or 0
            if value:
                plot.add(
                    Rect(
                        plot.x(index) - half,
                        plot.y(base),
                        2 * half,
                        plot.y(base + value) - plot.y(base),
                        fillColor=SERIES_COLORS[number % 3],
                        strokeColor=HexColor("#ffffff"),
                        strokeWidth=0.4,
                    )
                )
            base += value
    plot.legend([name for name, _ in series])
    return plot.drawing


def points_chart(
    dots: Sequence[tuple[float, float]],
    *,
    width: float,
    height: float,
    unit: str,
    line: Sequence[tuple[float, float]] = (),
    x_ticks: Sequence[tuple[float, str]] | None = None,
    x_title: str = "",
) -> Drawing:
    """Draw points, with an optional line over them.

    Used for a trend (one faint point per night and the rolling median as a
    line) and for a scatter of two measures.

    Args:
        dots: Position of each point.
        width: Width of the drawing, in points.
        height: Height of the drawing, in points.
        unit: Unit, or name, written above the value axis.
        line: Points of the line, in order.
        x_ticks: Positions and labels along the horizontal axis. Without them,
            round numbers are used.
        x_title: Name written under the horizontal axis.

    Returns:
        The drawing; an empty frame when there are no points.
    """
    xs = [x for x, _ in dots] or [0.0, 1.0]
    ys = [y for _, y in [*dots, *line]] or [0.0, 1.0]
    y_low, y_high, divisions = nice_range(min(ys), max(ys))
    if x_ticks is None:
        x_low, x_high, parts = nice_range(min(xs), max(xs))
        x_ticks = [
            (
                x_low + (x_high - x_low) * step / parts,
                f"{x_low + (x_high - x_low) * step / parts:g}",
            )
            for step in range(parts + 1)
        ]
    else:
        x_low, x_high = min(xs), max(max(xs), min(xs) + 1)
    plot = Plot(width, height, (x_low, x_high), (y_low, y_high), bottom=30 if x_title else 20)
    plot.grid(divisions, unit)
    for position, label in x_ticks:
        if x_low <= position <= x_high:
            plot.x_label(position, label)
    if x_title:
        plot.text(plot.left + plot.plot_width / 2, 4, x_title)
    for x, y in dots:
        plot.add(
            Circle(plot.x(x), plot.y(y), 1.1, fillColor=BAR, strokeColor=None, fillOpacity=0.45)
        )
    plot.line(line, 1, 1.4)
    return plot.drawing


def _hours(moment: str, start: datetime) -> float:
    """Return the hours between the start of a night and a moment."""
    return (datetime.fromisoformat(moment) - start).total_seconds() / 3600


LANE_HEIGHT = 52.0
LANE_GAP = 20.0
LANE_LABEL_SPACE = 18.0
OXYGEN_LIMIT = 90
"""Saturation under which a stretch counts as low; drawn as a dashed line."""


def _steps(
    spans: Sequence[tuple[dict[str, Any], float]], start: datetime
) -> list[tuple[float, float]]:
    """Return a stepped line: each span holds its value from its start to its end."""
    return [
        (_hours(moment, start), value)
        for span, value in spans
        for moment in (span["from"], span["to"])
    ]


def _bars(
    plot: Plot,
    spans: Sequence[dict[str, Any]],
    start: datetime,
    height: float,
    fill: Any,
    *,
    thinnest: float = 0.5,
) -> None:
    """Draw one filled bar per time span, standing on the base of the lane.

    A span shorter than ``thinnest`` points is widened to it, so it stays visible.
    """
    for span in spans:
        left, right = plot.x(_hours(span["from"], start)), plot.x(_hours(span["to"], start))
        width = max(right - left, thinnest)
        plot.drawing.add(Rect(left, plot.bottom, width, height, fillColor=fill, strokeColor=None))


def _level_line(plot: Plot, y: float, *, color: Any, dashed: bool = False) -> None:
    """Draw a horizontal line across the lane at a height in points."""
    plot.drawing.add(
        Line(
            plot.left,
            y,
            plot.left + plot.plot_width,
            y,
            strokeColor=color,
            strokeWidth=0.5,
            strokeDashArray=[3, 2] if dashed else None,
        )
    )


def _hour_labels(plot: Plot, start: datetime, length: float) -> None:
    """Label each full clock hour of the night under the lane."""
    first = ((60 - start.minute) % 60) / 60
    for hour in range(math.floor(length) + 1):
        position = hour + first
        if position <= length:
            clock = (start.hour + hour + (1 if start.minute else 0)) % 24
            plot.x_label(position, f"{clock:02d}:00")


def tracks_chart(detail: NightDetail, names: Sequence[str], *, width: float) -> Drawing:
    """Draw the four main tracks of one night on a shared time axis.

    From top to bottom: sleep stages, lowest oxygen of each interval with the
    90 % line, pulse, and snoring. Stretches with oxygen under 90 % are shaded
    across every track.

    Args:
        detail: Result of ``night_detail``.
        names: Titles of the four tracks, then of the four stages from deep to
            awake, then the words for "no data" (nine texts).
        width: Width of the drawing, in points.

    Returns:
        The drawing.
    """
    night, tracks = detail["night"], detail["tracks"]
    start = datetime.fromisoformat(night["start_at"])
    length = max(_hours(night["end_at"], start), 0.5)
    stages = [(span, float(STAGE_LEVELS.get(span["code"], 1))) for span in tracks["stages"]]
    oxygen = [(span, span["lowest"]) for span in tracks["oxygen"] if span["lowest"] is not None]
    pulse = [(_hours(point["at"], start), point["value"]) for point in tracks["pulse"]]
    beats = [value for _, value in pulse]
    lanes: list[tuple[tuple[float, float, int], Sequence[Any]]] = [
        ((0.0, 3.0, 3), stages),
        (nice_range(min([80.0, *(low for _, low in oxygen)]), 100.0), oxygen),
        (nice_range(min(beats, default=40), max(beats, default=100)), pulse),
        ((0.0, 1.0, 1), tracks["snoring"]),
    ]
    height = len(lanes) * (LANE_HEIGHT + LANE_GAP) + LANE_LABEL_SPACE
    drawing = Drawing(width, height)
    plots = []
    for index, ((low, high, _), content) in enumerate(lanes):
        plot = Plot(
            width,
            LANE_HEIGHT + LANE_LABEL_SPACE,
            (0, length),
            (low, high),
            left=44,
            top=0,
            bottom=LANE_LABEL_SPACE,
        )
        plot.drawing = drawing
        plot.bottom = height - (index + 1) * (LANE_HEIGHT + LANE_GAP)
        plot.height = plot.bottom + LANE_HEIGHT + 14
        _bars(plot, detail["low_spans"], start, LANE_HEIGHT, SHADE, thinnest=0.6)
        title = names[index] + ("" if content else f" · {names[8]}")
        drawing.add(
            String(
                2, plot.bottom + LANE_HEIGHT + 9, title, fontName=FONT, fontSize=7.5, fillColor=INK
            )
        )
        plots.append(plot)
    stage_plot, oxygen_plot, pulse_plot, snoring_plot = plots

    stage_plot.grid(3, labels=list(names[4:8]))
    stage_plot.line(_steps(stages, start), 0, 0.9)

    oxygen_plot.grid(lanes[1][0][2])
    oxygen_plot.line(_steps(oxygen, start), 0, 0.9)
    _level_line(oxygen_plot, oxygen_plot.y(OXYGEN_LIMIT), color=INK, dashed=True)

    pulse_plot.grid(lanes[2][0][2])
    pulse_plot.line(pulse, 1, 0.7)

    _level_line(snoring_plot, snoring_plot.bottom, color=GRID)
    _bars(snoring_plot, tracks["snoring"], start, LANE_HEIGHT * 0.7, GREEN)
    _hour_labels(snoring_plot, start, length)
    return drawing
