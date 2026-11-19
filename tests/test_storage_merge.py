"""Tests for the merge: the four rules, the preview and the import log."""

from __future__ import annotations

import json
from collections.abc import Iterator
from datetime import date, datetime
from typing import Any

import pandas as pd
import pytest

from healthlab.reading.source import ExportSource
from healthlab.storage import merge
from healthlab.storage.database import Connection, open_database
from healthlab.storage.errors import MergeError
from healthlab.storage.merge import ImportInfo, TablePlan, apply_merge, plan_merge
from healthlab.transform.common import KEPT, ValidationIssue
from healthlab.transform.export import transform_export
from tests.support.synthetic_export import SyntheticExport, build_export

FIRST = ImportInfo("first.zip", datetime(2026, 3, 1, 20, 0), "7013005")
SECOND = ImportInfo("second.zip", datetime(2026, 3, 15, 20, 0), "7013005")
NOW = datetime(2026, 4, 2, 9, 0)


@pytest.fixture
def connection() -> Iterator[Connection]:
    """An empty database in memory."""
    with open_database(None) as opened:
        yield opened


def steps(*rows: tuple[str, str, float | None]) -> pd.DataFrame:
    """Build a ``steps_day`` table from ``(id, day, steps)`` rows."""
    frame = pd.DataFrame(rows, columns=["samsung_id", "day", "steps"])
    frame["samsung_id"] = frame["samsung_id"].astype("string")
    frame["day"] = pd.to_datetime(frame["day"])
    frame["steps"] = frame["steps"].astype("float64")
    frame["distance_m"] = frame["steps"] * 0.75
    frame["calorie_kcal"] = float("nan")
    return frame


def intervals(day: str, counts: list[float]) -> pd.DataFrame:
    """Build a ``steps_interval`` table for one day."""
    start = pd.Timestamp(day)
    return pd.DataFrame(
        {
            "day": start,
            "interval": range(len(counts)),
            "start_at": [start + pd.Timedelta(minutes=10 * i) for i in range(len(counts))],
            "steps": counts,
            "distance_m": [0.0] * len(counts),
            "calorie_kcal": [0.0] * len(counts),
        }
    )


def stored(connection: Connection, sql: str) -> list[tuple[Any, ...]]:
    """Run a query and return its rows."""
    return connection.execute(sql).fetchall()


def step_rows(connection: Connection) -> list[tuple[Any, ...]]:
    """Return the stored daily steps as ``(id, steps)`` in day order."""
    return stored(connection, "SELECT samsung_id, steps FROM steps_day ORDER BY day")


BASE = steps(("a", "2026-02-27", 9000), ("b", "2026-02-28", 8000), ("c", "2026-03-01", 2000))


def test_records_the_database_does_not_have_are_added(connection: Connection) -> None:
    summary = apply_merge(connection, {"steps_day": BASE}, info=FIRST, now=NOW)
    assert summary.import_id == 1
    assert summary.plan.tables == (TablePlan("steps_day", new=3, updated=0, unchanged=0, kept=0),)
    assert step_rows(connection) == [("a", 9000), ("b", 8000), ("c", 2000)]
    assert stored(connection, "SELECT calorie_kcal FROM steps_day WHERE samsung_id = 'a'") == [
        (None,)
    ]


def test_identical_records_are_left_alone(connection: Connection) -> None:
    apply_merge(connection, {"steps_day": BASE}, info=FIRST)
    summary = apply_merge(connection, {"steps_day": BASE.copy()}, info=SECOND)
    assert summary.plan.tables == (TablePlan("steps_day", new=0, updated=0, unchanged=3, kept=0),)
    assert not summary.plan.changes_anything
    assert stored(connection, "SELECT count(*) FROM record_history") == [(0,)]


def test_a_changed_record_is_replaced_and_its_previous_values_are_saved(
    connection: Connection,
) -> None:
    apply_merge(connection, {"steps_day": BASE}, info=FIRST)
    newer = steps(("c", "2026-03-01", 11000), ("d", "2026-03-02", 7000))
    summary = apply_merge(connection, {"steps_day": newer}, info=SECOND, now=NOW)
    assert summary.plan.tables == (TablePlan("steps_day", new=1, updated=1, unchanged=0, kept=2),)
    assert step_rows(connection) == [("a", 9000), ("b", 8000), ("c", 11000), ("d", 7000)]
    history = stored(connection, "SELECT * FROM record_history")
    assert len(history) == 1
    table, key, replaced_at, import_id, previous = history[0]
    assert (table, key, replaced_at, import_id) == ("steps_day", "2026-03-01 00:00:00", NOW, 2)
    assert json.loads(previous) == {
        "samsung_id": "c",
        "steps": 2000.0,
        "distance_m": 1500.0,
        "calorie_kcal": None,
    }


def test_records_missing_from_the_export_are_kept(connection: Connection) -> None:
    apply_merge(connection, {"steps_day": BASE}, info=FIRST)
    summary = apply_merge(connection, {"steps_day": steps(("c", "2026-03-01", 2000))}, info=SECOND)
    assert summary.plan.tables == (TablePlan("steps_day", new=0, updated=0, unchanged=1, kept=2),)
    assert len(step_rows(connection)) == 3


def test_a_value_that_appears_or_disappears_counts_as_a_change(connection: Connection) -> None:
    apply_merge(connection, {"steps_day": BASE}, info=FIRST)
    newer = BASE.copy()
    newer.loc[0, "calorie_kcal"] = 300.0
    newer.loc[1, "steps"] = float("nan")
    summary = apply_merge(connection, {"steps_day": newer}, info=SECOND)
    assert summary.plan.total("updated") == 2
    assert step_rows(connection)[1] == ("b", None)


def test_an_older_export_adds_what_is_missing_but_never_overwrites(connection: Connection) -> None:
    apply_merge(connection, {"steps_day": BASE}, info=SECOND)
    older = steps(("c", "2026-03-01", 500), ("z", "2026-02-20", 4000))
    plan = plan_merge(connection, {"steps_day": older}, exported_at=FIRST.exported_at)
    assert plan.is_older_export
    assert plan.tables == (
        TablePlan("steps_day", new=1, updated=0, unchanged=0, kept=2, superseded=1),
    )
    apply_merge(connection, {"steps_day": older}, info=FIRST)
    assert step_rows(connection) == [("z", 4000), ("a", 9000), ("b", 8000), ("c", 2000)]
    assert stored(connection, "SELECT count(*) FROM record_history") == [(0,)]
    assert stored(connection, "SELECT superseded_count FROM import_table WHERE import_id = 2") == [
        (1,)
    ]


def test_changes_to_old_records_are_counted_apart(connection: Connection) -> None:
    apply_merge(connection, {"steps_day": BASE}, info=FIRST)
    newer = steps(("a", "2026-02-27", 1), ("c", "2026-03-01", 2))
    late = ImportInfo("late.zip", datetime(2026, 3, 30, 20, 0))
    plan = plan_merge(connection, {"steps_day": newer}, exported_at=late.exported_at)
    # 27 February is more than 30 days before 30 March; 1 March is not.
    assert (plan.tables[0].updated, plan.tables[0].updated_old) == (2, 1)


def test_the_preview_writes_nothing(connection: Connection) -> None:
    apply_merge(connection, {"steps_day": BASE}, info=FIRST)
    newer = steps(("c", "2026-03-01", 11000), ("d", "2026-03-02", 7000))
    plan = plan_merge(connection, {"steps_day": newer}, exported_at=SECOND.exported_at)
    assert (plan.total("new"), plan.total("updated"), plan.changes_anything) == (1, 1, True)
    assert (plan.first_date, plan.last_date) == (date(2026, 3, 1), date(2026, 3, 2))
    assert step_rows(connection) == [("a", 9000), ("b", 8000), ("c", 2000)]
    assert stored(connection, "SELECT count(*) FROM import_log") == [(1,)]
    assert stored(connection, "SELECT count(*) FROM record_history") == [(0,)]


def test_an_import_without_tables_is_recorded_with_no_period(connection: Connection) -> None:
    summary = apply_merge(connection, {}, info=FIRST, failures={"sleep": "table gone"}, now=NOW)
    assert summary.plan.tables == ()
    assert (summary.plan.first_date, summary.plan.last_date) == (None, None)
    assert stored(connection, "SELECT * FROM import_log") == [
        (1, NOW, "first.zip", "7013005", FIRST.exported_at, None, None)
    ]
    assert stored(connection, "SELECT * FROM import_failure") == [(1, "sleep", "table gone")]


def test_a_composite_key_identifies_each_interval(connection: Connection) -> None:
    apply_merge(connection, {"steps_interval": intervals("2026-03-01", [10, 20, 0])}, info=FIRST)
    summary = apply_merge(
        connection, {"steps_interval": intervals("2026-03-01", [10, 25, 30])}, info=SECOND
    )
    assert summary.plan.tables == (
        TablePlan("steps_interval", new=0, updated=2, unchanged=1, kept=0),
    )
    keys = stored(connection, "SELECT key FROM record_history ORDER BY key")
    assert keys == [("2026-03-01 00:00:00|1",), ("2026-03-01 00:00:00|2",)]
    assert stored(connection, "SELECT sum(steps) FROM steps_interval") == [(65,)]


def test_the_import_log_records_counts_issues_and_failed_domains(connection: Connection) -> None:
    issues = [
        ValidationIssue("steps_day", "x", "date_before_2020", "1970-01-01"),
        ValidationIssue("snoring_event", "y", "date_before_2020", "1970-01-01"),
        ValidationIssue("snoring_event", "z", "date_before_2020", "1970-01-01"),
        ValidationIssue("steps_interval", "w", "detail_file_empty", "w.json", KEPT),
    ]
    apply_merge(
        connection,
        {"steps_day": BASE},
        info=FIRST,
        issues=issues,
        failures={"hrv": "table not in the export: hrv"},
        now=NOW,
    )
    assert stored(connection, "SELECT * FROM import_log") == [
        (1, NOW, "first.zip", "7013005", FIRST.exported_at, date(2026, 2, 27), date(2026, 3, 1))
    ]
    assert stored(connection, "SELECT * FROM import_table ORDER BY table_name") == [
        (1, "snoring_event", 0, 0, 0, 0, 0, 2),
        (1, "steps_day", 3, 0, 0, 0, 0, 1),
    ]
    assert stored(
        connection, "SELECT count(*), count(*) FILTER (action = 'kept') FROM validation_issue"
    ) == [(4, 1)]
    assert stored(connection, "SELECT * FROM import_failure") == [
        (1, "hrv", "table not in the export: hrv")
    ]
    second = apply_merge(connection, {"steps_day": BASE}, info=SECOND)
    assert second.import_id == 2


def test_incoming_data_that_does_not_fit_the_schema_is_refused(connection: Connection) -> None:
    with pytest.raises(MergeError, match="tables not in the schema: mood"):
        plan_merge(connection, {"mood": BASE}, exported_at=FIRST.exported_at)
    with pytest.raises(MergeError, match=r"missing \['steps'\], unknown \['paces'\]"):
        apply_merge(connection, {"steps_day": BASE.rename(columns={"steps": "paces"})}, info=FIRST)
    no_key = BASE.copy()
    no_key.loc[0, "day"] = pd.NaT
    with pytest.raises(MergeError, match="1 incoming rows have no key"):
        apply_merge(connection, {"steps_day": no_key}, info=FIRST)
    repeated = steps(("a", "2026-02-27", 1), ("b", "2026-02-27", 2), ("c", "2026-02-27", 3))
    with pytest.raises(MergeError, match="the key repeats in 2 incoming rows"):
        apply_merge(connection, {"steps_day": repeated}, info=FIRST)
    assert stored(connection, "SELECT count(*) FROM steps_day") == [(0,)]
    assert stored(connection, "SELECT count(*) FROM import_log") == [(0,)]


def test_a_failure_halfway_leaves_the_database_untouched(
    connection: Connection, monkeypatch: pytest.MonkeyPatch
) -> None:
    apply_merge(connection, {"steps_day": BASE}, info=FIRST)

    def broken(*_: object, **__: object) -> None:
        raise RuntimeError("disk full")

    monkeypatch.setattr(merge, "_write_log", broken)
    newer = steps(("c", "2026-03-01", 11000), ("d", "2026-03-02", 7000))
    with pytest.raises(RuntimeError, match="disk full"):
        apply_merge(connection, {"steps_day": newer}, info=SECOND)
    assert step_rows(connection) == [("a", 9000), ("b", 8000), ("c", 2000)]
    assert stored(connection, "SELECT count(*) FROM record_history") == [(0,)]
    assert stored(connection, "SELECT count(*) FROM import_log") == [(1,)]


def test_two_exports_taken_on_different_dates_merge_without_losing_anything(
    tmp_path_factory: pytest.TempPathFactory, connection: Connection
) -> None:
    folder = tmp_path_factory.mktemp("exports")
    results = {}
    for name, days in (("older", 4), ("newer", 6)):
        export: SyntheticExport = build_export(folder / name, n_days=days)
        source = ExportSource.from_folder(export.root)
        results[name] = (transform_export(source), ImportInfo(name, source.exported_at))

    older, older_info = results["older"]
    first = apply_merge(connection, older.tables, info=older_info, issues=older.issues)
    assert first.plan.total("new") == sum(len(frame) for frame in older.tables.values())

    newer, newer_info = results["newer"]
    second = apply_merge(connection, newer.tables, info=newer_info, issues=newer.issues)
    by_table = {plan.table: plan for plan in second.plan.tables}
    # The day the older export was taken arrived partial and is now complete.
    assert by_table["steps_day"] == TablePlan("steps_day", new=2, updated=1, unchanged=3, kept=0)
    assert by_table["steps_interval"].updated > 0
    assert by_table["sleep_session"].updated == 0
    assert by_table["sleep_session"].new == 2
    assert second.plan.total("kept") == 0
    for name, frame in newer.tables.items():
        assert stored(connection, f'SELECT count(*) FROM "{name}"') == [(len(frame),)], name
    history = dict(stored(connection, "SELECT table_name, count(*) FROM record_history GROUP BY 1"))
    assert history == {
        "steps_day": 1,
        "steps_interval": by_table["steps_interval"].updated,
    }

    again = plan_merge(connection, newer.tables, exported_at=newer_info.exported_at)
    assert not again.changes_anything
    back = plan_merge(connection, older.tables, exported_at=older_info.exported_at)
    assert back.is_older_export
    assert (back.total("new"), back.total("updated")) == (0, 0)
    assert back.total("superseded") == 1 + by_table["steps_interval"].updated
