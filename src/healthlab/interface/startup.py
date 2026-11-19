"""Decide what a start of the app does, and keep a record when it fails.

A packaged app has no console: an error at start would close the window with no
trace. This module writes the error to a log file inside the data folder and
hands a short message to the caller, so the user sees what happened and where
the detail is.
"""

from __future__ import annotations

import traceback
from collections.abc import Callable, Sequence
from datetime import datetime
from pathlib import Path

import healthlab
from healthlab.config import Paths
from healthlab.interface.selfcheck import format_report, run_checks

CHECK_FLAG = "--check"
CHECK_REPORT_NAME = "check.txt"
ERROR_LOG_NAME = "error.log"


def check_report_path(paths: Paths) -> Path:
    """Return where the self-check report is written."""
    return paths.logs_dir / CHECK_REPORT_NAME


def error_log_path(paths: Paths) -> Path:
    """Return the file that collects errors at start."""
    return paths.logs_dir / ERROR_LOG_NAME


def _run_check(paths: Paths, sample: Path | None) -> int:
    """Run the self-check, write its report and return the exit code."""
    checks = run_checks(paths, sample)
    paths.ensure()
    check_report_path(paths).write_text(format_report(checks), encoding="utf-8")
    return 0 if all(check.ok for check in checks) else 1


def _record_error(paths: Paths, now: datetime) -> Path:
    """Append the error being handled to the log and return the log path."""
    paths.ensure()
    target = error_log_path(paths)
    with target.open("a", encoding="utf-8") as log:
        log.write(f"{now.isoformat(timespec='seconds')} HealthLab {healthlab.__version__}\n")
        log.write(traceback.format_exc())
        log.write("\n")
    return target


def run(
    arguments: Sequence[str],
    paths: Paths,
    open_window: Callable[[Paths], None],
    show_error: Callable[[str], None],
    *,
    now: datetime | None = None,
) -> int:
    """Start the app, or run the self-check when asked.

    Args:
        arguments: Command-line arguments, without the program name. ``--check``
            runs the self-check; an export named after it is imported into a
            temporary folder as part of the check.
        paths: Where the app keeps its files.
        open_window: Opens the window and returns when the user closes it.
        show_error: Shows a message to the user when the window cannot open.
        now: Moment written in the error log; the current time when omitted.

    Returns:
        The exit code of the process: 0 when everything went well.
    """
    if CHECK_FLAG in arguments:
        after = arguments[list(arguments).index(CHECK_FLAG) + 1 :]
        return _run_check(paths, Path(after[0]) if after else None)
    try:
        open_window(paths)
    except Exception as error:  # Last line of defence at start.
        target = _record_error(paths, now or datetime.now())
        show_error(f"{type(error).__name__}: {error}\n\n{target}")
        return 1
    return 0
