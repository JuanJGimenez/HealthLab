"""An in-memory export for the transform tests.

The transformers depend on the ``Source`` protocol, not on files. This fake lets a
test state the exact rows a table holds and assert on what comes out.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

import pandas as pd

from healthlab.reading.errors import DetailFileError, TableMissingError

EXPORTED_AT = datetime(2026, 1, 10, 12, 0, 0)

Row = dict[str, str | None]


def raw(rows: Sequence[Mapping[str, str | None]]) -> pd.DataFrame:
    """Build a raw table the way the reading layer returns it: every cell as text."""
    return pd.DataFrame([dict(row) for row in rows], dtype="string")


def timed(
    ident: str | None,
    start: str = "2026-01-02 02:30:00.000",
    end: str | None = "2026-01-02 09:30:00.000",
    offset: str | None = "UTC-0300",
    **cells: str | None,
) -> Row:
    """Build a row of a time-based table with Samsung's common columns."""
    return {
        "datauuid": ident,
        "start_time": start,
        "end_time": end,
        "time_offset": offset,
        **cells,
    }


def epoch_ms(moment: str) -> int:
    """Return a UTC moment as milliseconds since 1970, the way detail files store it."""
    return int(pd.Timestamp(moment).value // 1_000_000)


@dataclass
class FakeSource:
    """An export held in memory.

    Attributes:
        tables: Raw tables by Samsung name.
        details: Detail file contents by ``(table, file name)``.
        exported_at: Moment the export was taken.
        reads: Names of the tables read so far, in order.
    """

    tables: dict[str, pd.DataFrame] = field(default_factory=dict)
    details: dict[tuple[str, str], Any] = field(default_factory=dict)
    exported_at: datetime = EXPORTED_AT
    reads: list[str] = field(default_factory=list)

    def has(self, name: str) -> bool:
        """Tell whether the export contains the table ``name``."""
        return name in self.tables

    def read(self, name: str) -> pd.DataFrame:
        """Return a table, or fail the way the real source does."""
        if name not in self.tables:
            msg = f"table not in the export: {name}"
            raise TableMissingError(msg)
        self.reads.append(name)
        return self.tables[name]

    def detail(self, name: str, file_name: str) -> Any:
        """Return a detail file, or fail the way the real source does."""
        if (name, file_name) not in self.details:
            msg = f"detail file not found: {file_name}"
            raise DetailFileError(msg)
        return self.details[(name, file_name)]
