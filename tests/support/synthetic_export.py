"""Build a small fake Samsung Health export for tests.

The files follow the real export format observed in stage 0:

* Each CSV starts with a byte-order mark and a metadata line
  ``<full table name>,<app version>,<schema version>``.
* The header mixes bare column names with names prefixed by ``com.samsung.health...``.
* Every data row ends with a trailing comma.
* Times are UTC text; each row carries its own ``time_offset``.
* Detail series live in ``jsons/<full table name>/<first id character>/<file>``.

The content is deterministic: the same arguments always produce the same files and
the same record ids. Building two exports with a different number of days therefore
imitates two real exports taken on different dates, which is what the merge tests need.

No real health data is used anywhere in this module.
"""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from pathlib import Path
from typing import Final

APP_VERSION: Final = "7013005"
DEVICE: Final = "TestDevice/"
PACKAGE: Final = "com.sec.android.app.shealth"
FIRST_DAY: Final = date(2026, 1, 1)

_NAMESPACE: Final = uuid.UUID("6f1d2c1e-0000-4000-8000-000000000001")
_SLEEP: Final = "com.samsung.health.sleep."
_SPO2: Final = "com.samsung.health.oxygen_saturation."
_HR: Final = "com.samsung.health.heart_rate."

STAGE_AWAKE: Final = 40001
STAGE_LIGHT: Final = 40002
STAGE_DEEP: Final = 40003
STAGE_REM: Final = 40004

NIGHT_STAGES: Final = (
    (STAGE_LIGHT, 120),
    (STAGE_DEEP, 60),
    (STAGE_REM, 90),
    (STAGE_AWAKE, 30),
    (STAGE_LIGHT, 150),
)
"""Stages of every synthetic night, as (code, minutes). They add up to 450 minutes."""

NIGHT_MINUTES: Final = sum(minutes for _, minutes in NIGHT_STAGES)
NAP_MINUTES: Final = 60
LOW_OXYGEN_NIGHT: Final = 2
"""Index of the night that has two 10-minute intervals under 90 % oxygen."""

PARTIAL_DAY_STEPS: Final = 2000
"""Steps of the export day when the export is taken before the day ends."""


@dataclass(frozen=True, slots=True)
class TableSpec:
    """Layout of one synthetic table.

    Attributes:
        namespace: ``shealth`` or ``health``, as in the real file name.
        schema_version: Version written on the metadata line.
        header: Column names exactly as Samsung writes them.
    """

    namespace: str
    schema_version: int
    header: tuple[str, ...]


TABLES: Final[dict[str, TableSpec]] = {
    "sleep": TableSpec(
        "shealth",
        12,
        (
            "integrated_id",
            "total_rem_duration",
            "combined_id",
            "sleep_latency",
            "sleep_cycle",
            "total_light_duration",
            "efficiency",
            "sleep_score",
            "sleep_duration",
            _SLEEP + "start_time",
            _SLEEP + "update_time",
            _SLEEP + "create_time",
            _SLEEP + "time_offset",
            _SLEEP + "deviceuuid",
            _SLEEP + "pkg_name",
            _SLEEP + "end_time",
            _SLEEP + "datauuid",
        ),
    ),
    "sleep_stage": TableSpec(
        "health",
        7,
        (
            "start_time",
            "sleep_id",
            "update_time",
            "create_time",
            "stage",
            "time_offset",
            "deviceuuid",
            "pkg_name",
            "end_time",
            "datauuid",
        ),
    ),
    "tracker.oxygen_saturation": TableSpec(
        "shealth",
        5,
        (
            "tag_id",
            "coverage_rate",
            _SPO2 + "start_time",
            _SPO2 + "update_time",
            _SPO2 + "create_time",
            _SPO2 + "low_duration",
            _SPO2 + "binning",
            _SPO2 + "max",
            _SPO2 + "min",
            _SPO2 + "spo2",
            _SPO2 + "time_offset",
            _SPO2 + "deviceuuid",
            _SPO2 + "pkg_name",
            _SPO2 + "end_time",
            _SPO2 + "datauuid",
        ),
    ),
    "tracker.heart_rate": TableSpec(
        "shealth",
        3,
        (
            "tag_id",
            _HR + "heart_beat_count",
            _HR + "start_time",
            _HR + "binning_data",
            _HR + "update_time",
            _HR + "create_time",
            _HR + "max",
            _HR + "min",
            _HR + "time_offset",
            _HR + "deviceuuid",
            _HR + "pkg_name",
            _HR + "end_time",
            _HR + "datauuid",
            _HR + "heart_rate",
        ),
    ),
    "sleep_snoring": TableSpec(
        "shealth",
        3,
        (
            "duration",
            "create_sh_ver",
            "start_time",
            "custom",
            "modify_sh_ver",
            "update_time",
            "create_time",
            "time_offset",
            "deviceuuid",
            "pkg_name",
            "end_time",
            "datauuid",
        ),
    ),
    "step_daily_trend": TableSpec(
        "shealth",
        6,
        (
            "binning_data",
            "update_time",
            "create_time",
            "source_pkg_name",
            "source_type",
            "count",
            "speed",
            "distance",
            "calorie",
            "deviceuuid",
            "pkg_name",
            "datauuid",
            "day_time",
        ),
    ),
}
"""The Samsung tables the synthetic export contains."""

Row = dict[str, str]


@dataclass(frozen=True, slots=True)
class SyntheticExport:
    """Result of building a synthetic export.

    Attributes:
        root: Folder that holds the CSV files and the ``jsons`` folder.
        stamp: Timestamp used in every file name, as Samsung does.
        n_days: Calendar days the export covers; the last one is the export day.
    """

    root: Path
    stamp: str
    n_days: int

    def csv_path(self, table: str) -> Path:
        """Return the path of the CSV file of ``table``."""
        spec = TABLES[table]
        return self.root / f"com.samsung.{spec.namespace}.{table}.{self.stamp}.csv"

    def json_path(self, table: str, file_name: str) -> Path:
        """Return the path of a detail file referenced from a CSV cell."""
        spec = TABLES[table]
        folder = f"com.samsung.{spec.namespace}.{table}"
        return self.root / "jsons" / folder / file_name[0] / file_name


def record_id(table: str, key: str) -> str:
    """Return the stable id of a synthetic record.

    The id depends only on the table and the logical key, never on the export, so
    the same record keeps its id across exports as Samsung's ``datauuid`` does.

    Args:
        table: Table name.
        key: Logical key of the record inside the table.

    Returns:
        A UUID as text.
    """
    return str(uuid.uuid5(_NAMESPACE, f"{table}:{key}"))


def offset_for_night(index: int) -> timedelta:
    """Return the UTC offset of a night. Night 1 is UTC-4; the rest are UTC-3."""
    return timedelta(hours=-4) if index == 1 else timedelta(hours=-3)


def day_steps(index: int) -> int:
    """Return the full-day step total of day ``index``."""
    return 6000 + 500 * index


def _offset_text(offset: timedelta) -> str:
    """Format an offset the way Samsung does, for example ``UTC-0300``."""
    minutes = int(offset.total_seconds() // 60)
    sign = "-" if minutes < 0 else "+"
    hours, rest = divmod(abs(minutes), 60)
    return f"UTC{sign}{hours:02d}{rest:02d}"


def _utc_text(moment: datetime) -> str:
    """Format a UTC moment as Samsung writes it in CSV cells."""
    return moment.strftime("%Y-%m-%d %H:%M:%S.") + f"{moment.microsecond // 1000:03d}"


def _epoch_ms(moment: datetime) -> int:
    """Return a UTC moment as milliseconds since 1970, as used in detail files."""
    return int(moment.replace(tzinfo=UTC).timestamp() * 1000)


def _local_to_utc(day: date, at: time, offset: timedelta) -> datetime:
    """Convert a local date and time to a naive UTC moment."""
    return datetime.combine(day, at) - offset


def _common(start: datetime, end: datetime, offset: timedelta, ident: str) -> Row:
    """Return the cells every time-based record shares."""
    return {
        "start_time": _utc_text(start),
        "end_time": _utc_text(end),
        "update_time": _utc_text(end),
        "create_time": _utc_text(end),
        "time_offset": _offset_text(offset),
        "deviceuuid": DEVICE,
        "pkg_name": PACKAGE,
        "datauuid": ident,
    }


class _Builder:
    """Collect the rows and detail files of one export and write them to disk."""

    def __init__(self, export: SyntheticExport) -> None:
        """Start an empty export.

        Args:
            export: Where the files go and how they are named.
        """
        self.export = export
        self.rows: dict[str, list[Row]] = {table: [] for table in TABLES}
        self.details: list[tuple[str, str, object]] = []

    def add_detail(self, table: str, ident: str, suffix: str, content: object) -> str:
        """Register a detail file and return the name to put in the CSV cell."""
        file_name = f"{ident}.{suffix}"
        self.details.append((table, file_name, content))
        return file_name

    def add_sleep(self, key: str, start: datetime, minutes: int, offset: timedelta) -> None:
        """Add one sleep session with its stages.

        Args:
            key: Logical key of the session.
            start: Sleep onset in UTC.
            minutes: Session length.
            offset: UTC offset of the session.
        """
        ident = record_id("sleep", key)
        end = start + timedelta(minutes=minutes)
        stages = NIGHT_STAGES if minutes == NIGHT_MINUTES else ((STAGE_LIGHT, minutes),)
        light = sum(m for code, m in stages if code == STAGE_LIGHT)
        rem = sum(m for code, m in stages if code == STAGE_REM)
        awake = sum(m for code, m in stages if code == STAGE_AWAKE)
        row = _common(start, end, offset, ident)
        row.update(
            {
                "sleep_duration": str(minutes),
                "sleep_score": "80",
                "efficiency": str(round(100 * (minutes - awake) / minutes)),
                "sleep_latency": "600000",
                "sleep_cycle": "4",
                "total_light_duration": str(light),
                "total_rem_duration": str(rem),
            }
        )
        self.rows["sleep"].append(row)
        cursor = start
        for position, (code, length) in enumerate(stages):
            stage_end = cursor + timedelta(minutes=length)
            stage_row = _common(
                cursor, stage_end, offset, record_id("sleep_stage", f"{key}:{position}")
            )
            stage_row.update({"sleep_id": ident, "stage": str(code)})
            self.rows["sleep_stage"].append(stage_row)
            cursor = stage_end

    def add_oxygen(self, index: int, start: datetime, offset: timedelta) -> None:
        """Add the overnight oxygen record of night ``index`` with 10-minute intervals."""
        ident = record_id("tracker.oxygen_saturation", f"night:{index}")
        end = start + timedelta(minutes=NIGHT_MINUTES)
        low_intervals = {10, 11} if index == LOW_OXYGEN_NIGHT else set()
        bins = []
        for position in range(NIGHT_MINUTES // 10):
            low = position in low_intervals
            bin_start = start + timedelta(minutes=10 * position)
            bins.append(
                {
                    "spo2": 89 if low else 96,
                    "spo2_max": 92 if low else 98,
                    "spo2_min": 86 if low else 94,
                    "start_time": _epoch_ms(bin_start),
                    "end_time": _epoch_ms(bin_start + timedelta(seconds=599)),
                    "isIrregular": 0,
                }
            )
        row = _common(start, end, offset, ident)
        row.update(
            {
                "tag_id": "31301",
                "coverage_rate": "98.0",
                "spo2": "96.0",
                "min": "86.0" if low_intervals else "94.0",
                "max": "98.0",
                "low_duration": str(600 * len(low_intervals)) + ".0",
                "binning": self.add_detail(
                    "tracker.oxygen_saturation",
                    ident,
                    "com.samsung.health.oxygen_saturation.binning.json",
                    bins,
                ),
            }
        )
        self.rows["tracker.oxygen_saturation"].append(row)

    def add_spot_oxygen(self, moment: datetime, offset: timedelta) -> None:
        """Add one manual spot oxygen measurement, which is not a night record."""
        row = _common(moment, moment, offset, record_id("tracker.oxygen_saturation", "spot:0"))
        row.update({"tag_id": "31000", "spo2": "97.0"})
        self.rows["tracker.oxygen_saturation"].append(row)

    def add_heart_rate(self, index: int, start: datetime, offset: timedelta) -> None:
        """Add two hourly heart-rate records for night ``index``, with one bin per minute."""
        for hour in range(2):
            ident = record_id("tracker.heart_rate", f"night:{index}:{hour}")
            hour_start = start + timedelta(hours=hour)
            bins = []
            for minute in range(60):
                bin_start = hour_start + timedelta(minutes=minute)
                bins.append(
                    {
                        "heart_rate": 55.0 + hour,
                        "heart_rate_max": 58.0 + hour,
                        "heart_rate_min": 52.0 + hour,
                        "start_time": _epoch_ms(bin_start),
                        "end_time": _epoch_ms(bin_start + timedelta(seconds=59)),
                    }
                )
            row = _common(hour_start, hour_start + timedelta(hours=1), offset, ident)
            row.update(
                {
                    "tag_id": "21313",
                    "heart_beat_count": "1",
                    "heart_rate": str(55.0 + hour),
                    "min": str(52.0 + hour),
                    "max": str(58.0 + hour),
                    "binning_data": self.add_detail(
                        "tracker.heart_rate",
                        ident,
                        "com.samsung.health.heart_rate.binning_data.json",
                        bins,
                    ),
                }
            )
            self.rows["tracker.heart_rate"].append(row)

    def add_snoring(self, index: int, start: datetime, offset: timedelta) -> None:
        """Add two snoring events of two minutes each to night ``index``."""
        for position in range(2):
            event_start = start + timedelta(minutes=60 + 30 * position)
            event_end = event_start + timedelta(minutes=2)
            ident = record_id("sleep_snoring", f"night:{index}:{position}")
            row = _common(event_start, event_end, offset, ident)
            row.update({"duration": "120000", "create_sh_ver": "70130050"})
            self.rows["sleep_snoring"].append(row)

    def add_invalid_snoring(self) -> None:
        """Add a snoring event dated 1970, as the real export contains."""
        moment = datetime(1970, 1, 1, 0, 0, 0)
        row = _common(moment, moment, timedelta(hours=-3), record_id("sleep_snoring", "invalid:0"))
        row.update({"duration": "0", "create_sh_ver": "70130050"})
        self.rows["sleep_snoring"].append(row)

    def add_steps(self, index: int, day: date, total: int) -> None:
        """Add the three step rows Samsung writes per day.

        Source type -2 is the day total and carries 144 ten-minute bins that add up
        to it. Source types 109 and 0 are partial sources.

        Args:
            index: Day index, used in the record ids.
            day: Calendar day.
            total: Steps of the day in this export.
        """
        day_text = _utc_text(datetime.combine(day, time(0, 0)))
        for source, share in ((-2, 1.0), (109, 0.9), (0, 0.5)):
            count = round(total * share)
            ident = record_id("step_daily_trend", f"day:{index}:{source}")
            active = range(48, 120)
            base, extra = divmod(count, len(active))
            bins = []
            for position in range(144):
                steps = 0
                if position in active:
                    steps = base + (extra if position == active.start else 0)
                bins.append(
                    {
                        "count": steps,
                        "distance": round(steps * 0.75, 2),
                        "calorie": round(steps * 0.04, 2),
                        "speed": 1.3 if steps else 0.0,
                    }
                )
            self.rows["step_daily_trend"].append(
                {
                    "binning_data": self.add_detail(
                        "step_daily_trend", ident, "binning_data.json", bins
                    ),
                    "update_time": day_text,
                    "create_time": day_text,
                    "source_pkg_name": PACKAGE,
                    "source_type": str(source),
                    "count": str(count),
                    "speed": "1.3",
                    "distance": str(round(count * 0.75, 2)),
                    "calorie": str(round(count * 0.04, 2)),
                    "deviceuuid": DEVICE,
                    "pkg_name": PACKAGE,
                    "datauuid": ident,
                    "day_time": day_text,
                }
            )

    def write(self) -> None:
        """Write every CSV and detail file of the export."""
        self.export.root.mkdir(parents=True, exist_ok=True)
        for table, spec in TABLES.items():
            lines = [f"com.samsung.{spec.namespace}.{table},{APP_VERSION},{spec.schema_version}"]
            lines.append(",".join(spec.header))
            for row in self.rows[table]:
                cells = [row.get(column.rsplit(".", 1)[-1], "") for column in spec.header]
                if any("," in cell or '"' in cell for cell in cells):
                    msg = f"cell with a comma or quote in table {table}"
                    raise ValueError(msg)
                lines.append(",".join(cells) + ",")
            text = "\n".join(lines) + "\n"
            self.export.csv_path(table).write_text(text, encoding="utf-8-sig", newline="\n")
        for table, file_name, content in self.details:
            path = self.export.json_path(table, file_name)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(content), encoding="utf-8")


def build_export(
    dest: Path,
    *,
    n_days: int = 4,
    last_day_complete: bool = False,
    with_invalid_rows: bool = True,
) -> SyntheticExport:
    """Write a synthetic Samsung Health export and return its description.

    The export covers ``n_days`` calendar days starting on 1 January 2026. The last
    day is the export day: it has no night yet, and its step total is partial
    unless ``last_day_complete`` is true. Every earlier day has one night of 450
    minutes that starts at 23:30 local time. Day 1 also has a 60-minute nap, night 1
    is in UTC-4 and night 2 has two intervals of low oxygen.

    Args:
        dest: Folder under which the export folder is created.
        n_days: Calendar days to generate; at least 2.
        last_day_complete: Give the export day its full step total.
        with_invalid_rows: Include the kind of broken rows the real export contains.

    Returns:
        The location and shape of the export.

    Raises:
        ValueError: If ``n_days`` is less than 2.
    """
    if n_days < 2:
        msg = "n_days must be at least 2"
        raise ValueError(msg)
    last_day = FIRST_DAY + timedelta(days=n_days - 1)
    stamp = last_day.strftime("%Y%m%d") + "180000"
    export = SyntheticExport(root=dest / f"samsunghealth_test_{stamp}", stamp=stamp, n_days=n_days)
    builder = _Builder(export)

    for index in range(n_days):
        day = FIRST_DAY + timedelta(days=index)
        is_export_day = index == n_days - 1
        partial = is_export_day and not last_day_complete
        builder.add_steps(index, day, PARTIAL_DAY_STEPS if partial else day_steps(index))
        if is_export_day:
            continue
        offset = offset_for_night(index)
        start = _local_to_utc(day, time(23, 30), offset)
        builder.add_sleep(f"night:{index}", start, NIGHT_MINUTES, offset)
        builder.add_oxygen(index, start, offset)
        builder.add_heart_rate(index, start, offset)
        builder.add_snoring(index, start, offset)

    nap_offset = timedelta(hours=-3)
    nap_day = FIRST_DAY + timedelta(days=1)
    builder.add_sleep(
        "nap:1", _local_to_utc(nap_day, time(15, 0), nap_offset), NAP_MINUTES, nap_offset
    )
    builder.add_spot_oxygen(_local_to_utc(FIRST_DAY, time(12, 0), nap_offset), nap_offset)
    if with_invalid_rows:
        builder.add_invalid_snoring()
    builder.write()
    return export
