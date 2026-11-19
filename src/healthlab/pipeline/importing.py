"""Run an import in two steps: prepare a preview, then apply it if confirmed.

``prepare_import`` reads and transforms the export and counts what merging it
would do. It changes no stored record, so the user can look at the preview and
walk away. ``confirm_import`` backs the database up, merges and files the
original archive.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from healthlab.config import Paths
from healthlab.derived.rebuild import DerivedCounts, rebuild_derived
from healthlab.reading.archive import open_export
from healthlab.reading.compatibility import CompatibilityReport, compare_with_contracts
from healthlab.reading.source import ExportSource
from healthlab.storage.backup import backup_database, prune_backups
from healthlab.storage.database import open_database
from healthlab.storage.exports import archive_export, prune_exports
from healthlab.storage.merge import ImportInfo, ImportSummary, MergePlan, apply_merge, plan_merge
from healthlab.transform.export import TransformResult, transform_export


@dataclass(frozen=True, slots=True)
class PreparedImport:
    """An export that was read and compared with the database, not yet merged.

    Attributes:
        info: Name, moment and Samsung Health version of the export.
        archive: The zip file to keep after merging; ``None`` when the user
            chose a folder.
        compatibility: Differences between the export and the contracts.
        transformed: Clean tables, validation issues and failed domains.
        plan: What merging would do, table by table.
    """

    info: ImportInfo
    archive: Path | None
    compatibility: CompatibilityReport
    transformed: TransformResult
    plan: MergePlan


@dataclass(frozen=True, slots=True)
class ImportResult:
    """Outcome of a confirmed import.

    Attributes:
        summary: Import identifier and what the merge did.
        backup: Copy of the database taken before merging; ``None`` on the
            first import, when there was nothing to protect.
        derived: Number of nights and days after recomputing the calculated tables.
    """

    summary: ImportSummary
    backup: Path | None
    derived: DerivedCounts


Progress = Callable[[str], None]
"""Receives the name of each step as it starts: ``opening``, ``checking``,
``transforming`` and ``comparing``."""


def _silent(_: str) -> None:
    """Ignore progress, for callers that do not show it."""


def prepare_import(
    chosen: Path, paths: Paths, work_dir: Path, progress: Progress = _silent
) -> PreparedImport:
    """Read an export and build the preview of merging it.

    Args:
        chosen: Zip archive or folder picked by the user.
        paths: Where the app keeps its files.
        work_dir: Empty scratch folder for extracting an archive. The caller
            removes it when the import ends.
        progress: Called with the name of each step as it starts.

    Returns:
        Everything the preview shows and everything ``confirm_import`` needs.

    Raises:
        ReadingError: If ``chosen`` is not a readable Samsung Health export.
        SchemaVersionError: If the database was made by a newer HealthLab.
    """
    progress("opening")
    root = open_export(chosen, work_dir)
    progress("checking")
    compatibility = compare_with_contracts(root)
    source = ExportSource.from_folder(root)
    progress("transforming")
    transformed = transform_export(source, blocked_tables=compatibility.blocked_tables())
    info = ImportInfo(
        file_name=chosen.name,
        exported_at=source.exported_at,
        samsung_app_version=", ".join(compatibility.app_versions) or None,
    )
    progress("comparing")
    paths.ensure()
    with open_database(paths.database) as connection:
        plan = plan_merge(connection, transformed.tables, exported_at=info.exported_at)
    return PreparedImport(
        info=info,
        archive=chosen if chosen.is_file() else None,
        compatibility=compatibility,
        transformed=transformed,
        plan=plan,
    )


def _has_imports(database: Path) -> bool:
    """Tell whether the database already holds at least one import."""
    with open_database(database) as connection:
        rows = connection.execute("SELECT count(*) FROM import_log").fetchall()
    return bool(rows[0][0])


def confirm_import(
    prepared: PreparedImport, paths: Paths, *, now: datetime | None = None
) -> ImportResult:
    """Merge a prepared import into the database.

    Order of work: back the database up, merge in one transaction, recompute
    the calculated tables, file the original archive, then drop the backups and
    archives no longer needed. If the merge fails, the database is unchanged and
    the backup stays.

    Args:
        prepared: Result of ``prepare_import``.
        paths: Where the app keeps its files.
        now: Moment recorded for the import and the backup. Defaults to the clock.

    Returns:
        What the merge did and where the backup is.
    """
    moment = now or datetime.now()
    paths.ensure()
    backup = (
        backup_database(paths.database, paths.backups_dir, now=moment)
        if _has_imports(paths.database)
        else None
    )
    with open_database(paths.database, now=moment) as connection:
        summary = apply_merge(
            connection,
            prepared.transformed.tables,
            info=prepared.info,
            issues=prepared.transformed.issues,
            failures=prepared.transformed.failures,
            now=moment,
        )
        derived = rebuild_derived(connection)
        if prepared.archive is not None:
            archive_export(prepared.archive, paths.exports_dir)
        prune_exports(connection, paths.exports_dir)
    prune_backups(paths.backups_dir)
    return ImportResult(summary=summary, backup=backup, derived=derived)
