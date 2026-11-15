"""Copies of the database taken before each merge (design decisions 7 and 16).

A backup is a plain copy of the database file. Restoring one is copying it back.
"""

from __future__ import annotations

import shutil
from datetime import datetime
from pathlib import Path
from typing import Final

import duckdb

from misalud.config import THRESHOLDS
from misalud.storage.errors import StorageError

BACKUP_PREFIX: Final = "salud_"
BACKUP_SUFFIX: Final = ".duckdb"
STAMP_FORMAT: Final = "%Y%m%d_%H%M%S"


def list_backups(backups_dir: Path) -> list[Path]:
    """Return the backups in a folder, oldest first.

    Args:
        backups_dir: Folder that holds the backups.

    Returns:
        The backup files ordered by the moment in their name.
    """
    if not backups_dir.is_dir():
        return []
    return sorted(backups_dir.glob(f"{BACKUP_PREFIX}*{BACKUP_SUFFIX}"))


def backup_database(
    database: Path, backups_dir: Path, *, now: datetime | None = None
) -> Path | None:
    """Copy the database into the backups folder.

    The database must not be open elsewhere in this program: the function opens
    it briefly to flush pending writes to the file before copying.

    Args:
        database: The database file.
        backups_dir: Folder that receives the copy; created if missing.
        now: Moment written into the backup name. Defaults to the clock.

    Returns:
        The backup file, or ``None`` when there is no database yet to back up.
    """
    if not database.is_file():
        return None
    with duckdb.connect(str(database)) as connection:
        connection.execute("CHECKPOINT")
    backups_dir.mkdir(parents=True, exist_ok=True)
    stamp = (now or datetime.now()).strftime(STAMP_FORMAT)
    target = backups_dir / f"{BACKUP_PREFIX}{stamp}{BACKUP_SUFFIX}"
    shutil.copy2(database, target)
    return target


def prune_backups(backups_dir: Path, keep: int = THRESHOLDS.backups_to_keep) -> list[Path]:
    """Delete the oldest backups, leaving the ``keep`` most recent.

    Args:
        backups_dir: Folder that holds the backups.
        keep: Number of backups to leave.

    Returns:
        The files that were deleted.
    """
    backups = list_backups(backups_dir)
    surplus = backups[: max(len(backups) - keep, 0)]
    for path in surplus:
        path.unlink()
    return surplus


def restore_backup(backup: Path, database: Path) -> None:
    """Put a backup back in place of the database.

    The database must not be open. The current database file is replaced.

    Args:
        backup: A file returned by ``backup_database`` or ``list_backups``.
        database: The database file to replace.

    Raises:
        StorageError: If the backup file does not exist.
    """
    if not backup.is_file():
        msg = f"backup not found: {backup.name}"
        raise StorageError(msg)
    leftover_log = database.with_name(database.name + ".wal")
    leftover_log.unlink(missing_ok=True)
    shutil.copy2(backup, database)
