"""Everything the window can ask Python to do.

The screens are a web page inside the app window. They never touch files or the
database: they call the methods of ``Api`` and draw what comes back. Every
method takes and returns plain data, and reports a problem as
``{"ok": false, "error": ...}`` instead of raising, so a failure shows up as a
message on screen.
"""

from __future__ import annotations

import shutil
import tempfile
import threading
from collections.abc import Callable
from dataclasses import replace
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Final, Protocol, cast

import misalud
from misalud.config import THRESHOLDS, Paths
from misalud.derived.rebuild import ensure_derived
from misalud.interface.i18n import load_texts
from misalud.interface.settings import LANGUAGES, THEMES, load_settings, save_settings
from misalud.pipeline.importing import PreparedImport, confirm_import, prepare_import
from misalud.queries import database as database_queries
from misalud.queries import days as day_queries
from misalud.queries import nights as night_queries
from misalud.queries.common import NightKind, NightScope, Period, Record
from misalud.storage.backup import list_backups, restore_backup
from misalud.storage.database import Connection, open_database

RANGE_DAYS: Final = {"90": 90, "180": 180, "365": 365}
"""Period choices of the filter bar, in days counted back from the last night."""

NIGHT_KINDS: Final = ("all", "weekend", "weekdays")


class Dialogs(Protocol):
    """What the app window can do on the computer on behalf of the user."""

    def choose_export(self) -> Path | None:
        """Ask for the Samsung Health zip to import; ``None`` if cancelled."""
        ...

    def choose_save(self, suggested_name: str) -> Path | None:
        """Ask where to save a file; ``None`` if cancelled."""
        ...

    def open_folder(self, folder: Path) -> None:
        """Show a folder in the file explorer."""
        ...


def _safely(method: Callable[..., Record]) -> Callable[..., Record]:
    """Turn any failure of an ``Api`` method into an error answer."""

    def wrapper(self: Api, *args: Any) -> Record:
        try:
            return {"ok": True, **method(self, *args)}
        except Exception as error:
            return {"ok": False, "error": f"{type(error).__name__}: {error}"}

    wrapper.__name__ = method.__name__
    wrapper.__doc__ = method.__doc__
    return wrapper


class Api:
    """The methods the window calls.

    Attributes are private (leading underscore) so the window exposes only the
    methods.
    """

    def __init__(self, paths: Paths, dialogs: Dialogs) -> None:
        """Create the bridge.

        Args:
            paths: Where the app keeps its files.
            dialogs: File pickers and the file explorer.
        """
        self._paths = paths
        self._dialogs = dialogs
        self._prepared: PreparedImport | None = None
        self._work_dir: Path | None = None
        self._step = ""
        self._lock = threading.Lock()
        paths.ensure()

    def _open(self) -> Connection:
        """Open the database, with the calculated tables present."""
        connection = open_database(self._paths.database)
        ensure_derived(connection)
        return connection

    def _scope(self, connection: Connection, period: str, nights: str) -> NightScope:
        """Turn the filter bar's choices into the nights to query."""
        if nights not in NIGHT_KINDS:
            msg = f"unknown kind of night: {nights}"
            raise ValueError(msg)
        start = None
        if period != "all":
            last = database_queries.data_period(connection)["last_night"]
            if last is not None:
                start = date.fromisoformat(last) - timedelta(days=RANGE_DAYS[period] - 1)
        return NightScope(start=start, nights=cast(NightKind, nights))

    def _discard_import(self) -> None:
        """Forget a prepared import and remove its scratch folder."""
        self._prepared = None
        if self._work_dir is not None:
            shutil.rmtree(self._work_dir, ignore_errors=True)
            self._work_dir = None

    @_safely
    def bootstrap(self) -> Record:
        """Return what the page needs to start: texts, settings and what data exists."""
        settings = load_settings(self._paths.data_dir)
        with self._open() as connection:
            available = database_queries.data_period(connection)
        return {
            "version": misalud.__version__,
            "language": settings.language,
            "languages": list(LANGUAGES),
            "theme": settings.theme,
            "texts": load_texts(settings.language),
            "available": available,
            "night_metrics": list(night_queries.NIGHT_METRICS),
            "sustained_low_min": THRESHOLDS.sustained_low_min,
            "low_spo2_pct": THRESHOLDS.low_spo2_threshold_pct,
        }

    @_safely
    def set_language(self, language: str) -> Record:
        """Change the interface language and return its texts."""
        texts = load_texts(language)
        settings = load_settings(self._paths.data_dir)
        save_settings(self._paths.data_dir, replace(settings, language=language))
        return {"language": language, "texts": texts}

    @_safely
    def set_theme(self, theme: str) -> Record:
        """Remember the colour theme."""
        if theme not in THEMES:
            msg = f"unknown theme: {theme}"
            raise ValueError(msg)
        settings = load_settings(self._paths.data_dir)
        save_settings(self._paths.data_dir, replace(settings, theme=theme))
        return {"theme": theme}

    @_safely
    def dashboard(self, period: str, nights: str) -> Record:
        """Return the figures of every view for the chosen period and kind of night."""
        with self._open() as connection:
            scope = self._scope(connection, period, nights)
            days = Period(start=scope.start)
            return {
                "overview": night_queries.overview(connection, scope),
                "nights": night_queries.list_nights(connection, scope),
                "oxygen_weekdays": night_queries.sustained_low_by_weekday(connection, scope),
                "sleep_months": night_queries.nights_by_month(
                    connection,
                    ["hours", "asleep_hours", "score", "deep_min", "rem_min", "light_min"],
                    scope,
                ),
                "hrv_trend": night_queries.rolling_median(connection, "hrv_rmssd_ms", scope),
                "pulse_trend": night_queries.rolling_median(connection, "night_hr_avg", scope),
                "hrv_weekdays": night_queries.nights_by_weekday(connection, "hrv_rmssd_ms", scope),
                "pulse_weekdays": night_queries.nights_by_weekday(
                    connection, "night_hr_avg", scope
                ),
                "activity_months": day_queries.days_by_month(
                    connection, ["steps", "exercise_min", "stress_avg"], days
                ),
            }

    @_safely
    def worst_nights(self, period: str, nights: str, order_by: str) -> Record:
        """Return the hardest nights for oxygen, ranked by the chosen measure."""
        with self._open() as connection:
            scope = self._scope(connection, period, nights)
            return {
                "nights": night_queries.worst_oxygen_nights(connection, scope, order_by=order_by)
            }

    @_safely
    def relate(self, period: str, nights: str, x: str, y: str) -> Record:
        """Pair two metrics night by night, with their rank correlation."""
        with self._open() as connection:
            scope = self._scope(connection, period, nights)
            return night_queries.relate(connection, x, y, scope)

    @_safely
    def export_csv(self, period: str, nights: str) -> Record:
        """Save the nights of the current filter as a CSV file the user chooses."""
        target = self._dialogs.choose_save("misalud_noches.csv")
        if target is None:
            return {"saved": False}
        with self._open() as connection:
            text = night_queries.nights_csv(connection, self._scope(connection, period, nights))
        target.write_text(text, encoding="utf-8-sig", newline="")
        return {"saved": True, "file_name": target.name}

    @_safely
    def start_import(self) -> Record:
        """Ask for an export and build the preview of importing it.

        Nothing is stored. The preview stays ready for ``confirm_import`` until
        another import starts or ``cancel_import`` is called.
        """
        chosen = self._dialogs.choose_export()
        if chosen is None:
            return {"chosen": False}
        with self._lock:
            self._discard_import()
            self._work_dir = Path(tempfile.mkdtemp(prefix="misalud_import_"))

            def remember(step: str) -> None:
                self._step = step

            try:
                prepared = prepare_import(chosen, self._paths, self._work_dir, remember)
            except Exception:
                self._discard_import()
                raise
            finally:
                self._step = ""
            self._prepared = prepared
        plan = prepared.plan
        issues = prepared.transformed.issues
        return {
            "chosen": True,
            "file_name": prepared.info.file_name,
            "exported_at": prepared.info.exported_at.isoformat(),
            "samsung_app_version": prepared.info.samsung_app_version,
            "first_date": plan.first_date.isoformat() if plan.first_date else None,
            "last_date": plan.last_date.isoformat() if plan.last_date else None,
            "is_older_export": plan.is_older_export,
            "totals": {
                name: plan.total(name)
                for name in ("new", "updated", "unchanged", "kept", "superseded", "updated_old")
            },
            "tables": [
                {
                    "table": table.table,
                    "new": table.new,
                    "updated": table.updated,
                    "unchanged": table.unchanged,
                    "kept": table.kept,
                    "superseded": table.superseded,
                }
                for table in plan.tables
            ],
            "rejected": sum(1 for issue in issues if issue.action == "rejected"),
            "noticed": sum(1 for issue in issues if issue.action != "rejected"),
            "failed_domains": [
                {"domain": domain, "reason": reason}
                for domain, reason in sorted(prepared.transformed.failures.items())
            ],
            "compatibility": [
                {
                    "table": finding.table,
                    "severity": finding.severity.value,
                    "code": finding.code,
                    "detail": finding.detail,
                }
                for finding in prepared.compatibility.findings
                if finding.severity.value != "info"
            ],
        }

    @_safely
    def import_step(self) -> Record:
        """Return the step a running import is on, for the progress bar."""
        return {"step": self._step}

    @_safely
    def confirm_import(self) -> Record:
        """Merge the prepared import and return what changed."""
        with self._lock:
            if self._prepared is None:
                msg = "there is no prepared import to confirm"
                raise RuntimeError(msg)
            with self._open() as connection:
                before = database_queries.data_period(connection)
            try:
                result = confirm_import(self._prepared, self._paths)
            finally:
                self._discard_import()
        plan = result.summary.plan
        return {
            "import_id": result.summary.import_id,
            "new_records": plan.total("new"),
            "updated_records": plan.total("updated"),
            "new_nights": result.derived.nights - before["nights"],
            "new_days": result.derived.days - before["days"],
            "backup": result.backup.name if result.backup else None,
        }

    @_safely
    def cancel_import(self) -> Record:
        """Drop the prepared import without storing anything."""
        with self._lock:
            self._discard_import()
        return {}

    @_safely
    def database_panel(self) -> Record:
        """Return the state of the database for the "Database" panel."""
        with self._open() as connection:
            history = database_queries.import_history(connection)
            panel = {
                "available": database_queries.data_period(connection),
                "history": history,
                "tables": database_queries.table_sizes(connection),
                "issues": database_queries.issue_summary(connection),
            }
        database = self._paths.database
        return {
            **panel,
            "folder": str(self._paths.data_dir),
            "size_bytes": database.stat().st_size,
            "last_import": history[0]["imported_at"] if history else None,
            "backups": [
                {
                    "name": backup.name,
                    "size_bytes": backup.stat().st_size,
                    "saved_at": datetime.fromtimestamp(backup.stat().st_mtime).isoformat(
                        timespec="seconds"
                    ),
                }
                for backup in reversed(list_backups(self._paths.backups_dir))
            ],
        }

    @_safely
    def open_data_folder(self) -> Record:
        """Show the data folder in the file explorer."""
        self._dialogs.open_folder(self._paths.data_dir)
        return {}

    @_safely
    def restore_backup(self, name: str) -> Record:
        """Put a backup back in place of the database.

        Only a backup listed by ``database_panel`` can be restored: the name is
        looked up in the backups folder, never used as a path.
        """
        matches = [path for path in list_backups(self._paths.backups_dir) if path.name == name]
        if not matches:
            msg = f"backup not found: {name}"
            raise RuntimeError(msg)
        with self._lock:
            restore_backup(matches[0], self._paths.database)
        return {"restored": name}
