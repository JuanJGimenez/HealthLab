"""Contracts: what the importer expects from each Samsung Health file.

A contract records, for one Samsung table, its schema version, key, time column
and columns as seen in the reference export. Comparing a new export against the
contracts is how a change made by Samsung becomes visible before any data is
written (design decision 10).

The contracts live in ``contracts.json``, generated in stage 0 from a real export.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from functools import cache
from importlib import resources
from typing import Any


@dataclass(frozen=True, slots=True)
class ColumnContract:
    """One column of a Samsung table.

    Attributes:
        name: Column name without the ``com.samsung...`` prefix.
        dtype: Data type observed in the reference export.
        filled_pct: Share of rows with a value in the reference export, 0 to 100.
    """

    name: str
    dtype: str
    filled_pct: float


@dataclass(frozen=True, slots=True)
class TableContract:
    """What the importer expects from one Samsung table.

    Attributes:
        name: Table name without prefix or timestamp, such as ``sleep_stage``.
        source_file: File name pattern inside the export.
        schema_version: Version Samsung writes on the first line of the file.
        key: Column that identifies a record, or ``None`` when the table has none.
        time_column: Column that dates a record, or ``None``.
        rolling_window_days: Days of history each export carries when the table
            keeps only recent data; ``None`` when it carries the full history.
        detail_file_columns: Columns that point to a JSON or PDF detail file.
        feeds: MiSalud tables built from this table; empty when it is not used.
        columns: The columns, by name.
    """

    name: str
    source_file: str
    schema_version: int
    key: str | None
    time_column: str | None
    rolling_window_days: int | None
    detail_file_columns: tuple[str, ...]
    feeds: tuple[str, ...]
    columns: dict[str, ColumnContract]

    @property
    def is_used(self) -> bool:
        """Tell whether any MiSalud table is built from this one."""
        return bool(self.feeds)


def _table_from_json(name: str, raw: dict[str, Any]) -> TableContract:
    """Build a ``TableContract`` from its JSON representation.

    Args:
        name: Table name.
        raw: The table entry as stored in ``contracts.json``.

    Returns:
        The typed contract.
    """
    columns = {
        column: ColumnContract(name=column, dtype=spec["dtype"], filled_pct=spec["filled_pct"])
        for column, spec in raw["columns"].items()
    }
    return TableContract(
        name=name,
        source_file=raw["source_file"],
        schema_version=raw["schema_version"],
        key=raw["key"],
        time_column=raw["time_column"],
        rolling_window_days=raw["rolling_window_days"],
        detail_file_columns=tuple(raw["detail_file_columns"]),
        feeds=tuple(raw["feeds"]),
        columns=columns,
    )


@cache
def load_contracts() -> dict[str, TableContract]:
    """Load every table contract shipped with the package.

    The file is read once and the result is cached, so callers must treat the
    returned mapping as read-only.

    Returns:
        The contracts by table name.
    """
    text = resources.files("misalud.reading").joinpath("contracts.json").read_text("utf-8")
    document = json.loads(text)
    return {name: _table_from_json(name, raw) for name, raw in document["tables"].items()}
