"""List and read the CSV tables of a Samsung Health export.

File layout, as observed in real exports:

* The first line is metadata: ``<full table name>,<app version>,<schema version>``.
* The second line is the header. Some names are bare (``sleep_score``) and some
  carry a prefix (``com.samsung.health.sleep.start_time``).
* Every data row ends with a trailing comma, so rows have one more field than
  the header.

Tables are read as text. Converting to numbers and dates is the job of the
``transform`` layer, which knows the unit and meaning of each column.
"""

from __future__ import annotations

import csv
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

import pandas as pd

from misalud.reading.archive import TABLE_FILE_PATTERN
from misalud.reading.errors import TableFormatError

ENCODING = "utf-8-sig"
"""Samsung writes a byte-order mark; this codec drops it."""


@dataclass(frozen=True, slots=True)
class TableFile:
    """One table file of an export.

    Attributes:
        name: Table name without namespace or timestamp, such as ``sleep_stage``.
        namespace: ``shealth`` or ``health``.
        path: Location of the CSV file.
        stamp: Export timestamp taken from the file name.
        app_version: Samsung Health version written on the metadata line.
        schema_version: Table schema version written on the metadata line.
    """

    name: str
    namespace: str
    path: Path
    stamp: str
    app_version: str
    schema_version: int

    @property
    def full_name(self) -> str:
        """Table name with its namespace, as used for the ``jsons`` subfolder."""
        return f"com.samsung.{self.namespace}.{self.name}"


def short_name(column: str) -> str:
    """Return a column name without its ``com.samsung...`` prefix.

    Args:
        column: Column name as written in the header.

    Returns:
        The part after the last dot.
    """
    return column.rsplit(".", 1)[-1]


def _read_metadata(path: Path) -> tuple[str, int]:
    """Read the app version and schema version from the first line of a table.

    Args:
        path: Location of the CSV file.

    Returns:
        The app version and the schema version.

    Raises:
        TableFormatError: If the first line is not a metadata line.
    """
    with path.open(encoding=ENCODING, newline="") as handle:
        fields = handle.readline().strip().split(",")
    if len(fields) != 3 or not fields[2].isdigit():
        msg = f"{path.name}: first line is not '<table>,<app version>,<schema version>'"
        raise TableFormatError(msg)
    return fields[1], int(fields[2])


def list_tables(export_root: Path) -> dict[str, TableFile]:
    """Find every table file in an export folder.

    Args:
        export_root: Folder that directly holds the table files.

    Returns:
        The tables by name, in name order.

    Raises:
        TableFormatError: If a table file lacks its metadata line, or if two
            files claim the same table name.
    """
    found: dict[str, TableFile] = {}
    for path in sorted(export_root.iterdir()):
        match = TABLE_FILE_PATTERN.match(path.name)
        if not match:
            continue
        namespace, name, stamp = match.groups()
        if name in found:
            msg = f"two files for table {name}: {found[name].path.name} and {path.name}"
            raise TableFormatError(msg)
        app_version, schema_version = _read_metadata(path)
        found[name] = TableFile(name, namespace, path, stamp, app_version, schema_version)
    return dict(sorted(found.items()))


def read_header(table: TableFile) -> list[str]:
    """Return the column names of a table without prefixes, in file order.

    Args:
        table: The table to inspect.

    Returns:
        The short column names.

    Raises:
        TableFormatError: If the file has no header line, or if two columns share
            the same short name.
    """
    with table.path.open(encoding=ENCODING, newline="") as handle:
        handle.readline()
        header = next(csv.reader(handle), None)
    if not header:
        msg = f"{table.path.name}: no header line"
        raise TableFormatError(msg)
    names = [short_name(column) for column in header]
    repeated = sorted(name for name, count in Counter(names).items() if count > 1)
    if repeated:
        msg = f"{table.path.name}: columns share a short name: {', '.join(repeated)}"
        raise TableFormatError(msg)
    return names


def read_table(table: TableFile) -> pd.DataFrame:
    """Read a table as text, with prefixes removed from the column names.

    Empty cells become missing values. The extra field produced by the trailing
    comma of each row is dropped.

    Args:
        table: The table to read.

    Returns:
        One row per record and one text column per header name.

    Raises:
        TableFormatError: If the header is missing or ambiguous, or if a row has
            more fields than the header allows.
    """
    names = read_header(table)
    try:
        frame = pd.read_csv(
            table.path,
            skiprows=2,
            header=None,
            names=[*names, "_trailing"],
            dtype="string",
            encoding=ENCODING,
            keep_default_na=False,
            na_values=[""],
            index_col=False,
        )
    except pd.errors.ParserError as error:
        msg = f"{table.path.name}: {error}"
        raise TableFormatError(msg) from error
    if frame["_trailing"].notna().any():
        msg = f"{table.path.name}: rows have more fields than the header"
        raise TableFormatError(msg)
    return frame.drop(columns="_trailing")
