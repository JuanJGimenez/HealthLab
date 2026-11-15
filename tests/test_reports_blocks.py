"""Tests for the optional blocks of the report and the nights shown in detail."""

from __future__ import annotations

from collections.abc import Iterator
from datetime import date, datetime
from pathlib import Path

import pytest
from pypdf import PdfReader
from reportlab.graphics.shapes import Circle, PolyLine, Rect, String

from misalud.annotations.store import set_tag
from misalud.derived.rebuild import rebuild_derived
from misalud.queries.common import Period, UnknownMetricError
from misalud.queries.night_detail import night_detail
from misalud.queries.report import day_averages, ecg_list, night_averages, night_metric_stats
from misalud.reports.content import BLOCKS, Cross, ReportOptions, gather_report
from misalud.reports.pdf import render_pdf
from misalud.reports.plots import (
    line_chart,
    nice_range,
    points_chart,
    stacked_chart,
    tracks_chart,
)
from misalud.storage.database import Connection, open_database
from tests.support.sample_db import at, build_sample, insert

NOW = datetime(2026, 1, 20, 9, 0)
CROSS = Cross("hours", "bedtime_hour", "Horas en cama", "Hora de acostarse")
TRACK_NAMES = [
    "Etapas",
    "Oxígeno",
    "Pulso",
    "Ronquido",
    "Profundo",
    "Ligero",
    "REM",
    "Despierto",
    "sin dato",
]


@pytest.fixture
def db() -> Iterator[Connection]:
    """The sample database with two electrocardiograms and its calculated tables."""
    with build_sample() as connection:
        for ident, moment, pulse, code in [
            ("e1", "2026-01-05 12:00", 71.0, None),
            ("e2", "2026-01-05 12:00", 71.0, 1),
            ("e3", "2026-01-08 09:30", 0.0, 0),
        ]:
            insert(
                connection,
                "ecg",
                samsung_id=ident,
                start_at=at(moment),
                mean_hr=pulse,
                classification_code=code,
            )
        rebuild_derived(connection)
        yield connection


def shapes(drawing: object, kind: type) -> list[object]:
    """Return the shapes of one kind in a drawing."""
    return [shape for shape in drawing.contents if isinstance(shape, kind)]  # type: ignore[attr-defined]


def labels(drawing: object) -> list[str]:
    """Return every text written in a drawing."""
    return [shape.text for shape in shapes(drawing, String)]  # type: ignore[attr-defined]


def options(**extra: object) -> ReportOptions:
    """Build report options for the whole history, in Spanish."""
    return ReportOptions(period=Period(), language="es", generated_at=NOW, **extra)  # type: ignore[arg-type]


def test_period_averages_and_statistics(db: Connection) -> None:
    averages = night_averages(db, ["hours", "low_minutes", "deep_min"])
    assert averages == {"hours": pytest.approx(20.5 / 3), "low_minutes": 5.0, "deep_min": 80.0}
    assert night_metric_stats(db, "snoring_min") == {"nights": 1, "median": 2.0, "maximum": 2.0}
    assert night_metric_stats(db, "spo2_min") == {"nights": 2, "median": 88.5, "maximum": 93.0}
    days = day_averages(db, ["steps", "exercise_min"])
    assert days == {"days": 4, "steps": 7000.0, "exercise_min": 33.75}
    assert day_averages(db, [], Period(start=date(2026, 1, 9)))["days"] == 1
    for query in (night_averages, day_averages):
        with pytest.raises(UnknownMetricError):
            query(db, ["session_id"])
    with pytest.raises(UnknownMetricError):
        night_metric_stats(db, "night_date")


def test_an_electrocardiogram_stored_twice_is_listed_once(db: Connection) -> None:
    assert ecg_list(db) == [
        {"start_at": "2026-01-05T12:00:00", "mean_hr": 71.0, "classification_code": 1},
        {"start_at": "2026-01-08T09:30:00", "mean_hr": None, "classification_code": 0},
    ]
    assert len(ecg_list(db, Period(start=date(2026, 1, 6)))) == 1


@pytest.mark.parametrize(
    ("low", "high", "expected"),
    [
        (0, 9, (0, 10, 5)),
        (2, 30, (0, 30, 3)),
        (52, 73, (50, 80, 3)),
        (6.5, 7.9, (6.4, 8.0, 4)),
        (5, 5, (4.8, 6.0, 4)),
        (95, 100, (94, 100, 3)),
    ],
)
def test_an_axis_that_does_not_start_near_zero_starts_just_below_its_values(
    low: float, high: float, expected: tuple[float, float, int]
) -> None:
    assert nice_range(low, high) == pytest.approx(expected)


def test_a_line_chart_breaks_at_missing_values_and_names_its_series() -> None:
    months = [f"m{index}" for index in range(14)]
    values = [7.0, 7.2, None, 6.9, None, *[7.0] * 9]
    chart = line_chart(
        months, [("En cama", values), ("Dormido", [6.0] * 14)], width=400, height=120, unit="h"
    )
    assert len(shapes(chart, PolyLine)) == 3
    assert len(shapes(chart, Circle)) == 1
    written = labels(chart)
    assert {"h", "En cama", "Dormido", "m0", "m2"} <= set(written)
    assert "m1" not in written
    single = line_chart(["a", "b"], [("Pasos", [1.0, 2.0])], width=400, height=120, unit="")
    assert "Pasos" not in labels(single)
    assert shapes(line_chart([], [("x", [])], width=400, height=120, unit=""), PolyLine) == []


def test_a_stacked_chart_piles_one_piece_per_series() -> None:
    chart = stacked_chart(
        ["ene", "feb"],
        [("Profundo", [50.0, None]), ("REM", [100.0, 90.0])],
        width=400,
        height=120,
        unit="min",
    )
    assert len(shapes(chart, Rect)) == 3
    assert {"Profundo", "REM", "ene", "feb", "min", "150"} <= set(labels(chart))
    months = [f"m{index}" for index in range(14)]
    many = stacked_chart(months, [("Profundo", [50.0] * 14)], width=400, height=120, unit="min")
    assert "m0" in labels(many)
    assert "m1" not in labels(many)


def test_a_points_chart_draws_dots_a_line_and_its_axes() -> None:
    dots = [(1.0, 60.0), (2.0, 64.0), (3.0, 58.0)]
    trend = points_chart(
        dots,
        width=400,
        height=120,
        unit="lpm",
        line=dots,
        x_ticks=[(1.0, "ene 26"), (3.0, "mar 26"), (9.0, "sept 26")],
    )
    assert len(shapes(trend, Circle)) == 3
    assert len(shapes(trend, PolyLine)) == 1
    assert {"ene 26", "mar 26"} <= set(labels(trend))
    assert "sept 26" not in labels(trend)
    scatter = points_chart(
        [(50.0, 0.0), (70.0, 20.0)], width=400, height=160, unit="Minutos", x_title="Pulso"
    )
    assert {"Pulso", "Minutos", "50", "70"} <= set(labels(scatter))
    assert shapes(scatter, PolyLine) == []
    assert shapes(points_chart([], width=400, height=120, unit=""), Circle) == []


def test_the_tracks_of_a_night_are_drawn_with_low_oxygen_shaded(db: Connection) -> None:
    detail = night_detail(db, date(2026, 1, 5))
    assert detail is not None
    chart = tracks_chart(detail, TRACK_NAMES, width=480)
    written = labels(chart)
    assert {"Etapas", "Oxígeno", "Pulso", "Ronquido", "Profundo", "Despierto"} <= set(written)
    assert {"00:00", "03:00", "06:00"} <= set(written)
    # One shaded stretch on each of the four tracks, and two snoring events.
    assert len(shapes(chart, Rect)) == 4 + 2
    assert len(shapes(chart, PolyLine)) == 3
    empty = night_detail(db, date(2026, 1, 6))
    assert empty is not None
    without = labels(tracks_chart(empty, TRACK_NAMES, width=480))
    assert {
        "Etapas · sin dato",
        "Oxígeno · sin dato",
        "Pulso · sin dato",
        "Ronquido · sin dato",
    } <= set(without)
    assert "01:00" in without


def test_only_the_blocks_asked_for_are_gathered(db: Connection) -> None:
    assert list(BLOCKS) == ["heart", "sleep", "snoring", "activity", "day_night", "annotations"]
    assert gather_report(db, options()).blocks == {}
    set_tag(db, date(2026, 1, 5), 1, True)
    content = gather_report(
        db,
        options(
            blocks=tuple(BLOCKS),
            crosses=(CROSS,),
            detail_nights=(date(2026, 1, 5), date(2026, 1, 7)),
        ),
    )
    assert list(content.blocks) == list(BLOCKS)
    assert content.blocks["heart"]["overview"]["median_hrv_ms"] == 40
    assert len(content.blocks["heart"]["ecg"]) == 2
    assert content.blocks["sleep"]["averages"]["deep_min"] == 80
    assert content.blocks["snoring"]["series"] == [{"night_date": "2026-01-05", "snoring_min": 2.0}]
    assert content.blocks["activity"]["averages"]["days"] == 4
    assert content.blocks["day_night"][0]["nights"] == 3
    assert [row["tag"]["name"] for row in content.blocks["annotations"]] == ["alcohol"]
    # 7 January has no night, so only one of the two nights asked for is detailed.
    assert [detail["night"]["night_date"] for detail in content.details] == ["2026-01-05"]


def test_unknown_blocks_and_too_many_detail_nights_are_refused(db: Connection) -> None:
    with pytest.raises(ValueError, match="unknown report blocks: weather"):
        gather_report(db, options(blocks=("heart", "weather")))
    three = (date(2026, 1, 5), date(2026, 1, 6), date(2026, 1, 9))
    with pytest.raises(ValueError, match="at most 2 nights"):
        gather_report(db, options(detail_nights=three))


def test_each_block_and_each_detail_night_starts_a_page(db: Connection, tmp_path: Path) -> None:
    set_tag(db, date(2026, 1, 5), 1, True)
    content = gather_report(
        db,
        options(
            blocks=tuple(BLOCKS),
            crosses=(CROSS, Cross("score", "hours", "Puntaje", "Horas")),
            detail_nights=(date(2026, 1, 5), date(2026, 1, 6)),
        ),
    )
    target = tmp_path / "completo.pdf"
    assert render_pdf(content, target) == 2 + 6 + 2
    pages = [page.extract_text() for page in PdfReader(target).pages]
    expected = [
        ("Corazón", "58 lpm", "40 ms", "5 ene 2026, 12:00", "71 lpm"),
        ("Sueño", "6,7 h", "90 %", "80 · 120 · 200 · 20", "Los meses con menos de 5 noches"),
        ("Ronquido", "Noches con ronquido grabado", "2 min"),
        ("Actividad", "7000", "34 min", "Lunes a viernes"),
        (
            "Día y noche",
            "Hora de acostarse según Horas en cama",
            "-0,87 · 3 noches",
            "No se puede calcular una correlación con 3 noches.",
        ),
        ("Anotaciones", "Alcohol *", "10,0", "menos de 10 noches"),
        (
            "Detalle de la noche del 5 ene 2026 · Lun",
            "6,7 h dormidas",
            "10,0 min bajo 90 %",
            "de 23:30 a 06:30",
        ),
        ("Detalle de la noche del 6 ene 2026 · Mar", "Oxígeno (%) · sin dato"),
    ]
    for page, texts in zip(pages[2:], expected, strict=True):
        for text in texts:
            assert text in page, text
    assert "Sueño y oxígeno" not in pages[2]


def test_blocks_without_data_still_print(tmp_path: Path) -> None:
    with open_database(None) as connection:
        rebuild_derived(connection)
        content = gather_report(connection, options(blocks=tuple(BLOCKS)))
    target = tmp_path / "vacio.pdf"
    assert render_pdf(content, target) == 8
    text = " ".join(page.extract_text() for page in PdfReader(target).pages)
    for expected in [
        "No hay electrocardiogramas en el período.",
        "No se eligió ningún cruce.",
        "No hay noches con etiquetas en el período.",
    ]:
        assert expected in text
