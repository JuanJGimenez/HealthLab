"""Open a Samsung Health export, given as a zip archive or as a folder.

Samsung Health produces a folder named ``samsunghealth_<account>_<timestamp>`` that
holds one CSV per table plus the ``jsons`` and ``files`` folders. Users hand the app
either that folder, a parent of it, or the zip they made from it.
"""

from __future__ import annotations

import re
import zipfile
from pathlib import Path
from typing import Final

from healthlab.reading.errors import ExportNotFoundError, UnsafeArchiveError

TABLE_FILE_PATTERN: Final = re.compile(r"^com\.samsung\.(shealth|health)\.(.+)\.(\d{14})\.csv$")
"""File name of a table: namespace, table name and export timestamp."""


def is_export_folder(folder: Path) -> bool:
    """Tell whether ``folder`` directly holds the tables of an export.

    Args:
        folder: Folder to inspect.

    Returns:
        True when the folder contains at least one Samsung table file.
    """
    if not folder.is_dir():
        return False
    return any(TABLE_FILE_PATTERN.match(entry.name) for entry in folder.iterdir())


def locate_export(folder: Path) -> Path:
    """Find the export folder at or below ``folder``.

    The search goes breadth first, so the shallowest match wins, and visits
    sibling folders in name order, so the result does not depend on the disk.

    Args:
        folder: Folder that is, or contains, an export.

    Returns:
        The folder that directly holds the table files.

    Raises:
        ExportNotFoundError: If no folder below ``folder`` holds table files.
    """
    pending = [folder]
    while pending:
        current = pending.pop(0)
        if is_export_folder(current):
            return current
        if current.is_dir():
            pending.extend(sorted(entry for entry in current.iterdir() if entry.is_dir()))
    msg = f"no Samsung Health export found in {folder}"
    raise ExportNotFoundError(msg)


def extract_archive(archive: Path, target: Path) -> None:
    """Extract a zip archive into ``target``, refusing entries that escape it.

    An archive can name an entry ``../../somewhere``; extracting it blindly would
    write outside the target folder. Every entry is checked before anything is
    written, so a rejected archive leaves the target untouched.

    Args:
        archive: Zip file to extract.
        target: Folder to extract into. It is created when missing.

    Raises:
        ExportNotFoundError: If ``archive`` is not a zip file.
        UnsafeArchiveError: If an entry would land outside ``target``.
    """
    if not zipfile.is_zipfile(archive):
        msg = f"not a zip archive: {archive}"
        raise ExportNotFoundError(msg)
    root = target.resolve()
    with zipfile.ZipFile(archive) as bundle:
        for name in bundle.namelist():
            destination = (root / name).resolve()
            if destination != root and root not in destination.parents:
                msg = f"archive entry escapes the target folder: {name}"
                raise UnsafeArchiveError(msg)
        root.mkdir(parents=True, exist_ok=True)
        bundle.extractall(root)


def open_export(source: Path, workdir: Path) -> Path:
    """Return the export folder for a zip archive or a folder chosen by the user.

    A zip archive is extracted into ``workdir``; a folder is used in place and is
    never modified.

    Args:
        source: Zip archive, export folder or a parent of the export folder.
        workdir: Empty scratch folder used only when ``source`` is an archive. The
            caller owns it and removes it when the import ends.

    Returns:
        The folder that directly holds the table files.

    Raises:
        ExportNotFoundError: If ``source`` does not exist or holds no export.
        UnsafeArchiveError: If the archive has an entry that escapes ``workdir``.
    """
    if source.is_dir():
        return locate_export(source)
    if source.is_file():
        extract_archive(source, workdir)
        return locate_export(workdir)
    msg = f"does not exist: {source}"
    raise ExportNotFoundError(msg)
