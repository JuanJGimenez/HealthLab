"""Merge transformed tables into the database without losing anything.

The four rules (see ``docs/merge_rules.md``):

* A record the database does not have is added.
* A record that is identical is left alone.
* A record with different values replaces the stored one, whose previous values
  go to ``record_history``. If the database already holds a more recent export,
  the stored record stays instead: the newest export always wins.
* A record the database has and the export lacks is kept.

``plan_merge`` counts what each rule would do and writes nothing; it feeds the
preview the user confirms. ``apply_merge`` does the work in one transaction.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Any

import pandas as pd

from misalud.config import THRESHOLDS
from misalud.storage.database import Connection
from misalud.storage.errors import MergeError
from misalud.storage.schema import DETAIL_TABLES, TableSpec
from misalud.transform.common import REJECTED, ValidationIssue

FRAME_VIEW = "misalud_incoming_frame"


@dataclass(frozen=True, slots=True)
class ImportInfo:
    """What is known about an export before merging it.

    Attributes:
        file_name: Name of the archive or folder the user chose.
        exported_at: Moment the export was taken.
        samsung_app_version: Samsung Health version that wrote it, when known.
    """

    file_name: str
    exported_at: datetime
    samsung_app_version: str | None = None


@dataclass(frozen=True, slots=True)
class TablePlan:
    """What a merge does, or would do, to one table.

    Attributes:
        table: Table name.
        new: Records added.
        updated: Records replaced, with their previous values saved.
        unchanged: Records already stored with the same values.
        kept: Stored records the export does not have; they stay.
        superseded: Records that differ but stay as stored, because the database
            already holds a more recent export.
        updated_old: Part of ``updated`` dated more than 30 days before the
            export. Samsung normally changes only recent records, so a large
            number here deserves a look before confirming.
    """

    table: str
    new: int
    updated: int
    unchanged: int
    kept: int
    superseded: int = 0
    updated_old: int = 0


@dataclass(frozen=True, slots=True)
class MergePlan:
    """What a merge does, or would do, to the whole database.

    Attributes:
        tables: One entry per incoming table, in table name order.
        first_date: Earliest day covered by the incoming records.
        last_date: Latest day covered by the incoming records.
        is_older_export: Whether the database already holds a more recent export.
    """

    tables: tuple[TablePlan, ...]
    first_date: date | None
    last_date: date | None
    is_older_export: bool

    def total(self, field: str) -> int:
        """Add one count across every table, for example ``total("new")``."""
        return sum(int(getattr(table, field)) for table in self.tables)

    @property
    def changes_anything(self) -> bool:
        """Tell whether applying the plan would write any health record."""
        return self.total("new") + self.total("updated") > 0


@dataclass(frozen=True, slots=True)
class ImportSummary:
    """Result of an applied merge.

    Attributes:
        import_id: Identifier of the import in ``import_log``.
        plan: What the merge did.
    """

    import_id: int
    plan: MergePlan


def _quoted(names: Sequence[str], prefix: str = "") -> str:
    """Return column names quoted and separated by commas, optionally prefixed."""
    return ", ".join(f'{prefix}"{name}"' for name in names)


def _same_key(spec: TableSpec) -> str:
    """Return the SQL condition that pairs a stored row ``t`` with an incoming row ``i``."""
    return " AND ".join(f't."{name}" = i."{name}"' for name in spec.key)


def _differs(spec: TableSpec) -> str:
    """Return the SQL condition that tells a paired row changed any value."""
    return " OR ".join(f't."{name}" IS DISTINCT FROM i."{name}"' for name in spec.value_columns)


def _staged(spec: TableSpec) -> str:
    """Return the name of the temporary table that holds the incoming rows."""
    return f'"incoming_{spec.name}"'


def _one(connection: Connection, sql: str, parameters: Sequence[object] = ()) -> tuple[Any, ...]:
    """Run a query that returns exactly one row."""
    rows = connection.execute(sql, list(parameters)).fetchall()
    return tuple(rows[0])


def _stage(connection: Connection, spec: TableSpec, frame: pd.DataFrame) -> None:
    """Load incoming rows into a temporary table shaped like the real one.

    Nothing in the real tables changes. The temporary table lives in memory and
    disappears with the connection.

    Args:
        connection: An open connection.
        spec: The table the rows are meant for.
        frame: Incoming rows.

    Raises:
        MergeError: If the columns are not the ones the table has, or the key is
            missing or repeated in some row.
    """
    if set(frame.columns) != set(spec.columns):
        missing = sorted(set(spec.columns) - set(frame.columns))
        extra = sorted(set(frame.columns) - set(spec.columns))
        msg = f"{spec.name}: columns do not match the schema (missing {missing}, unknown {extra})"
        raise MergeError(msg)
    casts = ", ".join(
        f'CAST("{name}" AS {kind}) AS "{name}"' for name, kind in spec.columns.items()
    )
    connection.register(FRAME_VIEW, frame)
    try:
        connection.execute(
            f"CREATE OR REPLACE TEMP TABLE {_staged(spec)} AS SELECT {casts} FROM {FRAME_VIEW}"
        )
    finally:
        connection.unregister(FRAME_VIEW)
    no_key = " OR ".join(f'"{name}" IS NULL' for name in spec.key)
    without_key, rows, distinct = _one(
        connection,
        f"SELECT count(*) FILTER (WHERE {no_key}), count(*), "
        f"(SELECT count(*) FROM (SELECT DISTINCT {_quoted(spec.key)} FROM {_staged(spec)})) "
        f"FROM {_staged(spec)}",
    )
    if without_key:
        msg = f"{spec.name}: {without_key} incoming rows have no key"
        raise MergeError(msg)
    if rows != distinct:
        msg = f"{spec.name}: the key repeats in {rows - distinct} incoming rows"
        raise MergeError(msg)


def _stage_all(connection: Connection, tables: Mapping[str, pd.DataFrame]) -> list[TableSpec]:
    """Stage every incoming table and return their descriptions in name order.

    Raises:
        MergeError: If a table is not part of the schema or cannot be staged.
    """
    unknown = sorted(set(tables) - set(DETAIL_TABLES))
    if unknown:
        msg = f"tables not in the schema: {', '.join(unknown)}"
        raise MergeError(msg)
    specs = [DETAIL_TABLES[name] for name in sorted(tables)]
    for spec in specs:
        _stage(connection, spec, tables[spec.name])
    return specs


def _latest_export(connection: Connection) -> datetime | None:
    """Return the export moment of the most recent export already imported."""
    (latest,) = _one(connection, "SELECT max(exported_at) FROM import_log")
    return latest if isinstance(latest, datetime) else None


def _plan_table(
    connection: Connection, spec: TableSpec, *, old_before: datetime, newest_wins: bool
) -> TablePlan:
    """Count what each merge rule does to one staged table."""
    incoming, stored, matched, differing, differing_old = (
        int(value)
        for value in _one(
            connection,
            f"""SELECT
                (SELECT count(*) FROM {_staged(spec)}),
                (SELECT count(*) FROM "{spec.name}"),
                count(*),
                count(*) FILTER (WHERE {_differs(spec)}),
                count(*) FILTER (WHERE ({_differs(spec)}) AND t."{spec.time_column}" < ?)
            FROM "{spec.name}" t JOIN {_staged(spec)} i ON {_same_key(spec)}""",
            [old_before],
        )
    )
    return TablePlan(
        table=spec.name,
        new=incoming - matched,
        updated=differing if newest_wins else 0,
        unchanged=matched - differing,
        kept=stored - matched,
        superseded=0 if newest_wins else differing,
        updated_old=differing_old if newest_wins else 0,
    )


def _plan(connection: Connection, specs: Sequence[TableSpec], exported_at: datetime) -> MergePlan:
    """Build the plan for tables that are already staged."""
    latest = _latest_export(connection)
    is_older = latest is not None and exported_at < latest
    old_before = exported_at - timedelta(days=THRESHOLDS.recalculation_warning_age_days)
    plans = tuple(
        _plan_table(connection, spec, old_before=old_before, newest_wins=not is_older)
        for spec in specs
    )
    moments = [
        _one(
            connection,
            f'SELECT min("{spec.time_column}"), max("{spec.time_column}") FROM {_staged(spec)}',
        )
        for spec in specs
    ]
    firsts = [first for first, _ in moments if isinstance(first, datetime)]
    lasts = [last for _, last in moments if isinstance(last, datetime)]
    return MergePlan(
        tables=plans,
        first_date=min(firsts).date() if firsts else None,
        last_date=max(lasts).date() if lasts else None,
        is_older_export=is_older,
    )


def plan_merge(
    connection: Connection, tables: Mapping[str, pd.DataFrame], *, exported_at: datetime
) -> MergePlan:
    """Count what merging ``tables`` would do, without changing any stored record.

    Args:
        connection: An open connection.
        tables: Transformed tables by name.
        exported_at: Moment the export was taken.

    Returns:
        The counts per table and the period the export covers.

    Raises:
        MergeError: If a table is unknown, has the wrong columns or a broken key.
    """
    return _plan(connection, _stage_all(connection, tables), exported_at)


def _merge_table(
    connection: Connection, spec: TableSpec, *, import_id: int, now: datetime, newest_wins: bool
) -> None:
    """Apply the merge rules to one staged table."""
    table, staged = f'"{spec.name}"', _staged(spec)
    if newest_wins:
        key_text = " || '|' || ".join(f'CAST(t."{name}" AS VARCHAR)' for name in spec.key)
        previous = ", ".join(f'"{name}" := t."{name}"' for name in spec.value_columns)
        connection.execute(
            f"""INSERT INTO record_history
            SELECT ?, {key_text}, ?, ?, CAST(to_json(struct_pack({previous})) AS VARCHAR)
            FROM {table} t JOIN {staged} i ON {_same_key(spec)} WHERE {_differs(spec)}""",
            [spec.name, now, import_id],
        )
        assignments = ", ".join(f'"{name}" = i."{name}"' for name in spec.value_columns)
        connection.execute(
            f"UPDATE {table} AS t SET {assignments} FROM {staged} i "
            f"WHERE {_same_key(spec)} AND ({_differs(spec)})"
        )
    columns = _quoted(list(spec.columns))
    connection.execute(
        f"INSERT INTO {table} ({columns}) SELECT {_quoted(list(spec.columns), 'i.')} "
        f"FROM {staged} i WHERE NOT EXISTS (SELECT 1 FROM {table} t WHERE {_same_key(spec)})"
    )


def _write_log(
    connection: Connection,
    *,
    import_id: int,
    now: datetime,
    info: ImportInfo,
    plan: MergePlan,
    issues: Sequence[ValidationIssue],
    failures: Mapping[str, str],
) -> None:
    """Record the import: its summary, per-table counts, issues and failed domains."""
    connection.execute(
        "INSERT INTO import_log VALUES (?, ?, ?, ?, ?, ?, ?)",
        [
            import_id,
            now,
            info.file_name,
            info.samsung_app_version,
            info.exported_at,
            plan.first_date,
            plan.last_date,
        ],
    )
    rejected = Counter(issue.table for issue in issues if issue.action == REJECTED)
    by_table = {table.table: table for table in plan.tables}
    for name in sorted(set(by_table) | set(rejected)):
        counts = by_table.get(name, TablePlan(name, 0, 0, 0, 0))
        connection.execute(
            "INSERT INTO import_table VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            [
                import_id,
                name,
                counts.new,
                counts.updated,
                counts.unchanged,
                counts.kept,
                counts.superseded,
                rejected[name],
            ],
        )
    if issues:
        connection.executemany(
            "INSERT INTO validation_issue VALUES (?, ?, ?, ?, ?, ?)",
            [[import_id, i.table, i.key, i.rule, i.value, i.action] for i in issues],
        )
    if failures:
        connection.executemany(
            "INSERT INTO import_failure VALUES (?, ?, ?)",
            [[import_id, domain, reason] for domain, reason in sorted(failures.items())],
        )


def apply_merge(
    connection: Connection,
    tables: Mapping[str, pd.DataFrame],
    *,
    info: ImportInfo,
    issues: Sequence[ValidationIssue] = (),
    failures: Mapping[str, str] | None = None,
    now: datetime | None = None,
) -> ImportSummary:
    """Merge ``tables`` into the database and record the import.

    Everything happens in one transaction: if any step fails, the database is
    left exactly as it was.

    Args:
        connection: An open connection.
        tables: Transformed tables by name.
        info: What is known about the export.
        issues: Records the transformation rejected or kept with a notice.
        failures: Reason of failure by domain, for domains that did not transform.
        now: Moment recorded for the import. Defaults to the clock.

    Returns:
        The import identifier and what the merge did.

    Raises:
        MergeError: If a table is unknown, has the wrong columns or a broken key.
    """
    moment = now or datetime.now()
    specs = _stage_all(connection, tables)
    connection.execute("BEGIN")
    try:
        plan = _plan(connection, specs, info.exported_at)
        (latest_id,) = _one(connection, "SELECT coalesce(max(import_id), 0) FROM import_log")
        import_id = int(latest_id) + 1
        for spec in specs:
            _merge_table(
                connection,
                spec,
                import_id=import_id,
                now=moment,
                newest_wins=not plan.is_older_export,
            )
        _write_log(
            connection,
            import_id=import_id,
            now=moment,
            info=info,
            plan=plan,
            issues=issues,
            failures=failures or {},
        )
    except BaseException:
        connection.execute("ROLLBACK")
        raise
    connection.execute("COMMIT")
    return ImportSummary(import_id, plan)
