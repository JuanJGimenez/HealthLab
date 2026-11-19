"""Build ``day``: one row per calendar day with activity, pulse, stress and energy.

Every day that has any daytime record gets a row. Each row links to the night
before (the one the wearer woke up from) and the night after, so the screens can
relate what happened during a day with how the wearer slept.
"""

from __future__ import annotations

from typing import Final

from healthlab.storage.database import Connection

DAY_SQL: Final = """
CREATE OR REPLACE TABLE day AS
WITH pulse AS (
    SELECT CAST(start_at AS DATE) AS day,
        avg(heart_rate) AS hr_avg, min(heart_rate) AS hr_min, max(heart_rate) AS hr_max
    FROM heart_rate_minute GROUP BY 1
),
tension AS (
    SELECT CAST(start_at AS DATE) AS day, avg(score) AS stress_avg, count(*) AS stress_count
    FROM stress GROUP BY 1
),
workout AS (
    SELECT CAST(e.start_at AS DATE) AS day,
        sum(e.duration_min) AS exercise_min,
        count(*) AS exercise_count,
        string_agg(DISTINCT l.label, ', ' ORDER BY l.label) AS exercise_types
    FROM exercise e JOIN exercise_label l USING (samsung_id)
    GROUP BY 1
),
steps AS (SELECT CAST(day AS DATE) AS day, steps FROM steps_day),
activity AS (SELECT * REPLACE (CAST(day AS DATE) AS day) FROM activity_day),
energy AS (SELECT CAST(day AS DATE) AS day, energy_score FROM vitality_day),
calendar AS (
    SELECT day FROM pulse UNION SELECT day FROM tension UNION SELECT day FROM workout
    UNION SELECT day FROM steps UNION SELECT day FROM activity UNION SELECT day FROM energy
)
SELECT
    c.day,
    coalesce(steps.steps, activity.steps) AS steps,
    activity.active_min,
    activity.distance_m,
    activity.floors,
    activity.active_calorie_kcal,
    coalesce(workout.exercise_min, 0) AS exercise_min,
    coalesce(workout.exercise_count, 0) AS exercise_count,
    workout.exercise_types,
    pulse.hr_avg,
    pulse.hr_min,
    pulse.hr_max,
    tension.stress_avg,
    coalesce(tension.stress_count, 0) AS stress_count,
    energy.energy_score,
    previous.night_date AS previous_night_date,
    following.night_date AS next_night_date
FROM calendar c
LEFT JOIN steps USING (day)
LEFT JOIN activity USING (day)
LEFT JOIN workout USING (day)
LEFT JOIN pulse USING (day)
LEFT JOIN tension USING (day)
LEFT JOIN energy USING (day)
LEFT JOIN night previous ON previous.night_date = c.day - 1
LEFT JOIN night following ON following.night_date = c.day
ORDER BY c.day
"""


def rebuild_day(connection: Connection) -> int:
    """Recompute the ``day`` table from the detail tables and ``night``.

    ``night`` and ``exercise_label`` must be up to date (see ``rebuild_derived``).

    Args:
        connection: An open connection.

    Returns:
        The number of days.
    """
    connection.execute(DAY_SQL)
    return int(connection.execute("SELECT count(*) FROM day").fetchall()[0][0])
