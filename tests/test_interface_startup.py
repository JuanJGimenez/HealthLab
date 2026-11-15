"""Tests for the self-check and for what a start of the app does."""

from __future__ import annotations

import zipfile
from datetime import datetime
from pathlib import Path

import pytest

import misalud
from misalud.config import Paths
from misalud.interface import selfcheck, startup
from misalud.interface.selfcheck import Check, format_report, run_checks
from tests.support.synthetic_export import build_export


@pytest.fixture
def paths(tmp_path: Path) -> Paths:
    return Paths(root=tmp_path / "app")


def test_a_complete_app_passes_every_check(paths: Paths) -> None:
    checks = run_checks(paths)
    assert [check.name for check in checks] == [
        "page files",
        "texts",
        "table contracts",
        "window library",
        "data folder",
        "database",
        "report",
    ]
    assert all(check.ok for check in checks), checks
    details = {check.name: check.detail for check in checks}
    assert details["page files"] == "4 files"
    assert details["texts"] == "es, en"
    assert details["data folder"] == str(paths.data_dir)
    assert details["database"] == "schema version 2"
    assert details["report"] == "2 pages"
    assert paths.database.is_file()
    assert not list(paths.logs_dir.iterdir())


def test_a_missing_page_file_and_library_fail_without_stopping_the_rest(
    paths: Paths, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    web = tmp_path / "web"
    web.mkdir()
    (web / "index.html").write_text("", encoding="utf-8")
    monkeypatch.setattr(selfcheck, "WEB_DIR", web)
    monkeypatch.setattr(selfcheck, "WINDOW_LIBRARY", "misalud_no_such_library")
    outcome = {check.name: check for check in run_checks(paths)}
    assert not outcome["page files"].ok
    assert outcome["page files"].detail == (
        "FileNotFoundError: missing: app.css, app.js, vendor/echarts.min.js"
    )
    assert not outcome["window library"].ok
    assert outcome["window library"].detail.startswith("ModuleNotFoundError")
    assert outcome["database"].ok
    assert outcome["report"].ok


def test_the_report_lists_each_check_and_a_verdict() -> None:
    passed = [Check("texts", True, "es, en")]
    assert format_report(passed) == (
        f"MiSalud {misalud.__version__}\n[OK] texts: es, en\nRESULT: OK\n"
    )
    failed = [*passed, Check("database", False, "IOError: locked")]
    assert format_report(failed).splitlines()[-2:] == [
        "[FAIL] database: IOError: locked",
        "RESULT: 1 FAILED",
    ]


def sample_export(tmp_path: Path) -> Path:
    """Build a synthetic export of four days and zip it."""
    export = build_export(tmp_path / "export", n_days=4)
    target = tmp_path / "samsunghealth_sample.zip"
    with zipfile.ZipFile(target, "w") as bundle:
        for path in sorted(export.root.rglob("*")):
            if path.is_file():
                bundle.write(path, path.relative_to(export.root.parent))
    return target


def test_a_sample_export_is_imported_away_from_the_user_data(paths: Paths, tmp_path: Path) -> None:
    checks = run_checks(paths, sample_export(tmp_path))
    assert (checks[-1].name, checks[-1].ok, checks[-1].detail) == (
        "import",
        True,
        "3 nights, 4 days",
    )
    assert not paths.exports_dir.exists() or not list(paths.exports_dir.iterdir())
    broken = run_checks(paths, tmp_path / "missing.zip")[-1]
    assert (broken.name, broken.ok) == ("import", False)


def test_the_check_flag_takes_a_sample_export(paths: Paths, tmp_path: Path) -> None:
    assert startup.run(["--check", str(sample_export(tmp_path))], paths, refuse, refuse) == 0
    report = startup.check_report_path(paths).read_text(encoding="utf-8")
    assert "[OK] import: 3 nights, 4 days" in report


def refuse(_: object) -> None:
    raise AssertionError("must not be called")


def test_the_check_flag_writes_the_report_and_opens_no_window(paths: Paths) -> None:
    assert startup.run(["--check"], paths, refuse, refuse) == 0
    report = startup.check_report_path(paths).read_text(encoding="utf-8")
    assert report.endswith("RESULT: OK\n")
    assert report.count("[OK]") == 7


def test_a_failed_check_gives_a_failing_exit_code(
    paths: Paths, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(selfcheck, "WINDOW_LIBRARY", "misalud_no_such_library")
    assert startup.run(["--check"], paths, refuse, refuse) == 1
    report = startup.check_report_path(paths).read_text(encoding="utf-8")
    assert report.endswith("RESULT: 1 FAILED\n")


def test_a_normal_start_opens_the_window(paths: Paths) -> None:
    opened: list[Paths] = []
    assert startup.run([], paths, opened.append, refuse) == 0
    assert opened == [paths]
    assert not startup.error_log_path(paths).exists()


def test_an_error_at_start_is_logged_and_shown(paths: Paths) -> None:
    def broken(_: Paths) -> None:
        raise RuntimeError("no window")

    shown: list[str] = []
    moment = datetime(2026, 11, 15, 10, 30)
    assert startup.run([], paths, broken, shown.append, now=moment) == 1
    assert startup.run([], paths, broken, shown.append) == 1
    log = startup.error_log_path(paths)
    assert shown[0] == f"RuntimeError: no window\n\n{log}"
    text = log.read_text(encoding="utf-8")
    assert text.startswith(f"2026-11-15T10:30:00 MiSalud {misalud.__version__}\n")
    assert text.count("RuntimeError: no window") == 2
