"""Tests for transforming a whole export."""

from __future__ import annotations

import pandas as pd

from healthlab.reading.contracts import load_contracts
from healthlab.reading.errors import TableMissingError
from healthlab.reading.source import ExportSource
from healthlab.transform.common import DomainResult, Source, TransformError, ValidationIssue
from healthlab.transform.export import DOMAIN_SOURCES, DOMAINS, transform_export
from tests.support import synthetic_export as synth
from tests.support.fake_source import FakeSource
from tests.support.synthetic_export import SyntheticExport

SYNTHETIC_DOMAINS = ("sleep", "oxygen", "snoring", "heart_rate", "steps")


def test_a_failing_domain_is_recorded_and_the_others_go_through() -> None:
    def good(_: Source) -> DomainResult:
        issue = ValidationIssue("a", "k", "rule", "v")
        return DomainResult(tables={"a": pd.DataFrame({"x": [1]})}, issues=[issue])

    def no_table(_: Source) -> DomainResult:
        raise TableMissingError("table not in the export: hrv")

    def no_column(_: Source) -> DomainResult:
        raise TransformError("stress: missing required columns: score")

    result = transform_export(
        FakeSource(), {"good": good, "no_table": no_table, "no_column": no_column}
    )
    assert list(result.tables) == ["a"]
    assert [issue.rule for issue in result.issues] == ["rule"]
    assert result.failures == {
        "no_table": "table not in the export: hrv",
        "no_column": "stress: missing required columns: score",
    }


def test_an_export_without_tables_fails_every_domain_without_raising() -> None:
    result = transform_export(FakeSource())
    assert result.tables == {}
    assert set(result.failures) == set(DOMAINS)


def test_the_synthetic_export_goes_through_its_domains(export: SyntheticExport) -> None:
    result = transform_export(ExportSource.from_folder(export.root))
    assert set(result.failures) == set(DOMAINS) - set(SYNTHETIC_DOMAINS)

    sessions = result.tables["sleep_session"]
    assert sorted(sessions["duration_min"]) == [synth.NAP_MINUTES, *[synth.NIGHT_MINUTES] * 3]
    assert int(sessions["is_night"].sum()) == 3
    nights = sessions[sessions["is_night"]]
    assert set(nights["start_at"].dt.strftime("%H:%M")) == {"23:30"}
    assert sorted(nights["utc_offset_min"].unique()) == [-240, -180]
    assert nights["night_date"].dt.strftime("%Y-%m-%d").tolist() == [
        "2026-01-01",
        "2026-01-02",
        "2026-01-03",
    ]
    stage_minutes = result.tables["sleep_stage"].groupby("session_id")["duration_min"].sum()
    assert stage_minutes.to_dict() == sessions.set_index("samsung_id")["duration_min"].to_dict()

    oxygen = result.tables["spo2_night"]
    assert len(oxygen) == 3
    intervals = result.tables["spo2_interval"]
    assert len(intervals) == 3 * synth.NIGHT_MINUTES // 10
    low = oxygen[oxygen["low_seconds"] > 0]
    assert len(low) == 1
    below = intervals[(intervals["night_samsung_id"] == low["samsung_id"].iloc[0])]
    assert int((below["spo2_min"] < 90).sum()) * 600 == low["low_seconds"].iloc[0]

    assert len(result.tables["heart_rate_minute"]) == 3 * 2 * 60
    assert result.tables["heart_rate_minute"]["start_utc"].is_unique

    days = result.tables["steps_day"]
    assert len(days) == export.n_days
    assert days["steps"].iloc[-1] == synth.PARTIAL_DAY_STEPS
    per_day = result.tables["steps_interval"].groupby("day")["steps"].sum()
    assert per_day.tolist() == days["steps"].tolist()

    assert [(i.table, i.rule) for i in result.issues] == [("snoring_event", "date_before_2020")]
    assert not result.tables["snoring_event"]["start_at"].dt.year.eq(1970).any()


def test_every_domain_names_the_used_tables_it_reads() -> None:
    contracts = load_contracts()
    assert set(DOMAIN_SOURCES) == set(DOMAINS)
    for domain, tables in DOMAIN_SOURCES.items():
        for table in tables:
            assert contracts[table].is_used, f"{domain}: {table}"


def test_a_domain_that_reads_a_blocked_table_is_not_run(export: SyntheticExport) -> None:
    source = ExportSource.from_folder(export.root)
    result = transform_export(source, blocked_tables=frozenset({"sleep_stage", "badge"}))
    assert result.failures["sleep"] == "incompatible tables: sleep_stage"
    assert "sleep_session" not in result.tables
    assert "spo2_night" in result.tables
