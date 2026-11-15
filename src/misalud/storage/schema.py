"""Shape of every table in the database.

Detail tables are described as data, not as SQL text, because the merge needs to
know each table's key and columns to compare records. The same description
creates the table, so the two can never disagree.

Table and column names here come from this module only, never from user input,
which is why they can be placed in SQL statements directly.
"""

from __future__ import annotations

from dataclasses import dataclass
from types import MappingProxyType
from typing import Final

TEXT: Final = "VARCHAR"
MOMENT: Final = "TIMESTAMP"
NUMBER: Final = "DOUBLE"
WHOLE: Final = "BIGINT"
FLAG: Final = "BOOLEAN"


@dataclass(frozen=True, slots=True)
class TableSpec:
    """One detail table.

    Attributes:
        name: Table name.
        key: Columns that identify a record across exports (the merge key).
        columns: Every column and its SQL type, in table order.
        time_column: Column that dates a record, used to tell old changes from
            recent ones and to report the period an import covers.
    """

    name: str
    key: tuple[str, ...]
    columns: MappingProxyType[str, str]
    time_column: str

    @property
    def value_columns(self) -> tuple[str, ...]:
        """Columns that are not part of the key: the ones compared to detect a change."""
        return tuple(name for name in self.columns if name not in self.key)

    def create_statement(self) -> str:
        """Return the SQL that creates the table."""
        columns = ", ".join(f'"{name}" {kind}' for name, kind in self.columns.items())
        key = ", ".join(f'"{name}"' for name in self.key)
        return f'CREATE TABLE "{self.name}" ({columns}, PRIMARY KEY ({key}))'


def _numbers(*names: str) -> dict[str, str]:
    """Describe several numeric columns."""
    return dict.fromkeys(names, NUMBER)


def _spec(name: str, key: tuple[str, ...], time_column: str, columns: dict[str, str]) -> TableSpec:
    """Build a table description."""
    return TableSpec(name, key, MappingProxyType(columns), time_column)


_ID: Final = ("samsung_id",)
_SPAN: Final = {"samsung_id": TEXT, "start_at": MOMENT, "end_at": MOMENT, "utc_offset_min": NUMBER}
_NIGHT_POINT: Final = {"night_samsung_id": TEXT, "start_utc": MOMENT, "start_at": MOMENT}
_NIGHT_KEY: Final = ("night_samsung_id", "start_utc")
_POINT: Final = {"start_utc": MOMENT, "start_at": MOMENT}
_DAY: Final = {"samsung_id": TEXT, "day": MOMENT}

_SPECS: Final = (
    _spec(
        "sleep_session",
        _ID,
        "start_at",
        {
            **_SPAN,
            "night_date": MOMENT,
            "duration_min": NUMBER,
            "fragment_count": WHOLE,
            "is_night": FLAG,
            **_numbers(
                "score",
                "efficiency_pct",
                "latency_min",
                "cycles",
                "light_min",
                "rem_min",
                "physical_recovery",
                "mental_recovery",
                "movement_awakening",
            ),
        },
    ),
    _spec(
        "sleep_stage",
        _ID,
        "start_at",
        {
            "samsung_id": TEXT,
            "session_id": TEXT,
            "start_at": MOMENT,
            "end_at": MOMENT,
            "stage_code": WHOLE,
            "duration_min": NUMBER,
        },
    ),
    _spec(
        "spo2_night",
        _ID,
        "start_at",
        {
            **_SPAN,
            **_numbers("spo2_avg", "spo2_min", "spo2_max", "low_seconds", "coverage_pct"),
        },
    ),
    _spec(
        "spo2_interval",
        _NIGHT_KEY,
        "start_at",
        {
            **_NIGHT_POINT,
            "end_at": MOMENT,
            **_numbers("spo2_avg", "spo2_min", "spo2_max"),
            "is_irregular": FLAG,
        },
    ),
    _spec(
        "skin_temperature",
        _ID,
        "start_at",
        {
            **_SPAN,
            **_numbers(
                "temperature_c", "baseline_c", "min_c", "max_c", "lower_bound_c", "upper_bound_c"
            ),
        },
    ),
    _spec(
        "skin_temperature_minute",
        _NIGHT_KEY,
        "start_at",
        {**_NIGHT_POINT, **_numbers("mean_c", "min_c", "max_c")},
    ),
    _spec(
        "respiratory_rate",
        _ID,
        "start_at",
        {**_SPAN, **_numbers("rate_avg", "lower_limit", "upper_limit"), "is_outlier": FLAG},
    ),
    _spec("respiratory_rate_minute", _NIGHT_KEY, "start_at", {**_NIGHT_POINT, **_numbers("rate")}),
    _spec("snoring_event", _ID, "start_at", {**_SPAN, **_numbers("duration_s")}),
    _spec(
        "heart_rate_minute",
        ("start_utc",),
        "start_at",
        {**_POINT, **_numbers("heart_rate", "heart_rate_min", "heart_rate_max")},
    ),
    _spec(
        "hrv_window",
        ("start_utc",),
        "start_at",
        {**_POINT, "end_at": MOMENT, **_numbers("rmssd_ms", "sdnn_ms")},
    ),
    _spec("stress", _ID, "start_at", {**_SPAN, **_numbers("score", "score_min", "score_max")}),
    _spec(
        "ecg",
        _ID,
        "start_at",
        {
            "samsung_id": TEXT,
            "start_at": MOMENT,
            "utc_offset_min": NUMBER,
            "mean_hr": NUMBER,
            "classification_code": WHOLE,
            "sample_frequency_hz": WHOLE,
            "sample_count": WHOLE,
            "trace_file": TEXT,
        },
    ),
    _spec(
        "exercise",
        _ID,
        "start_at",
        {
            **_SPAN,
            "duration_min": NUMBER,
            "type_code": WHOLE,
            "custom_id": TEXT,
            **_numbers(
                "calorie_kcal",
                "distance_m",
                "mean_hr",
                "max_hr",
                "min_hr",
                "mean_speed_mps",
                "vo2_max",
            ),
        },
    ),
    _spec(
        "weight",
        _ID,
        "measured_at",
        {
            "samsung_id": TEXT,
            "measured_at": MOMENT,
            "utc_offset_min": NUMBER,
            **_numbers(
                "weight_kg",
                "height_cm",
                "body_fat_pct",
                "skeletal_muscle_mass_kg",
                "basal_metabolic_rate_kcal",
            ),
        },
    ),
    _spec(
        "steps_day", ("day",), "day", {**_DAY, **_numbers("steps", "distance_m", "calorie_kcal")}
    ),
    _spec(
        "steps_interval",
        ("day", "interval"),
        "day",
        {
            "day": MOMENT,
            "interval": WHOLE,
            "start_at": MOMENT,
            **_numbers("steps", "distance_m", "calorie_kcal"),
        },
    ),
    _spec(
        "activity_day",
        ("day",),
        "day",
        {
            **_DAY,
            **_numbers(
                "steps",
                "active_min",
                "walk_min",
                "run_min",
                "exercise_min",
                "distance_m",
                "active_calorie_kcal",
                "floors",
            ),
        },
    ),
    _spec(
        "vitality_day",
        ("day",),
        "day",
        {**_DAY, **_numbers("energy_score", "sleeping_hr", "sleeping_hrv_ms")},
    ),
    _spec("movement_minute", ("start_utc",), "start_at", {**_POINT, **_numbers("activity_level")}),
)

DETAIL_TABLES: Final = MappingProxyType({spec.name: spec for spec in _SPECS})
"""Every table the merge writes to, by name."""

CONTROL_STATEMENTS: Final = (
    "CREATE TABLE schema_version (version INTEGER PRIMARY KEY, applied_at TIMESTAMP NOT NULL)",
    """CREATE TABLE import_log (
        import_id INTEGER PRIMARY KEY,
        imported_at TIMESTAMP NOT NULL,
        file_name VARCHAR NOT NULL,
        samsung_app_version VARCHAR,
        exported_at TIMESTAMP NOT NULL,
        first_date DATE,
        last_date DATE
    )""",
    """CREATE TABLE import_table (
        import_id INTEGER NOT NULL,
        table_name VARCHAR NOT NULL,
        new_count BIGINT NOT NULL,
        updated_count BIGINT NOT NULL,
        unchanged_count BIGINT NOT NULL,
        kept_count BIGINT NOT NULL,
        superseded_count BIGINT NOT NULL,
        rejected_count BIGINT NOT NULL,
        PRIMARY KEY (import_id, table_name)
    )""",
    """CREATE TABLE import_failure (
        import_id INTEGER NOT NULL,
        domain VARCHAR NOT NULL,
        reason VARCHAR NOT NULL,
        PRIMARY KEY (import_id, domain)
    )""",
    """CREATE TABLE record_history (
        table_name VARCHAR NOT NULL,
        key VARCHAR NOT NULL,
        replaced_at TIMESTAMP NOT NULL,
        import_id INTEGER NOT NULL,
        previous_values VARCHAR NOT NULL
    )""",
    """CREATE TABLE validation_issue (
        import_id INTEGER NOT NULL,
        table_name VARCHAR NOT NULL,
        key VARCHAR NOT NULL,
        rule VARCHAR NOT NULL,
        value VARCHAR,
        action VARCHAR NOT NULL
    )""",
    """CREATE TABLE sleep_stage_code (
        code INTEGER PRIMARY KEY, name VARCHAR NOT NULL, is_verified BOOLEAN NOT NULL
    )""",
    """CREATE TABLE exercise_type_code (
        code INTEGER PRIMARY KEY, name VARCHAR NOT NULL, is_verified BOOLEAN NOT NULL
    )""",
)
"""Tables that describe the imports and the codes, not the health records."""

OWN_STATEMENTS: Final = (
    """CREATE TABLE tag (
        tag_id INTEGER PRIMARY KEY, name VARCHAR NOT NULL UNIQUE, is_active BOOLEAN NOT NULL
    )""",
    """CREATE TABLE annotation (
        day DATE NOT NULL,
        tag_id INTEGER NOT NULL,
        note VARCHAR,
        created_at TIMESTAMP NOT NULL,
        updated_at TIMESTAMP NOT NULL,
        PRIMARY KEY (day, tag_id)
    )""",
    """CREATE TABLE user_profile (
        name VARCHAR, birth_year INTEGER, sex VARCHAR, height_cm DOUBLE
    )""",
)
"""Tables the user fills in. A merge never touches them."""

SLEEP_STAGE_CODES: Final = (
    (40001, "awake", False),
    (40002, "light", True),
    (40003, "deep", False),
    (40004, "rem", True),
)
"""Stage codes from the data dictionary. Verified ones match Samsung's own totals."""

EXERCISE_TYPE_CODES: Final = (
    (0, "other", False),
    (1001, "walking", False),
    (1002, "running", False),
    (10007, "unidentified", False),
    (11007, "cycling", False),
    (14001, "weights", False),
    (14003, "circuit", False),
)
"""Standard exercise codes seen so far. Samsung does not export their names."""
