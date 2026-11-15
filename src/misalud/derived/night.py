"""Build ``night``: one row per real night, with every signal attached.

A night is the longest sleep session of more than two hours that belongs to a
date. Samsung does not link oxygen, temperature, breathing or snoring records to
a sleep session, so they are attached by time: a record belongs to a night when
it starts between 30 minutes before sleep onset and wake-up. If several records
qualify, the longest one is used.

All time comparisons are made in UTC, because that is the only clock that does
not repeat or skip when the wearer changes time zone.
"""

from __future__ import annotations

from typing import Final

from misalud.config import THRESHOLDS
from misalud.storage.database import Connection

_UTC: Final = "{alias}.{column} - to_minutes(CAST({alias}.utc_offset_min AS BIGINT))"


def _utc(alias: str, column: str) -> str:
    """Return the SQL that converts a local time column of ``alias`` to UTC."""
    return _UTC.format(alias=alias, column=column)


def _window_join(table: str, columns: str) -> str:
    """Return the SQL that picks, for each night, the longest record of ``table`` in its window.

    Args:
        table: A table with ``samsung_id``, ``start_at``, ``end_at`` and
            ``utc_offset_min``.
        columns: Select list taken from the record, with ``r`` as its alias.

    Returns:
        A subquery with ``night_date`` and the requested columns, one row per
        night that has a record.
    """
    return f"""(
        SELECT night_date, {columns}
        FROM main m JOIN "{table}" r
          ON {_utc("r", "start_at")} BETWEEN m.window_start_utc AND m.end_utc
        QUALIFY row_number() OVER (
            PARTITION BY m.night_date ORDER BY r.end_at - r.start_at DESC, r.samsung_id
        ) = 1
    )"""


NIGHT_SQL: Final = f"""
CREATE OR REPLACE TABLE night AS
WITH long_session AS (
    SELECT s.*,
        {_utc("s", "start_at")} AS start_utc,
        {_utc("s", "end_at")} AS end_utc,
        row_number() OVER (
            PARTITION BY night_date ORDER BY duration_min DESC, start_at
        ) AS position,
        sum(duration_min) OVER (PARTITION BY night_date) AS total_min
    FROM sleep_session s
    WHERE is_night
),
main AS (
    SELECT *, start_utc - to_minutes($padding) AS window_start_utc
    FROM long_session
    WHERE position = 1
),
stage AS (
    SELECT session_id,
        sum(duration_min) FILTER (stage_code = 40001) AS awake_min,
        sum(duration_min) FILTER (stage_code = 40002) AS light_min,
        sum(duration_min) FILTER (stage_code = 40003) AS deep_min,
        sum(duration_min) FILTER (stage_code = 40004) AS rem_min
    FROM sleep_stage
    GROUP BY session_id
),
oxygen AS {
    _window_join(
        "spo2_night",
        "r.samsung_id AS spo2_id, r.spo2_avg, r.spo2_min, r.low_seconds / 60 AS low_minutes, "
        "round(epoch(r.end_at - r.start_at) / 3600, 2) AS spo2_recorded_hours",
    )
},
oxygen_interval AS (
    SELECT night_samsung_id AS spo2_id,
        count(*) FILTER (spo2_min < $low) AS intervals_below_90,
        count(*) FILTER (spo2_min < $very_low) AS intervals_below_85
    FROM spo2_interval
    GROUP BY night_samsung_id
),
skin AS {
    _window_join(
        "skin_temperature",
        "r.temperature_c AS skin_temp_c, r.temperature_c - r.baseline_c AS skin_temp_vs_baseline_c",
    )
},
breathing AS {_window_join("respiratory_rate", "r.rate_avg AS respiratory_rate_avg")},
snoring AS (
    SELECT m.night_date, sum(e.duration_s) / 60 AS snoring_min, count(*) AS snoring_events
    FROM main m JOIN snoring_event e
      ON {_utc("e", "start_at")} BETWEEN m.start_utc AND m.end_utc
    GROUP BY m.night_date
),
variability AS (
    SELECT m.night_date, median(h.rmssd_ms) AS hrv_rmssd_ms, median(h.sdnn_ms) AS hrv_sdnn_ms
    FROM main m JOIN hrv_window h ON h.start_utc BETWEEN m.start_utc AND m.end_utc
    GROUP BY m.night_date
),
pulse AS (
    SELECT m.night_date, avg(h.heart_rate) AS night_hr_avg, min(h.heart_rate) AS night_hr_min
    FROM main m JOIN heart_rate_minute h ON h.start_utc BETWEEN m.start_utc AND m.end_utc
    GROUP BY m.night_date
),
workout AS (
    SELECT CAST(e.start_at AS DATE) AS day,
        sum(e.duration_min) AS exercise_min,
        count(*) AS exercise_count,
        string_agg(DISTINCT l.label, ', ' ORDER BY l.label) AS exercise_types
    FROM exercise e JOIN exercise_label l USING (samsung_id)
    GROUP BY 1
),
tension AS (
    SELECT CAST(start_at AS DATE) AS day, avg(score) AS stress_avg FROM stress GROUP BY 1
)
SELECT
    CAST(m.night_date AS DATE) AS night_date,
    m.samsung_id AS session_id,
    m.start_at,
    m.end_at,
    round(m.duration_min / 60, 2) AS hours,
    m.fragment_count,
    m.total_min - m.duration_min AS extra_sleep_min,
    m.score,
    m.efficiency_pct,
    m.physical_recovery,
    m.mental_recovery,
    m.movement_awakening,
    hour(m.start_at) + minute(m.start_at) / 60
        + CASE WHEN hour(m.start_at) < 12 THEN 24 ELSE 0 END AS bedtime_hour,
    isodow(m.night_date) AS weekday,
    isodow(m.night_date) IN (5, 6) AS is_weekend_night,
    stage.awake_min,
    stage.light_min,
    stage.deep_min,
    stage.rem_min,
    (stage.light_min + stage.deep_min + stage.rem_min) / 60 AS asleep_hours,
    oxygen.spo2_avg,
    oxygen.spo2_min,
    oxygen.low_minutes,
    CASE WHEN oxygen.spo2_id IS NOT NULL
        THEN coalesce(oxygen_interval.intervals_below_90, 0) END AS intervals_below_90,
    CASE WHEN oxygen.spo2_id IS NOT NULL
        THEN coalesce(oxygen_interval.intervals_below_85, 0) END AS intervals_below_85,
    oxygen.spo2_recorded_hours,
    variability.hrv_rmssd_ms,
    variability.hrv_sdnn_ms,
    pulse.night_hr_avg,
    pulse.night_hr_min,
    skin.skin_temp_c,
    skin.skin_temp_vs_baseline_c,
    breathing.respiratory_rate_avg,
    snoring.snoring_min,
    snoring.snoring_events,
    workout.exercise_min,
    workout.exercise_count,
    workout.exercise_types,
    steps_day.steps,
    tension.stress_avg
FROM main m
LEFT JOIN stage ON stage.session_id = m.samsung_id
LEFT JOIN oxygen USING (night_date)
LEFT JOIN oxygen_interval USING (spo2_id)
LEFT JOIN skin USING (night_date)
LEFT JOIN breathing USING (night_date)
LEFT JOIN snoring USING (night_date)
LEFT JOIN variability USING (night_date)
LEFT JOIN pulse USING (night_date)
LEFT JOIN workout ON workout.day = CAST(m.night_date AS DATE)
LEFT JOIN steps_day ON steps_day.day = m.night_date
LEFT JOIN tension ON tension.day = CAST(m.night_date AS DATE)
ORDER BY night_date
"""

VERY_LOW_SPO2_PCT: Final = 85
"""Second oxygen level counted per night, below the main threshold of 90."""


def rebuild_night(connection: Connection) -> int:
    """Recompute the ``night`` table from the detail tables.

    The table is replaced in full; it holds nothing that cannot be recomputed.
    ``exercise_label`` must exist (see ``rebuild_derived``).

    Args:
        connection: An open connection.

    Returns:
        The number of nights.
    """
    connection.execute(
        NIGHT_SQL,
        {
            "padding": THRESHOLDS.signal_join_padding_min,
            "low": THRESHOLDS.low_spo2_threshold_pct,
            "very_low": VERY_LOW_SPO2_PCT,
        },
    )
    return int(connection.execute("SELECT count(*) FROM night").fetchall()[0][0])
