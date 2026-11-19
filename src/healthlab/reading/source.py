"""One object that gives access to everything inside an export.

The ``transform`` layer needs three things from an export: tables, detail files
and the moment the export was taken. ``ExportSource`` bundles them so a domain
transformer receives a single argument and never builds file paths itself.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd

from healthlab.reading.details import read_detail
from healthlab.reading.errors import TableMissingError
from healthlab.reading.tables import TableFile, list_tables, read_table

STAMP_FORMAT = "%Y%m%d%H%M%S"


@dataclass(frozen=True, slots=True)
class ExportSource:
    """An opened Samsung Health export.

    Attributes:
        root: Folder that directly holds the table files.
        tables: The table files by name.
    """

    root: Path
    tables: dict[str, TableFile]

    @classmethod
    def from_folder(cls, root: Path) -> ExportSource:
        """Open the export stored in ``root``.

        Args:
            root: Folder that directly holds the table files.

        Returns:
            The opened export.
        """
        return cls(root=root, tables=list_tables(root))

    @property
    def exported_at(self) -> datetime:
        """Moment the export was taken, from the timestamp in the file names.

        Returns:
            The latest timestamp among the table files, in the local time of the
            phone that made the export.

        Raises:
            TableMissingError: If the export has no tables at all.
        """
        if not self.tables:
            msg = "the export has no tables"
            raise TableMissingError(msg)
        latest = max(table.stamp for table in self.tables.values())
        return datetime.strptime(latest, STAMP_FORMAT)

    def has(self, name: str) -> bool:
        """Tell whether the export contains the table ``name``."""
        return name in self.tables

    def read(self, name: str) -> pd.DataFrame:
        """Read a table as text.

        Args:
            name: Table name without namespace or timestamp.

        Returns:
            One row per record and one text column per header name.

        Raises:
            TableMissingError: If the export does not contain the table.
        """
        if name not in self.tables:
            msg = f"table not in the export: {name}"
            raise TableMissingError(msg)
        return read_table(self.tables[name])

    def detail(self, name: str, file_name: str) -> Any:
        """Load a detail file referenced from a cell of table ``name``.

        Args:
            name: Table whose cell names the file.
            file_name: File name as written in the cell.

        Returns:
            The parsed JSON content.

        Raises:
            TableMissingError: If the export does not contain the table.
            DetailFileError: If the file is missing or is not valid JSON.
        """
        if name not in self.tables:
            msg = f"table not in the export: {name}"
            raise TableMissingError(msg)
        return read_detail(self.root, self.tables[name], file_name)
