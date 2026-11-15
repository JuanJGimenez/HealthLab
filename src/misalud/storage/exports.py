"""Keep the original export archives (design decisions 9 and 18).

Every export usually carries the whole history, so the two most recent archives
are enough to redo an import. The exception protects history Samsung may have
trimmed: an older archive that reaches further back than the ones kept is never
deleted.
"""

from __future__ import annotations

import shutil
from datetime import date
from pathlib import Path

from misalud.config import THRESHOLDS
from misalud.storage.database import Connection


def archive_export(archive: Path, exports_dir: Path) -> Path:
    """Copy an imported archive into the exports folder.

    Args:
        archive: The zip file the user imported.
        exports_dir: Folder that keeps the originals; created if missing.

    Returns:
        The stored copy. An archive already stored under the same name is
        replaced, since it is the same export.
    """
    exports_dir.mkdir(parents=True, exist_ok=True)
    target = exports_dir / archive.name
    if archive.resolve() != target.resolve():
        shutil.copy2(archive, target)
    return target


def prune_exports(
    connection: Connection, exports_dir: Path, keep: int = THRESHOLDS.exports_to_keep
) -> list[Path]:
    """Delete stored archives that are no longer needed.

    The ``keep`` archives with the most recent export moment stay. An older one
    is deleted only when the import log shows that some kept archive starts on
    the same day or earlier, so no history is lost. An archive the log does not
    know is left alone.

    Args:
        connection: An open connection, to read the import log.
        exports_dir: Folder that keeps the originals.
        keep: Number of recent archives to leave.

    Returns:
        The files that were deleted.
    """
    rows = connection.execute(
        """SELECT file_name, max(exported_at), min(first_date)
        FROM import_log GROUP BY file_name ORDER BY max(exported_at) DESC"""
    ).fetchall()
    stored = [(name, first) for name, _, first in rows if (exports_dir / name).is_file()]
    recent, older = stored[:keep], stored[keep:]
    starts: list[date] = [first for _, first in recent if first is not None]
    deleted = []
    for name, first in older:
        if first is not None and starts and min(starts) <= first:
            path = exports_dir / name
            path.unlink()
            deleted.append(path)
    return deleted
