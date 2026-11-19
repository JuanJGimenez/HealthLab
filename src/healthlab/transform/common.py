"""Building blocks shared by every domain transformer.

A transformer turns raw Samsung tables, read as text, into clean HealthLab tables:
local times, numbers with known units, names from the data dictionary. Along the
way it validates content and records every record it rejects or keeps with a
caveat as a ``ValidationIssue``, so nothing disappears silently.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, Final, Protocol

import pandas as pd

from healthlab.config import EARLIEST_VALID_YEAR, ValueRange
from healthlab.reading.errors import DetailFileError

UTC_TEXT_FORMAT: Final = "%Y-%m-%d %H:%M:%S.%f"
"""How Samsung writes moments and days in CSV cells."""

OFFSET_PATTERN: Final = r"UTC([+-])(\d{2})(\d{2})"
"""How Samsung writes a UTC offset, for example ``UTC-0300``."""

FUTURE_MARGIN: Final = timedelta(days=2)
"""Slack allowed after the export moment before a record counts as dated in the future.

The export timestamp is in the phone's local time and records carry their own
offsets, so a record taken minutes before exporting in another time zone can
appear to be a few hours ahead.
"""

REJECTED: Final = "rejected"
KEPT: Final = "kept"


class TransformError(Exception):
    """A domain cannot be transformed, for example because a needed column is gone."""


class Source(Protocol):
    """What a transformer needs from an export."""

    @property
    def exported_at(self) -> datetime:
        """Moment the export was taken."""
        ...

    def has(self, name: str) -> bool:
        """Tell whether the export contains the table ``name``."""
        ...

    def read(self, name: str) -> pd.DataFrame:
        """Read a table as text."""
        ...

    def detail(self, name: str, file_name: str) -> Any:
        """Load a detail file referenced from a cell of table ``name``."""
        ...


@dataclass(frozen=True, slots=True)
class ValidationIssue:
    """One record, or group of values, that failed a content check.

    Attributes:
        table: HealthLab table the record was meant for.
        key: Identifier of the record, usually Samsung's id.
        rule: Stable name of the check that failed.
        value: The offending value, or a count when the issue covers several values.
        action: ``rejected`` when the record was left out, ``kept`` when it was
            stored and the issue is only a notice.
    """

    table: str
    key: str
    rule: str
    value: str
    action: str = REJECTED


@dataclass(slots=True)
class DomainResult:
    """Output of one domain transformer.

    Attributes:
        tables: Clean HealthLab tables by name.
        issues: Records rejected or kept with a caveat.
    """

    tables: dict[str, pd.DataFrame] = field(default_factory=dict)
    issues: list[ValidationIssue] = field(default_factory=list)


def require_columns(frame: pd.DataFrame, table: str, columns: Iterable[str]) -> None:
    """Fail when a raw table lacks a column the transformer cannot work without.

    Args:
        frame: Raw table.
        table: Samsung table name, for the error message.
        columns: Names that must be present.

    Raises:
        TransformError: If any column is missing.
    """
    missing = sorted(set(columns) - set(frame.columns))
    if missing:
        msg = f"{table}: missing required columns: {', '.join(missing)}"
        raise TransformError(msg)


def text_column(frame: pd.DataFrame, name: str) -> pd.Series[str]:
    """Return a column of a raw table, or an all-missing column when it is absent.

    Optional columns come and go between Samsung Health versions; a transformer
    treats a missing optional column as a column without values.

    Args:
        frame: Raw table.
        name: Column name.

    Returns:
        The column as text, aligned with ``frame``.
    """
    if name in frame.columns:
        return frame[name]
    return pd.Series(pd.NA, index=frame.index, dtype="string")


def to_number(values: pd.Series[str]) -> pd.Series[float]:
    """Convert text to numbers; text that is not a number becomes missing.

    Args:
        values: A column read as text.

    Returns:
        The same column as floating point numbers.
    """
    return pd.to_numeric(values, errors="coerce").astype("float64")


def number_column(frame: pd.DataFrame, name: str) -> pd.Series[float]:
    """Return a possibly absent column of a raw table as numbers."""
    return to_number(text_column(frame, name))


def parse_utc(values: pd.Series[str]) -> pd.Series[pd.Timestamp]:
    """Parse moments written as ``YYYY-MM-DD HH:MM:SS.mmm``.

    Args:
        values: A column of moments as text.

    Returns:
        The moments; text in any other shape becomes missing.
    """
    return pd.to_datetime(values, format=UTC_TEXT_FORMAT, errors="coerce")


def offset_minutes(values: pd.Series[str]) -> pd.Series[float]:
    """Convert offsets such as ``UTC-0300`` into minutes east of UTC.

    Args:
        values: A column of offsets as text.

    Returns:
        Minutes to add to UTC to get local time; missing where the text is not
        an offset.
    """
    parts = values.str.extract("^" + OFFSET_PATTERN + "$")
    minutes = to_number(parts[1]) * 60 + to_number(parts[2])
    return minutes.where(parts[0] != "-", -minutes)


def epoch_ms_to_local(milliseconds: Iterable[float], offset_min: float) -> pd.DatetimeIndex:
    """Convert UTC milliseconds since 1970 into local moments.

    Detail files carry no offset of their own; the caller passes the offset of the
    record that names the file.

    Args:
        milliseconds: Moments as written in a detail file.
        offset_min: Minutes east of UTC.

    Returns:
        The local moments, without time zone information.
    """
    moments = pd.to_datetime(list(milliseconds), unit="ms")
    return pd.DatetimeIndex(moments + pd.Timedelta(minutes=offset_min))


def report(
    issues: list[ValidationIssue],
    frame: pd.DataFrame,
    mask: pd.Series[bool],
    *,
    table: str,
    rule: str,
    value: pd.Series[Any],
    key: str = "samsung_id",
    action: str = REJECTED,
) -> None:
    """Record one issue per row selected by ``mask``.

    Args:
        issues: List the issues are appended to.
        frame: Table under validation.
        mask: Rows that failed the check.
        table: HealthLab table the rows were meant for.
        rule: Stable name of the check.
        value: Column holding the offending values.
        key: Column of ``frame`` that identifies a row.
        action: ``rejected`` or ``kept``.
    """
    selected = mask.fillna(False).astype(bool)
    for ident, bad in zip(frame.loc[selected, key], value[selected], strict=True):
        issues.append(ValidationIssue(table, str(ident), rule, str(bad), action))


def prepare_timed(
    raw: pd.DataFrame,
    *,
    samsung_table: str,
    table: str,
    exported_at: datetime,
    issues: list[ValidationIssue],
    with_end: bool = True,
) -> pd.DataFrame:
    """Give a raw time-based table its id, local times and offset; drop bad rows.

    Rows are rejected, and reported, when their id is missing, their time or
    offset cannot be read, or their date is before 2020 or after the export.

    Args:
        raw: Raw table with ``datauuid``, ``start_time`` and ``time_offset``.
        samsung_table: Samsung table name, for error messages.
        table: HealthLab table the rows are meant for, for the issues.
        exported_at: Moment the export was taken.
        issues: List the issues are appended to.
        with_end: Whether the table has an ``end_time`` to convert too.

    Returns:
        The surviving rows with their raw columns plus ``samsung_id``,
        ``start_at``, ``utc_offset_min`` and, when asked, ``end_at``.

    Raises:
        TransformError: If a required column is missing.
    """
    needed = ["datauuid", "start_time", "time_offset", *(["end_time"] if with_end else [])]
    require_columns(raw, samsung_table, needed)
    frame = raw.copy()
    frame["samsung_id"] = frame["datauuid"]
    offset = offset_minutes(frame["time_offset"])
    shift = pd.to_timedelta(offset, unit="m")
    frame["utc_offset_min"] = offset
    frame["start_at"] = parse_utc(frame["start_time"]) + shift
    if with_end:
        frame["end_at"] = parse_utc(frame["end_time"]) + shift

    no_id = frame["samsung_id"].isna()
    report(
        issues,
        frame.assign(samsung_id="?"),
        no_id,
        table=table,
        rule="missing_id",
        value=frame["start_time"],
    )
    frame = frame[~no_id]

    unreadable = frame["start_at"].isna()
    if with_end:
        unreadable |= frame["end_at"].isna()
    report(
        issues, frame, unreadable, table=table, rule="unreadable_time", value=frame["start_time"]
    )
    frame = frame[~unreadable]

    too_old = frame["start_at"].dt.year < EARLIEST_VALID_YEAR
    report(issues, frame, too_old, table=table, rule="date_before_2020", value=frame["start_time"])
    frame = frame[~too_old]

    future = frame["start_at"] > pd.Timestamp(exported_at + FUTURE_MARGIN)
    report(issues, frame, future, table=table, rule="date_after_export", value=frame["start_time"])
    return pd.DataFrame(frame[~future]).reset_index(drop=True)


def reject_out_of_range(
    frame: pd.DataFrame,
    columns: Iterable[str],
    allowed: ValueRange,
    *,
    table: str,
    rule: str,
    issues: list[ValidationIssue],
) -> pd.DataFrame:
    """Drop rows where any of ``columns`` has a value outside ``allowed``.

    Missing values pass: a check on range says nothing about absence.

    Args:
        frame: Table with numeric columns and a ``samsung_id`` column.
        columns: Columns to check.
        allowed: Accepted interval, bounds included.
        table: HealthLab table, for the issues.
        rule: Stable name of the check.
        issues: List the issues are appended to.

    Returns:
        The rows that pass.
    """
    result = frame
    for column in columns:
        values = result[column]
        bad = values.notna() & ~values.between(allowed.low, allowed.high)
        report(issues, result, bad, table=table, rule=rule, value=values)
        result = result[~bad]
    return result.reset_index(drop=True)


def parse_day(values: pd.Series[str]) -> pd.Series[pd.Timestamp]:
    """Parse the ``day_time`` column of a daily table.

    Samsung writes the local day as its midnight, ``YYYY-MM-DD 00:00:00.000``.

    Args:
        values: The column as text.

    Returns:
        The days at midnight; any other text becomes missing.
    """
    return parse_utc(values).dt.normalize()


def _read_measurements(source: Source, samsung_table: str, file_name: str) -> tuple[list[Any], str]:
    """Read the measurements of one detail file.

    Args:
        source: The export.
        samsung_table: Samsung table the file belongs to.
        file_name: Name of the detail file.

    Returns:
        The measurements that carry a ``start_time``, and the validation rule
        that explains why there are none: empty when there are measurements.
    """
    try:
        content = source.detail(samsung_table, file_name)
    except DetailFileError:
        return [], "detail_file_unreadable"
    items = [item for item in content if "start_time" in item] if isinstance(content, list) else []
    return items, "" if items else "detail_file_empty"


def _joined(parts: list[pd.DatetimeIndex]) -> pd.DatetimeIndex:
    """Return the moments of every part as one index, in order."""
    return pd.DatetimeIndex(parts[0].append(parts[1:])) if parts else pd.DatetimeIndex([])


def expand_details(
    source: Source,
    parents: pd.DataFrame,
    *,
    samsung_table: str,
    table: str,
    file_column: str,
    fields: Mapping[str, str],
    issues: list[ValidationIssue],
    with_end: bool = False,
) -> pd.DataFrame:
    """Turn the detail files of a table into one row per measurement.

    Each parent row names a file holding a list of measurements. Every
    measurement has a ``start_time`` in UTC milliseconds; the parent's offset
    converts it to local time.

    A file that is missing, unreadable or not a list is reported and skipped;
    the parent row itself is not affected.

    Args:
        source: The export.
        parents: Rows with ``samsung_id``, ``utc_offset_min`` and ``file_column``.
        samsung_table: Samsung table the files belong to.
        table: HealthLab table being built, for the issues.
        file_column: Column of ``parents`` that names the detail file.
        fields: Measurement keys to keep, mapped to their output column names.
        issues: List the issues are appended to.
        with_end: Whether to keep each measurement's ``end_time`` as ``end_at``.

    Returns:
        One row per measurement with ``parent_id``, ``start_utc``, ``start_at``,
        optionally ``end_at``, and one numeric column per requested field.
        ``start_utc`` identifies the measurement: local times repeat when the
        wearer travels west, UTC moments never do.
    """
    parent_ids: list[str] = []
    utc_starts: list[pd.DatetimeIndex] = []
    starts: list[pd.DatetimeIndex] = []
    ends: list[pd.DatetimeIndex] = []
    columns: dict[str, list[Any]] = {name: [] for name in fields.values()}
    rows = parents.loc[parents[file_column].notna(), ["samsung_id", "utc_offset_min", file_column]]
    for ident, offset, file_name in rows.itertuples(index=False, name=None):
        items, problem = _read_measurements(source, samsung_table, file_name)
        if problem:
            issues.append(ValidationIssue(table, ident, problem, file_name, KEPT))
            continue
        parent_ids.extend([ident] * len(items))
        utc_starts.append(epoch_ms_to_local((item["start_time"] for item in items), 0))
        starts.append(epoch_ms_to_local((item["start_time"] for item in items), offset))
        if with_end:
            ends.append(epoch_ms_to_local((item.get("end_time") for item in items), offset))
        for key, name in fields.items():
            columns[name].extend(item.get(key) for item in items)

    result = pd.DataFrame({"parent_id": pd.Series(parent_ids, dtype="string")})
    result["start_utc"] = _joined(utc_starts)
    result["start_at"] = _joined(starts)
    if with_end:
        result["end_at"] = _joined(ends)
    for name, values in columns.items():
        result[name] = pd.to_numeric(pd.Series(values, dtype="object"), errors="coerce").astype(
            "float64"
        )
    return result


def drop_out_of_range_points(
    points: pd.DataFrame,
    column: str,
    allowed: ValueRange,
    *,
    table: str,
    rule: str,
    issues: list[ValidationIssue],
) -> pd.DataFrame:
    """Drop measurements outside ``allowed``, reporting one issue per parent record.

    A per-minute series can hold thousands of points, so the issue carries the
    number of dropped points of each parent instead of one entry per point.

    Args:
        points: Output of ``expand_details``.
        column: Numeric column to check.
        allowed: Accepted interval, bounds included.
        table: HealthLab table, for the issues.
        rule: Stable name of the check.
        issues: List the issues are appended to.

    Returns:
        The measurements that pass. Missing values pass.
    """
    values = points[column]
    bad = values.notna() & ~values.between(allowed.low, allowed.high)
    for parent, count in points.loc[bad, "parent_id"].value_counts(sort=False).items():
        issues.append(ValidationIssue(table, str(parent), rule, str(int(count))))
    return points[~bad].reset_index(drop=True)


def prepare_daily(
    raw: pd.DataFrame,
    *,
    samsung_table: str,
    table: str,
    exported_at: datetime,
    issues: list[ValidationIssue],
) -> pd.DataFrame:
    """Give a raw daily table its id and day; drop bad and repeated rows.

    Rows are rejected, and reported, when their id is missing, their day cannot
    be read, or their day is before 2020 or after the export. When several rows
    claim the same day, the last one in file order wins and the others are
    reported.

    Args:
        raw: Raw table with ``datauuid`` and ``day_time``.
        samsung_table: Samsung table name, for error messages.
        table: HealthLab table the rows are meant for, for the issues.
        exported_at: Moment the export was taken.
        issues: List the issues are appended to.

    Returns:
        The surviving rows, one per day in day order, with their raw columns plus
        ``samsung_id`` and ``day``.

    Raises:
        TransformError: If a required column is missing.
    """
    require_columns(raw, samsung_table, ["datauuid", "day_time"])
    frame = raw.copy()
    frame["samsung_id"] = frame["datauuid"].fillna("?")
    frame["day"] = parse_day(frame["day_time"])

    no_id = frame["datauuid"].isna()
    report(issues, frame, no_id, table=table, rule="missing_id", value=frame["day_time"])
    frame = frame[~no_id]

    unreadable = frame["day"].isna()
    report(issues, frame, unreadable, table=table, rule="unreadable_day", value=frame["day_time"])
    frame = frame[~unreadable]

    too_old = frame["day"].dt.year < EARLIEST_VALID_YEAR
    report(issues, frame, too_old, table=table, rule="date_before_2020", value=frame["day_time"])
    frame = frame[~too_old]

    future = frame["day"] > pd.Timestamp(exported_at + FUTURE_MARGIN)
    report(issues, frame, future, table=table, rule="date_after_export", value=frame["day_time"])
    frame = frame[~future]

    repeated = frame["day"].duplicated(keep="last")
    report(issues, frame, repeated, table=table, rule="duplicate_day", value=frame["day_time"])
    return pd.DataFrame(frame[~repeated]).sort_values("day").reset_index(drop=True)


def unique_by_utc_start(points: pd.DataFrame) -> pd.DataFrame:
    """Keep one measurement per UTC moment, the last one in file order.

    Two hourly records can overlap by a minute; a series keyed by time stores the
    repeated minute once. The comparison uses the UTC moment, not local time: a
    wearer who flies west lives the same local hour twice, and those are two
    different hours of measurements.

    Args:
        points: Output of ``expand_details``.

    Returns:
        The measurements in time order, without ``parent_id``.
    """
    unique = points.drop_duplicates("start_utc", keep="last").sort_values("start_utc")
    return unique.drop(columns="parent_id").reset_index(drop=True)


def unique_within_parent(points: pd.DataFrame) -> pd.DataFrame:
    """Keep one measurement per parent record and UTC moment, the last in file order.

    A few detail files list the same moment twice. The pair parent and moment is
    the merge key of the series that belong to a night, so it must not repeat.

    Args:
        points: Output of ``expand_details``.

    Returns:
        The measurements without repeats, in their original order.
    """
    unique = points.drop_duplicates(["parent_id", "start_utc"], keep="last")
    return unique.reset_index(drop=True)


def reject_repeated_spans(
    frame: pd.DataFrame, *, table: str, issues: list[ValidationIssue]
) -> pd.DataFrame:
    """Keep one night record per exact start and end, the first one Samsung created.

    Samsung sometimes writes, days later, further records stamped with the start
    and end of a night it had already recorded, each with different values. The
    record created right after the night is the genuine one; the later ones
    cannot be placed on any night and are rejected.

    Args:
        frame: Output of ``prepare_timed``, optionally with ``create_time``.
        table: HealthLab table, for the issues.
        issues: List the issues are appended to.

    Returns:
        The rows without repeated spans, in their original order.
    """
    by_creation = frame.assign(created=text_column(frame, "create_time")).sort_values(
        "created", kind="stable", na_position="last"
    )
    repeated = by_creation.duplicated(["start_at", "end_at"], keep="first").reindex(frame.index)
    report(
        issues, frame, repeated, table=table, rule="repeated_night_span", value=frame["start_time"]
    )
    return frame[~repeated].reset_index(drop=True)
