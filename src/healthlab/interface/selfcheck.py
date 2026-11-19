"""Check that an installed copy of the app has everything it needs to run.

A packaged app can lose a file on the way: a page asset, a language file, a
library. The self-check walks through each piece without opening the window, so
the packaging step can prove the folder works before anyone uses it, and a
user with a problem can produce a short report.

Run it with ``HealthLab.exe --check``; the report is written to the logs folder.
With an export after the flag, ``HealthLab.exe --check export.zip``, it also runs
a whole import of that export into a temporary folder, which never touches the
data of the user.
"""

from __future__ import annotations

import importlib
import tempfile
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import healthlab
from healthlab.config import Paths
from healthlab.derived.rebuild import ensure_derived
from healthlab.interface.i18n import load_texts
from healthlab.interface.settings import LANGUAGES
from healthlab.pipeline.importing import confirm_import, prepare_import
from healthlab.queries.common import Period
from healthlab.reading.contracts import load_contracts
from healthlab.reports.content import ReportOptions, gather_report
from healthlab.reports.pdf import render_pdf
from healthlab.reports.texts import load_report_texts
from healthlab.storage.database import open_database, schema_version

WEB_DIR = Path(__file__).resolve().parent / "web"

PAGE_FILES = ("index.html", "app.css", "app.js", "vendor/echarts.min.js")
"""Files the window loads. Without any of them the page stays blank."""

WINDOW_LIBRARY = "webview"


@dataclass(frozen=True, slots=True)
class Check:
    """Outcome of one check.

    Attributes:
        name: Short name of what was checked.
        ok: Whether it passed.
        detail: What was found, or the error.
    """

    name: str
    ok: bool
    detail: str


def _page_files() -> str:
    """Confirm every file of the page is present."""
    missing = [name for name in PAGE_FILES if not (WEB_DIR / name).is_file()]
    if missing:
        msg = f"missing: {', '.join(missing)}"
        raise FileNotFoundError(msg)
    return f"{len(PAGE_FILES)} files"


def _texts() -> str:
    """Load the interface and report texts of every language."""
    for language in LANGUAGES:
        load_texts(language)
        load_report_texts(language)
    return ", ".join(LANGUAGES)


def _contracts() -> str:
    """Load the description of the Samsung tables."""
    return f"{len(load_contracts())} tables"


def _window_library() -> str:
    """Import the library that opens the window."""
    module = importlib.import_module(WINDOW_LIBRARY)
    return str(getattr(module, "__version__", "present"))


def _data_folder(paths: Paths) -> str:
    """Create the data folders and prove they can be written."""
    paths.ensure()
    probe = paths.logs_dir / "write_test.tmp"
    probe.write_text("ok", encoding="utf-8")
    probe.unlink()
    return str(paths.data_dir)


def _database(paths: Paths) -> str:
    """Open the database, which creates or migrates it, and its calculated tables."""
    paths.ensure()
    with open_database(paths.database) as connection:
        ensure_derived(connection)
        return f"schema version {schema_version(connection)}"


def _report() -> str:
    """Build a report from an empty database, to prove the PDF engine works."""
    with tempfile.TemporaryDirectory() as folder:
        work = Path(folder)
        with open_database(work / "check.duckdb") as connection:
            ensure_derived(connection)
            options = ReportOptions(period=Period(), language="es", generated_at=datetime.now())
            pages = render_pdf(gather_report(connection, options), work / "check.pdf")
    return f"{pages} pages"


def _import(sample: Path) -> str:
    """Import an export from start to end into a temporary app folder."""
    with tempfile.TemporaryDirectory() as folder:
        scratch = Paths(root=Path(folder) / "app")
        scratch.ensure()
        work = Path(folder) / "work"
        work.mkdir()
        result = confirm_import(prepare_import(sample, scratch, work), scratch)
    return f"{result.derived.nights} nights, {result.derived.days} days"


def run_checks(paths: Paths, sample: Path | None = None) -> list[Check]:
    """Run every check and return the outcomes, in a fixed order.

    A failing check never stops the others: the report shows everything that is
    wrong at once.

    Args:
        paths: Where the app keeps its files.
        sample: A Samsung Health export to import into a temporary folder, as
            one more check; ``None`` to skip it.

    Returns:
        One ``Check`` per piece of the app.
    """
    steps: list[tuple[str, Callable[[], str]]] = [
        ("page files", _page_files),
        ("texts", _texts),
        ("table contracts", _contracts),
        ("window library", _window_library),
        ("data folder", lambda: _data_folder(paths)),
        ("database", lambda: _database(paths)),
        ("report", _report),
    ]
    if sample is not None:
        steps.append(("import", lambda: _import(sample)))
    checks = []
    for name, step in steps:
        try:
            checks.append(Check(name, True, step()))
        except Exception as error:  # The report must list every failure.
            checks.append(Check(name, False, f"{type(error).__name__}: {error}"))
    return checks


def format_report(checks: list[Check]) -> str:
    """Return the outcomes as a short text report.

    Args:
        checks: Outcomes from ``run_checks``.

    Returns:
        One line per check, with the app version first and the verdict last.
    """
    lines = [f"HealthLab {healthlab.__version__}"]
    lines += [f"[{'OK' if check.ok else 'FAIL'}] {check.name}: {check.detail}" for check in checks]
    failed = sum(not check.ok for check in checks)
    lines.append("RESULT: OK" if not failed else f"RESULT: {failed} FAILED")
    return "\n".join(lines) + "\n"
