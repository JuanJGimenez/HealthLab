"""Read the detail files of an export: the per-minute and per-interval series.

A table cell can name a file such as ``<id>.binning_data.json``. The file lives in
``jsons/<full table name>/<first character of the id>/``. Most hold a list of
measurements; a few hold a single object.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from misalud.reading.errors import DetailFileError
from misalud.reading.tables import TableFile

DETAILS_FOLDER = "jsons"


def detail_path(export_root: Path, table: TableFile, file_name: str) -> Path:
    """Return where a detail file referenced from ``table`` is stored.

    Args:
        export_root: Folder that directly holds the table files.
        table: Table whose cell names the file.
        file_name: File name as written in the cell.

    Returns:
        The expected location; the file may not exist.

    Raises:
        DetailFileError: If the name is empty or tries to leave its folder.
    """
    if not file_name or Path(file_name).name != file_name:
        msg = f"{table.name}: invalid detail file name {file_name!r}"
        raise DetailFileError(msg)
    return export_root / DETAILS_FOLDER / table.full_name / file_name[0] / file_name


def read_detail(export_root: Path, table: TableFile, file_name: str) -> Any:
    """Load a detail file referenced from a table cell.

    Args:
        export_root: Folder that directly holds the table files.
        table: Table whose cell names the file.
        file_name: File name as written in the cell.

    Returns:
        The parsed JSON content, usually a list of measurements.

    Raises:
        DetailFileError: If the file is missing or is not valid JSON.
    """
    path = detail_path(export_root, table, file_name)
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as error:
        msg = f"{table.name}: detail file not found: {file_name}"
        raise DetailFileError(msg) from error
    except (json.JSONDecodeError, UnicodeDecodeError) as error:
        msg = f"{table.name}: detail file is not valid JSON: {file_name}"
        raise DetailFileError(msg) from error
