"""Tests for the description of the database tables."""

from __future__ import annotations

from misalud.reading.source import ExportSource
from misalud.storage.schema import DETAIL_TABLES, MOMENT
from misalud.transform.export import transform_export
from tests.support.synthetic_export import SyntheticExport


def test_every_table_has_a_key_and_a_time_column_among_its_columns() -> None:
    assert len(DETAIL_TABLES) == 20
    for name, spec in DETAIL_TABLES.items():
        assert spec.name == name
        assert spec.key, name
        assert set(spec.key) <= set(spec.columns), name
        assert spec.columns[spec.time_column] == MOMENT, name
        assert spec.value_columns, name
        assert not set(spec.value_columns) & set(spec.key), name


def test_the_create_statement_lists_columns_and_the_key() -> None:
    statement = DETAIL_TABLES["respiratory_rate_minute"].create_statement()
    assert statement == (
        'CREATE TABLE "respiratory_rate_minute" ("night_samsung_id" VARCHAR, '
        '"start_utc" TIMESTAMP, "start_at" TIMESTAMP, "rate" DOUBLE, '
        'PRIMARY KEY ("night_samsung_id", "start_utc"))'
    )


def test_the_schema_matches_what_the_transformation_produces(export: SyntheticExport) -> None:
    result = transform_export(ExportSource.from_folder(export.root))
    assert result.tables
    for name, frame in result.tables.items():
        assert list(frame.columns) == list(DETAIL_TABLES[name].columns), name
