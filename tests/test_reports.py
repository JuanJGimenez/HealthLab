"""Tests for the doctor's report: its figures, its texts, its charts and the PDF."""

from __future__ import annotations

from collections.abc import Iterator
from datetime import date, datetime
from pathlib import Path

import pandas as pd
import pytest
from pypdf import PdfReader
from reportlab.graphics.shapes import Rect, String

from healthlab.annotations.profile import load_profile, save_profile
from healthlab.annotations.store import AnnotationError, add_tag, rename_tag, set_tag
from healthlab.derived.rebuild import rebuild_derived
from healthlab.queries.common import NightScope, Period
from healthlab.queries.report import low_minutes_series, report_summary, tag_patterns, top_nights
from healthlab.reports.charts import category_chart, nice_axis, timeline_chart
from healthlab.reports.content import PersonalData, ReportOptions, gather_report
from healthlab.reports.pdf import clock, render_pdf
from healthlab.reports.texts import REPORT_LANGUAGES, load_report_texts
from healthlab.storage.database import Connection, open_database
from tests.support.sample_db import at, build_sample, insert

NOW = datetime(2026, 1, 20, 9, 0)
DASH = "\u2013"


@pytest.fixture
def db() -> Iterator[Connection]:
    """The sample database with its calculated tables built."""
    with build_sample() as connection:
        rebuild_derived(connection)
        yield connection


def add_nights(db: Connection, first: str, low_minutes: list[float]) -> list[date]:
    """Add plain nights with valid oxygen and the given minutes under 90 %."""
    days = list(pd.date_range(first, periods=len(low_minutes)).date)
    frame = pd.DataFrame(
        {"night_date": days, "low_minutes": low_minutes, "spo2_recorded_hours": 6.0, "weekday": 1}
    )
    db.register("more_nights", frame)
    db.execute("INSERT INTO night BY NAME SELECT * FROM more_nights")
    db.unregister("more_nights")
    return days


def options(language: str = "es", **extra: object) -> ReportOptions:
    """Build report options for the whole history."""
    return ReportOptions(period=Period(), language=language, generated_at=NOW, **extra)  # type: ignore[arg-type]


def pdf_text(path: Path) -> list[str]:
    """Return the text of each page of a PDF."""
    return [page.extract_text() for page in PdfReader(path).pages]


def test_the_summary_counts_nights_by_minutes_under_90(db: Connection) -> None:
    summary = report_summary(db)
    assert summary == {
        "nights": 3,
        "first_night": "2026-01-05",
        "last_night": "2026-01-09",
        "nights_with_oxygen": 2,
        "average_spo2": 95.0,
        "nights_below_90": 1,
        "nights_5_min": 1,
        "nights_10_min": 1,
        "max_low_minutes": 10.0,
        "max_low_date": "2026-01-05",
        "average_night_hr": 57.5,
        "average_asleep_hours": pytest.approx(400 / 60),
        "snoring_nights": 1,
        "median_snoring_min": 2.0,
    }
    empty = report_summary(db, Period(start=date(2027, 1, 1)))
    assert (empty["nights"], empty["max_low_minutes"], empty["first_night"]) == (0, None, None)


def test_the_series_and_the_top_nights_use_only_valid_oxygen(db: Connection) -> None:
    assert low_minutes_series(db) == [
        {"night_date": "2026-01-05", "low_minutes": 10.0},
        {"night_date": "2026-01-09", "low_minutes": 0.0},
    ]
    rename_tag(db, 2, "Cena después de las 22")
    for tag_id in (1, 2):
        set_tag(db, date(2026, 1, 5), tag_id, True)
    top = top_nights(db)
    assert len(top) == 1
    assert (top[0]["night_date"], top[0]["low_minutes"], top[0]["bedtime_hour"]) == (
        "2026-01-05",
        10.0,
        23.5,
    )
    assert top[0]["tags"] == [
        {"name": "alcohol", "builtin_key": "alcohol"},
        {"name": "Cena después de las 22", "builtin_key": "late_dinner"},
    ]
    assert top_nights(db, limit=0) == []


def test_the_top_nights_are_ranked_by_minutes_and_limited(db: Connection) -> None:
    add_nights(db, "2026-02-01", [float(value) for value in range(1, 13)])
    top = top_nights(db)
    assert [night["low_minutes"] for night in top] == [12, 11, 10, 10, 9, 8, 7, 6, 5, 4]
    assert top[0]["tags"] == []


def test_a_tag_pattern_needs_ten_nights_in_each_group(db: Connection) -> None:
    assert tag_patterns(db) == []
    days = add_nights(db, "2026-02-01", [8.0] * 6 + [0.0] * 6 + [6.0] * 2 + [0.0] * 8)
    for day in days[:12]:
        set_tag(db, day, 1, True)
    for day in days[:3]:
        set_tag(db, day, 2, True)
    patterns = tag_patterns(db)
    assert patterns == [
        {
            "name": "alcohol",
            "builtin_key": "alcohol",
            "with_nights": 12,
            "with_sustained": 6,
            "with_share_pct": 50.0,
            "without_nights": 12,
            "without_sustained": 3,
            "without_share_pct": 25.0,
        }
    ]
    assert tag_patterns(db, NightScope(start=date(2026, 2, 1))) == [
        {**patterns[0], "without_nights": 10, "without_sustained": 2, "without_share_pct": 20.0}
    ]
    assert tag_patterns(db, Period(start=date(2026, 2, 5))) == []


def test_the_profile_is_saved_and_proposes_height_and_weight_from_the_watch(
    db: Connection,
) -> None:
    assert load_profile(db) == {
        "name": None,
        "birth_year": None,
        "sex": None,
        "height_cm": None,
        "weight_kg": None,
    }
    insert(
        db,
        "weight",
        samsung_id="w1",
        measured_at=at("2026-01-02 08:00"),
        weight_kg=91.0,
        height_cm=173.0,
    )
    insert(db, "weight", samsung_id="w2", measured_at=at("2026-01-08 08:00"), weight_kg=90.0)
    proposed = load_profile(db)
    assert (proposed["height_cm"], proposed["weight_kg"]) == (173.0, 90.0)
    save_profile(db, name="  Ana  ", birth_year=1982, sex="femenino", height_cm=170.0)
    save_profile(db, name="Ana Pérez", birth_year=1982, sex=" ", height_cm=170.0)
    assert load_profile(db) == {
        "name": "Ana Pérez",
        "birth_year": 1982,
        "sex": None,
        "height_cm": 170.0,
        "weight_kg": 90.0,
    }
    for year in (1850, 2999):
        with pytest.raises(AnnotationError, match="birth year out of range"):
            save_profile(db, name=None, birth_year=year, sex=None, height_cm=None)
    save_profile(db, name=None, birth_year=None, sex=None, height_cm=None)
    assert load_profile(db)["name"] is None


def test_report_texts_exist_in_every_language_with_the_same_keys() -> None:
    spanish, english = (load_report_texts(language) for language in REPORT_LANGUAGES)
    assert set(spanish.words) == set(english.words)
    for texts in (spanish, english):
        assert len(texts.words["months"].split(",")) == 12
        assert len(texts.words["weekdays"].split(",")) == 7
    with pytest.raises(ValueError, match="unknown report language: fr"):
        load_report_texts("fr")


def test_numbers_dates_and_tags_follow_the_language() -> None:
    spanish, english = load_report_texts("es"), load_report_texts("en")
    assert (spanish.number(95.93, 1), english.number(95.93, 1)) == ("95,9", "95.9")
    assert [spanish.number(value) for value in (56.5, 57.5, 0.5)] == ["57", "58", "1"]
    assert (spanish.number(-0.04, 1), spanish.number(None), spanish.number(7)) == ("0,0", DASH, "7")
    assert (spanish.day("2026-01-05"), english.day(date(2026, 9, 5))) == (
        "5 ene 2026",
        "5 Sep 2026",
    )
    assert spanish.day(None) == DASH
    assert (spanish.weekday(1), english.weekday(7)) == ("Lun", "Sun")
    assert spanish.tag({"name": "alcohol", "builtin_key": "alcohol"}) == "Alcohol"
    assert english.tag({"name": "late_dinner", "builtin_key": "late_dinner"}) == "Late dinner"
    assert spanish.tag({"name": "Vino", "builtin_key": "alcohol"}) == "Vino"
    assert spanish.tag({"name": "Mate", "builtin_key": None}) == "Mate"
    assert spanish.text("count.of", count=1, total=2, pct="50") == "1 de 2 (50 %)"
    assert (clock(24.5, spanish), clock(22.75, spanish), clock(None, spanish)) == (
        "00:30",
        "22:45",
        DASH,
    )


@pytest.mark.parametrize(
    ("value", "top", "divisions"),
    [(0, 1, 5), (0.7, 1, 5), (30.1, 40, 4), (13, 20, 4), (25, 30, 3), (45, 50, 5), (91, 100, 5)],
)
def test_axes_end_on_round_numbers(value: float, top: float, divisions: int) -> None:
    assert nice_axis(value) == (top, divisions)


def test_the_timeline_chart_draws_one_bar_per_night_with_time_under_90() -> None:
    points = [(date(2026, 1, 1), 0.0), (date(2026, 2, 10), 12.0), (date(2026, 3, 20), 3.0)]
    months = load_report_texts("es").words["months"].split(",")
    chart = timeline_chart(
        points, width=400, height=150, unit="min", threshold=5, month_names=months
    )
    bars = [shape for shape in chart.contents if isinstance(shape, Rect)]
    labels = [shape.text for shape in chart.contents if isinstance(shape, String)]
    assert len(bars) == 2
    assert {"min", "0", "20", "ene 26", "feb 26", "mar 26"} <= set(labels)
    empty = timeline_chart([], width=400, height=150, unit="min", threshold=5, month_names=months)
    assert not [shape for shape in empty.contents if isinstance(shape, Rect)]
    late_start = timeline_chart(
        [(date(2026, 1, 20), 1.0), (date(2026, 2, 5), 1.0)],
        width=400,
        height=150,
        unit="min",
        threshold=5,
        month_names=months,
    )
    assert "ene 26" not in [s.text for s in late_start.contents if isinstance(s, String)]


def test_the_category_chart_skips_categories_without_a_value() -> None:
    chart = category_chart(
        ["Lun", "Mar", "Mié"], [10.0, None, 25.0], width=300, height=120, unit="%"
    )
    assert len([shape for shape in chart.contents if isinstance(shape, Rect)]) == 2
    labels = [shape.text for shape in chart.contents if isinstance(shape, String)]
    assert {"Lun", "Mar", "Mié", "10 %", "25 %"} <= set(labels)
    assert "30" in labels


def test_the_report_gathers_every_block(db: Connection) -> None:
    content = gather_report(db, options())
    assert content.summary["nights"] == 3
    assert len(content.series) == 2
    assert [night["night_date"] for night in content.top_nights] == ["2026-01-05"]
    assert content.weekdays["overall_share_pct"] == 50.0
    assert content.tag_patterns == []


def test_the_pdf_opens_with_the_summary_and_follows_with_the_tables(
    db: Connection, tmp_path: Path
) -> None:
    custom = add_tag(db, "Mate")
    set_tag(db, date(2026, 1, 5), custom, True)
    set_tag(db, date(2026, 1, 5), 1, True)
    person = PersonalData(name="Ana Pérez", age=44, sex="femenino", height_cm=170, weight_kg=64.5)
    content = gather_report(db, options(watch_model="Galaxy Watch Ultra", personal=person))
    target = tmp_path / "informe.pdf"
    assert render_pdf(content, target) == 2
    first, second = pdf_text(target)
    for expected in [
        "Informe de sueño y oxígeno nocturno",
        "5 ene 2026 a 9 ene 2026",
        "Galaxy Watch Ultra",
        "20 ene 2026",
        "Ana Pérez · 44 años · femenino · 170 cm · 64,5 kg",
        "2 de 3 (67 %)",
        "1 de 2 (50 %)",
        "10,0 min, el 5 ene 2026",
        "58 lpm",
        "6,7 h",
        "1 noches, 2 min",
        "Página 1",
    ]:
        assert expected in first, expected
    for expected in [
        "Las 10 noches con más tiempo bajo 90 %",
        "5 ene 2026 · Lun",
        "23:30",
        "Alcohol, Mate",
        "Ninguna etiqueta tiene todavía 10 noches en cada grupo.",
        "Notas de método",
        "Página 2",
    ]:
        assert expected in second, expected


def test_the_pdf_shows_tag_patterns_and_follows_the_language(
    db: Connection, tmp_path: Path
) -> None:
    days = add_nights(db, "2026-02-01", [8.0] * 6 + [0.0] * 18)
    for day in days[:12]:
        set_tag(db, day, 1, True)
    target = tmp_path / "report.pdf"
    render_pdf(gather_report(db, options("en")), target)
    first, second = pdf_text(target)
    assert "Sleep and night oxygen report" in first
    assert "Watch" not in first.split("Summary")[0].replace("wrist watch", "")
    assert "Personal data" not in first
    assert "Alcohol" in second
    assert "6 of 12 (50 %)" in second
    assert "No tag has 10 nights" not in second


def test_a_report_without_nights_is_still_a_valid_pdf(tmp_path: Path) -> None:
    with open_database(None) as connection:
        rebuild_derived(connection)
        content = gather_report(connection, options(personal=PersonalData()))
    target = tmp_path / "vacio.pdf"
    assert render_pdf(content, target) == 2
    first, second = pdf_text(target)
    assert "Datos personales" not in first
    assert "Ninguna noche del período tuvo tiempo bajo 90 %." in second
