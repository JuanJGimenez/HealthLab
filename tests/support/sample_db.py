"""A small hand-made database for the derived and query tests.

Three nights and a nap, built so every rule of the ``night`` and ``day`` tables
has a case whose answer can be worked out by hand:

* Night A, Monday 5 January: two long sessions on the same date, a full oxygen
  recording with drops, every other signal, and two workouts that day.
* Night B, Tuesday 6 January: starts after midnight; its oxygen recording lasts
  only two hours, so its oxygen figures must not be reported.
* Night C, Friday 9 January: recorded in another time zone (UTC-4).
"""

from __future__ import annotations

from datetime import datetime, timedelta

from healthlab.storage.database import Connection, open_database
from healthlab.storage.schema import DETAIL_TABLES


def at(text: str) -> datetime:
    """Parse ``YYYY-MM-DD HH:MM`` into a moment."""
    return datetime.strptime(text, "%Y-%m-%d %H:%M")


def insert(connection: Connection, table: str, **values: object) -> None:
    """Insert one row into a detail table; columns not given stay empty."""
    spec = DETAIL_TABLES[table]
    unknown = set(values) - set(spec.columns)
    assert not unknown, unknown
    columns = ", ".join(f'"{name}"' for name in values)
    marks = ", ".join("?" for _ in values)
    connection.execute(f'INSERT INTO "{table}" ({columns}) VALUES ({marks})', list(values.values()))


def span(ident: str, start: str, end: str, offset: int = -180) -> dict[str, object]:
    """Return the id, local times and offset common to most records."""
    return {"samsung_id": ident, "start_at": at(start), "end_at": at(end), "utc_offset_min": offset}


def session(
    connection: Connection, ident: str, start: str, end: str, *, offset: int = -180, score: int = 80
) -> None:
    """Insert a sleep session; it counts as a night when longer than two hours."""
    minutes = (at(end) - at(start)).total_seconds() / 60
    night_date = (at(start) - timedelta(hours=12)).replace(hour=0, minute=0)
    insert(
        connection,
        "sleep_session",
        **span(ident, start, end, offset),
        night_date=night_date,
        duration_min=minutes,
        fragment_count=1,
        is_night=minutes > 120,
        score=score,
        efficiency_pct=90,
    )


def pulse(connection: Connection, utc: str, rate: float, offset: int = -180) -> None:
    """Insert one minute of heart rate, given its UTC moment."""
    local = at(utc) + timedelta(minutes=offset)
    insert(connection, "heart_rate_minute", start_utc=at(utc), start_at=local, heart_rate=rate)


def build_sample() -> Connection:
    """Create the sample database in memory, without calculated tables."""
    db = open_database(None)

    session(db, "A", "2026-01-05 23:30", "2026-01-06 06:30")
    session(db, "A2", "2026-01-06 07:30", "2026-01-06 10:00")
    session(db, "B", "2026-01-07 00:30", "2026-01-07 07:00")
    session(db, "C", "2026-01-09 22:00", "2026-01-10 05:00", offset=-240)
    session(db, "nap", "2026-01-08 15:00", "2026-01-08 16:00")

    stage_start = at("2026-01-05 23:30")
    for index, (code, minutes) in enumerate([(40001, 20), (40002, 200), (40003, 80), (40004, 120)]):
        stage_end = stage_start + timedelta(minutes=minutes)
        insert(
            db,
            "sleep_stage",
            samsung_id=f"stage{index}",
            session_id="A",
            start_at=stage_start,
            end_at=stage_end,
            stage_code=code,
            duration_min=minutes,
        )
        stage_start = stage_end

    oxygen = [
        ("oxA", "2026-01-05 23:40", "2026-01-06 06:20", -180, 94, 84, 600),
        ("oxA-short", "2026-01-05 23:10", "2026-01-05 23:25", -180, 99, 80, 0),
        ("oxA-early", "2026-01-05 22:50", "2026-01-06 06:50", -180, 99, 99, 0),
        ("oxB", "2026-01-07 00:40", "2026-01-07 02:40", -180, 95, 91, 0),
        ("oxC", "2026-01-09 22:05", "2026-01-10 05:00", -240, 96, 93, 0),
    ]
    for ident, start, end, offset, average, lowest, low_seconds in oxygen:
        insert(
            db,
            "spo2_night",
            **span(ident, start, end, offset),
            spo2_avg=average,
            spo2_min=lowest,
            low_seconds=low_seconds,
        )
    intervals = [("oxA", 92), ("oxA", 89), ("oxA", 84), ("oxA", 88), ("oxA-short", 80), ("oxC", 93)]
    for index, (night, lowest) in enumerate(intervals):
        insert(
            db,
            "spo2_interval",
            night_samsung_id=night,
            start_utc=at("2026-01-06 03:00") + timedelta(minutes=10 * index),
            start_at=at("2026-01-06 00:00") + timedelta(minutes=10 * index),
            end_at=at("2026-01-06 00:09") + timedelta(minutes=10 * index, seconds=59),
            spo2_min=lowest,
        )

    insert(
        db,
        "skin_temperature",
        **span("skinA", "2026-01-05 23:35", "2026-01-06 06:25"),
        temperature_c=34.5,
        baseline_c=34.0,
    )
    insert(
        db,
        "respiratory_rate",
        **span("breathA", "2026-01-05 23:35", "2026-01-06 06:25"),
        rate_avg=14.2,
    )
    for ident, start, seconds in [
        ("snore1", "2026-01-06 01:00", 30),
        ("snore2", "2026-01-06 02:00", 90),
        ("snore-after", "2026-01-06 07:00", 600),
    ]:
        insert(db, "snoring_event", **span(ident, start, start), duration_s=seconds)

    # Night A runs from 02:30 to 09:30 UTC on 6 January.
    for utc, rate in [("02:30", 60), ("05:00", 50), ("09:30", 70), ("09:31", 100)]:
        pulse(db, f"2026-01-06 {utc}", rate)
    # Night C runs from 02:00 to 09:00 UTC on 10 January, at UTC-4.
    pulse(db, "2026-01-10 02:00", 55, offset=-240)
    pulse(db, "2026-01-10 01:30", 120, offset=-240)
    for utc, rmssd, sdnn in [
        ("03:00", 30, 40),
        ("04:00", 50, 60),
        ("05:00", 40, 70),
        ("10:00", 999, 999),
    ]:
        moment = at(f"2026-01-06 {utc}")
        insert(
            db,
            "hrv_window",
            start_utc=moment,
            start_at=moment - timedelta(hours=3),
            rmssd_ms=rmssd,
            sdnn_ms=sdnn,
        )

    insert(
        db,
        "exercise_custom_type",
        custom_id="c1",
        name="CrossFit",
        created_at=at("2025-03-30 10:00"),
    )
    workouts = [
        ("walk", "2026-01-05 18:00", "2026-01-05 19:00", 60, 1001, None),
        ("box", "2026-01-05 19:30", "2026-01-05 20:15", 45, 0, "c1"),
        ("mystery", "2026-01-06 18:00", "2026-01-06 18:30", 30, 99999, None),
    ]
    for ident, start, end, minutes, code, custom in workouts:
        insert(
            db,
            "exercise",
            **span(ident, start, end),
            duration_min=minutes,
            type_code=code,
            custom_id=custom,
        )
    for ident, start, score in [("st1", "2026-01-05 10:00", 20), ("st2", "2026-01-05 16:00", 40)]:
        insert(db, "stress", **span(ident, start, start), score=score)

    insert(db, "steps_day", samsung_id="steps5", day=at("2026-01-05 00:00"), steps=9000)
    insert(
        db,
        "activity_day",
        samsung_id="act5",
        day=at("2026-01-05 00:00"),
        steps=9100,
        active_min=100,
        distance_m=7000,
        floors=3,
        active_calorie_kcal=400,
    )
    insert(db, "activity_day", samsung_id="act7", day=at("2026-01-07 00:00"), steps=5000)
    insert(db, "vitality_day", samsung_id="vit6", day=at("2026-01-06 00:00"), energy_score=85)
    return db
