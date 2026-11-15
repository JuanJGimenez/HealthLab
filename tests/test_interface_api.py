"""Tests for what the window can ask Python to do."""

from __future__ import annotations

import zipfile
from pathlib import Path
from typing import Any

import pytest

import misalud
from misalud.config import Paths
from misalud.interface import api as api_module
from misalud.interface.api import Api
from misalud.interface.settings import Settings, load_settings
from misalud.storage.backup import list_backups
from tests.support.fake_dialogs import FakeDialogs
from tests.support.synthetic_export import build_export


def archive(tmp_path: Path, days: int) -> Path:
    """Build a synthetic export of ``days`` days and zip it."""
    export = build_export(tmp_path / f"export{days}", n_days=days)
    target = tmp_path / f"samsunghealth_{days}.zip"
    with zipfile.ZipFile(target, "w") as bundle:
        for path in sorted(export.root.rglob("*")):
            if path.is_file():
                bundle.write(path, path.relative_to(export.root.parent))
    return target


@pytest.fixture
def dialogs() -> FakeDialogs:
    """Dialogs that answer nothing until a test configures them."""
    return FakeDialogs()


@pytest.fixture
def api(tmp_path: Path, dialogs: FakeDialogs) -> Api:
    """The bridge over an empty app folder."""
    return Api(Paths(tmp_path / "app"), dialogs)


def do_import(api: Api, dialogs: FakeDialogs, tmp_path: Path, days: int) -> dict[str, Any]:
    """Import a synthetic export through the bridge and return the final summary."""
    dialogs.export = archive(tmp_path, days)
    preview = api.start_import()
    assert preview["ok"], preview
    result = api.confirm_import()
    assert result["ok"], result
    return result


def test_the_page_starts_with_texts_settings_and_no_data(api: Api) -> None:
    boot = api.bootstrap()
    assert boot["ok"]
    assert (boot["version"], boot["language"], boot["theme"]) == (
        misalud.__version__,
        "es",
        "system",
    )
    assert boot["languages"] == ["es", "en"]
    assert boot["texts"]["action.update"] == "Actualizar datos"
    assert boot["available"]["nights"] == 0
    assert "low_minutes" in boot["night_metrics"]
    assert (boot["sustained_low_min"], boot["low_spo2_pct"]) == (5, 90)


def test_an_empty_database_answers_every_view_with_nothing(api: Api) -> None:
    empty = api.dashboard("90", "all")
    assert (empty["ok"], empty["nights"], empty["overview"]["nights"]) == (True, [], 0)
    assert api.relate("all", "all", "hours", "score")["points"] == []


def test_language_and_theme_are_changed_and_remembered(api: Api, tmp_path: Path) -> None:
    changed = api.set_language("en")
    assert (changed["ok"], changed["texts"]["action.update"]) == (True, "Update data")
    assert api.set_theme("dark") == {"ok": True, "theme": "dark"}
    assert load_settings(tmp_path / "app" / "data") == Settings(language="en", theme="dark")
    assert api.bootstrap()["language"] == "en"
    assert api.set_language("fr") == {"ok": False, "error": "ValueError: unknown language: fr"}
    assert api.set_theme("neon")["error"] == "ValueError: unknown theme: neon"


def test_cancelling_the_file_dialog_starts_nothing(api: Api) -> None:
    assert api.start_import() == {"ok": True, "chosen": False}
    assert api.import_step() == {"ok": True, "step": ""}
    assert api.confirm_import() == {
        "ok": False,
        "error": "RuntimeError: there is no prepared import to confirm",
    }


def test_an_import_shows_a_preview_and_is_stored_only_after_confirming(
    api: Api, dialogs: FakeDialogs, tmp_path: Path
) -> None:
    dialogs.export = archive(tmp_path, 4)
    preview = api.start_import()
    assert preview["ok"] and preview["chosen"]
    assert preview["file_name"] == "samsunghealth_4.zip"
    assert preview["exported_at"] == "2026-01-04T18:00:00"
    assert (preview["first_date"], preview["is_older_export"]) == ("2026-01-01", False)
    assert preview["totals"]["new"] > 0
    assert preview["totals"]["updated"] == 0
    assert {row["table"] for row in preview["tables"]} >= {"sleep_session", "steps_day"}
    assert (preview["rejected"], preview["noticed"]) == (1, 0)
    assert {failure["domain"] for failure in preview["failed_domains"]} >= {"hrv", "stress"}
    assert all(finding["severity"] != "info" for finding in preview["compatibility"])
    assert api.bootstrap()["available"]["nights"] == 0

    result = api.confirm_import()
    assert result == {
        "ok": True,
        "import_id": 1,
        "new_records": preview["totals"]["new"],
        "updated_records": 0,
        "new_nights": 3,
        "new_days": 4,
        "backup": None,
    }
    assert api.bootstrap()["available"]["nights"] == 3
    assert api.confirm_import()["ok"] is False


def test_a_second_import_reports_what_it_added_and_makes_a_backup(
    api: Api, dialogs: FakeDialogs, tmp_path: Path
) -> None:
    do_import(api, dialogs, tmp_path, 4)
    result = do_import(api, dialogs, tmp_path, 6)
    assert (result["new_nights"], result["new_days"]) == (2, 2)
    assert result["updated_records"] > 0
    assert result["backup"] is not None


def test_a_cancelled_preview_stores_nothing(api: Api, dialogs: FakeDialogs, tmp_path: Path) -> None:
    dialogs.export = archive(tmp_path, 4)
    assert api.start_import()["ok"]
    assert api.cancel_import() == {"ok": True}
    assert api.confirm_import()["ok"] is False
    assert api.bootstrap()["available"]["nights"] == 0


def test_a_file_that_is_not_an_export_gives_an_error_answer(
    api: Api, dialogs: FakeDialogs, tmp_path: Path
) -> None:
    dialogs.export = tmp_path / "holiday.zip"
    with zipfile.ZipFile(dialogs.export, "w") as bundle:
        bundle.writestr("photo.txt", "not health data")
    answer = api.start_import()
    assert answer["ok"] is False
    assert answer["error"].startswith("ExportNotFoundError")
    assert api.confirm_import()["ok"] is False


def test_the_dashboard_returns_every_view_for_the_chosen_filter(
    api: Api, dialogs: FakeDialogs, tmp_path: Path
) -> None:
    do_import(api, dialogs, tmp_path, 6)
    everything = api.dashboard("all", "all")
    assert everything["ok"]
    assert everything["overview"]["nights"] == 5
    assert len(everything["nights"]) == 5
    assert set(everything) >= {
        "oxygen_weekdays",
        "sleep_months",
        "hrv_trend",
        "pulse_trend",
        "hrv_weekdays",
        "pulse_weekdays",
        "activity_months",
    }
    assert everything["sleep_months"][0]["month"] == "2026-01-01"
    assert everything["activity_months"][0]["days"] == 6
    weekend = api.dashboard("all", "weekend")
    weekdays = api.dashboard("all", "weekdays")
    assert weekend["overview"]["nights"] + weekdays["overview"]["nights"] == 5
    assert api.dashboard("90", "all")["overview"]["nights"] == 5
    assert (
        api.dashboard("all", "holidays")["error"] == "ValueError: unknown kind of night: holidays"
    )
    assert api.dashboard("7", "all")["ok"] is False


def test_a_period_counts_back_from_the_last_night(
    api: Api, dialogs: FakeDialogs, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    do_import(api, dialogs, tmp_path, 6)
    monkeypatch.setitem(api_module.RANGE_DAYS, "90", 2)
    recent = api.dashboard("90", "all")
    assert [night["night_date"] for night in recent["nights"]] == ["2026-01-04", "2026-01-05"]


def test_worst_nights_and_relations_are_answered(
    api: Api, dialogs: FakeDialogs, tmp_path: Path
) -> None:
    do_import(api, dialogs, tmp_path, 6)
    worst = api.worst_nights("all", "all", "low_minutes")
    assert worst["ok"]
    assert worst["nights"][0]["low_minutes"] > 0
    assert api.worst_nights("all", "all", "night_date")["ok"] is False
    related = api.relate("all", "all", "hours", "low_minutes")
    assert (related["ok"], related["nights"]) == (True, 5)
    assert api.relate("all", "all", "hours", "session_id")["ok"] is False


def test_nights_are_saved_as_csv_where_the_user_chooses(
    api: Api, dialogs: FakeDialogs, tmp_path: Path
) -> None:
    do_import(api, dialogs, tmp_path, 4)
    assert api.export_csv("all", "all") == {"ok": True, "saved": False}
    dialogs.save = tmp_path / "nights.csv"
    assert api.export_csv("all", "all") == {"ok": True, "saved": True, "file_name": "nights.csv"}
    lines = dialogs.save.read_text(encoding="utf-8-sig").splitlines()
    assert lines[0].startswith("night_date,session_id")
    assert len(lines) == 4


def test_the_database_panel_shows_state_history_and_backups(
    api: Api, dialogs: FakeDialogs, tmp_path: Path
) -> None:
    empty = api.database_panel()
    assert (empty["ok"], empty["history"], empty["last_import"], empty["backups"]) == (
        True,
        [],
        None,
        [],
    )
    do_import(api, dialogs, tmp_path, 4)
    do_import(api, dialogs, tmp_path, 6)
    panel = api.database_panel()
    assert panel["folder"] == str(tmp_path / "app" / "data")
    assert panel["version"] == misalud.__version__
    assert panel["size_bytes"] > 0
    assert [row["file_name"] for row in panel["history"]] == [
        "samsunghealth_6.zip",
        "samsunghealth_4.zip",
    ]
    assert panel["last_import"] == panel["history"][0]["imported_at"]
    assert panel["available"]["nights"] == 5
    assert panel["issues"] == [
        {"table": "snoring_event", "rule": "date_before_2020", "action": "rejected", "records": 1}
    ]
    assert len(panel["tables"]) > 20
    assert len(panel["backups"]) == 1
    assert panel["backups"][0]["name"].startswith("salud_")
    assert panel["backups"][0]["size_bytes"] > 0


def test_the_data_folder_can_be_shown(api: Api, dialogs: FakeDialogs, tmp_path: Path) -> None:
    assert api.open_data_folder() == {"ok": True}
    assert dialogs.opened == [tmp_path / "app" / "data"]


def test_a_backup_is_restored_by_name_only(api: Api, dialogs: FakeDialogs, tmp_path: Path) -> None:
    do_import(api, dialogs, tmp_path, 4)
    do_import(api, dialogs, tmp_path, 6)
    assert api.bootstrap()["available"]["nights"] == 5
    backup = list_backups(tmp_path / "app" / "data" / "backups")[0]
    assert api.restore_backup("../salud.duckdb")["error"] == (
        "RuntimeError: backup not found: ../salud.duckdb"
    )
    assert api.restore_backup(backup.name) == {"ok": True, "restored": backup.name}
    assert api.bootstrap()["available"]["nights"] == 3


def test_one_night_comes_with_tracks_tags_and_annotations(
    api: Api, dialogs: FakeDialogs, tmp_path: Path
) -> None:
    do_import(api, dialogs, tmp_path, 6)
    night = api.night("2026-01-02")
    assert (night["ok"], night["found"]) == (True, True)
    assert (night["previous"], night["next"]) == ("2026-01-01", "2026-01-03")
    assert night["night"]["night_date"] == "2026-01-02"
    assert len(night["tracks"]["stages"]) > 0
    assert len(night["tracks"]["pulse"]) > 0
    assert night["tracks"]["movement"] == []
    assert len(night["tags"]) == 8
    assert night["annotations"] == {"tags": [], "note": None}
    assert api.night("2030-01-01") == {"ok": True, "found": False}
    assert api.night("yesterday")["ok"] is False


def test_tags_and_notes_are_saved_from_the_night_screen(
    api: Api, dialogs: FakeDialogs, tmp_path: Path
) -> None:
    do_import(api, dialogs, tmp_path, 4)
    assert api.set_tag("2026-01-02", 1, True)["annotations"] == {"tags": [1], "note": None}
    noted = api.set_note("2026-01-02", "cena con amigos")
    assert noted == {"ok": True, "annotations": {"tags": [1], "note": "cena con amigos"}}
    assert api.night("2026-01-02")["annotations"]["note"] == "cena con amigos"
    assert api.set_tag("2026-01-02", 1, False)["annotations"]["tags"] == []
    assert api.set_tag("2026-01-02", 99, True)["error"] == "AnnotationError: unknown tag: 99"
    do_import(api, dialogs, tmp_path, 6)
    assert api.night("2026-01-02")["annotations"]["note"] == "cena con amigos"


def test_the_shown_tracks_are_remembered(api: Api) -> None:
    boot = api.bootstrap()
    assert boot["shown_tracks"] == ["stages", "oxygen", "pulse", "snoring"]
    assert len(boot["tracks"]) == 8
    chosen = api.set_tracks(["movement", "oxygen"])
    assert chosen == {"ok": True, "shown_tracks": ["oxygen", "movement"]}
    assert api.bootstrap()["shown_tracks"] == ["oxygen", "movement"]
    assert api.set_tracks(["aura"])["error"] == "ValueError: unknown tracks: aura"


def test_the_tag_filter_reaches_every_view(api: Api, dialogs: FakeDialogs, tmp_path: Path) -> None:
    do_import(api, dialogs, tmp_path, 6)
    api.set_tag("2026-01-02", 1, True)
    api.set_tag("2026-01-04", 1, True)
    assert len(api.bootstrap()["tags"]) == 8
    tagged = api.dashboard("all", "all", 1, True)
    assert [night["night_date"] for night in tagged["nights"]] == ["2026-01-02", "2026-01-04"]
    assert tagged["overview"]["nights"] == 2
    assert api.dashboard("all", "all", 1, False)["overview"]["nights"] == 3
    assert len(api.worst_nights("all", "all", "low_minutes", 1, True)["nights"]) == 2
    related = api.relate("all", "all", "hours", "low_minutes", None, True, 1)
    assert [point["tagged"] for point in related["points"]] == [False, True, False, True, False]
    assert api.relate("all", "all", "hours", "low_minutes", 1, False)["nights"] == 3
    dialogs.save = tmp_path / "tagged.csv"
    api.export_csv("all", "all", 1, True)
    assert len(dialogs.save.read_text(encoding="utf-8-sig").splitlines()) == 3
    comparison = api.tag_comparison("all", "all", 1)
    assert (comparison["ok"], comparison["with"]["nights"], comparison["without"]["nights"]) == (
        True,
        2,
        3,
    )
    assert comparison["with"]["enough_nights"] is False


def test_two_nights_are_compared_through_the_bridge(
    api: Api, dialogs: FakeDialogs, tmp_path: Path
) -> None:
    do_import(api, dialogs, tmp_path, 6)
    api.set_tag("2026-01-03", 2, True)
    compared = api.compare_nights("2026-01-02", "2026-01-03")
    assert (compared["ok"], compared["found"]) == (True, True)
    assert compared["a"]["night"]["night_date"] == "2026-01-02"
    assert compared["b"]["annotations"] == {"tags": [2], "note": None}
    assert len(compared["a"]["tracks"]["pulse"]) > 0
    assert set(compared["differences"]) >= {"low_minutes", "night_hr_avg"}
    assert len(compared["tags"]) == 8
    assert api.compare_nights("2026-01-02", "2030-01-01") == {
        "ok": True,
        "found": False,
        "missing": ["2030-01-01"],
    }
    assert api.compare_nights("2026-01-02", "never")["ok"] is False


def test_any_date_can_be_annotated_from_the_calendar(
    api: Api, dialogs: FakeDialogs, tmp_path: Path
) -> None:
    do_import(api, dialogs, tmp_path, 4)
    with_night = api.day("2026-01-02")
    assert (with_night["ok"], with_night["has_night"], len(with_night["tags"])) == (True, True, 8)
    api.set_tag("2025-12-20", 6, True)
    earlier = api.day("2025-12-20")
    assert (earlier["has_night"], earlier["annotations"]["tags"]) == (False, [6])


def test_tags_are_managed_through_the_bridge(api: Api) -> None:
    assert len(api.tags()["tags"]) == 8
    added = api.add_tag("Mate")
    assert added["tags"][-1]["name"] == "Mate"
    new_id = added["tags"][-1]["tag_id"]
    assert api.rename_tag(new_id, "Mate de noche")["tags"][-1]["name"] == "Mate de noche"
    off = api.set_tag_active(new_id, False)
    assert off["tags"][-1]["is_active"] is False
    assert len(api.bootstrap()["tags"]) == 8
    assert api.add_tag("alcohol")["error"].startswith("AnnotationError: there is already")
    assert api.rename_tag(99, "x")["ok"] is False
    assert api.set_tag_active(99, True)["ok"] is False


def test_one_day_comes_with_tracks_and_the_typical_day(
    api: Api, dialogs: FakeDialogs, tmp_path: Path
) -> None:
    do_import(api, dialogs, tmp_path, 6)
    boot = api.bootstrap()
    assert boot["day_tracks"] == ["pulse", "stress", "steps", "exercise", "sleep"]
    assert "day.hr_avg" in boot["relate_metrics"]
    day = api.day_detail("2026-01-02")
    assert (day["ok"], day["found"]) == (True, True)
    assert (day["previous"], day["next"]) == ("2026-01-01", "2026-01-03")
    assert len(day["tracks"]["steps"]) > 0
    assert len(day["tracks"]["sleep"]) > 0
    assert len(day["tags"]) == 8
    assert api.set_tag("2026-01-02", 3, True)["ok"]
    assert api.day_detail("2026-01-02")["annotations"]["tags"] == [3]
    assert api.day_detail("2030-01-01") == {"ok": True, "found": False}
    assert (api.day("2026-01-02")["has_day"], api.day("2030-01-01")["has_day"]) == (True, False)
    everything = api.dashboard("all", "all")
    assert len(everything["hourly"]["pulse"]) > 0
    assert everything["notices"] == []
    assert api.relate("all", "all", "day.hr_avg", "hours")["ok"]


def test_the_report_is_saved_as_a_pdf_where_the_user_chooses(
    api: Api, dialogs: FakeDialogs, tmp_path: Path
) -> None:
    do_import(api, dialogs, tmp_path, 6)
    start = api.report_options()
    assert (start["ok"], start["watch_model"], start["profile"]["name"]) == (True, "", None)
    assert api.create_report("all", {}) == {"ok": True, "saved": False}

    dialogs.save = tmp_path / "informe.pdf"
    plain = api.create_report("all", {"watch_model": "  Galaxy Watch  "})
    assert plain == {"ok": True, "saved": True, "file_name": "informe.pdf", "pages": 2}
    assert dialogs.save.read_bytes().startswith(b"%PDF")
    assert api.report_options()["watch_model"] == "Galaxy Watch"

    personal = {
        "include_personal": True,
        "name": "Ana Pérez",
        "birth_year": "1982",
        "sex": "femenino",
        "height_cm": "170",
        "weight_kg": "64.5",
    }
    assert api.create_report("90", personal)["saved"] is True
    assert api.report_options()["profile"] == {
        "name": "Ana Pérez",
        "birth_year": 1982,
        "sex": "femenino",
        "height_cm": 170.0,
        "weight_kg": None,
    }
    assert api.create_report("all", {"include_personal": True})["saved"] is True
    assert api.report_options()["profile"]["name"] is None
    wrong = api.create_report("all", {"include_personal": True, "birth_year": "1492"})
    assert wrong["error"] == "AnnotationError: birth year out of range: 1492"
    api.set_language("en")
    assert api.create_report("all", {})["saved"] is True


def test_the_report_can_add_blocks_a_relation_and_nights_in_detail(
    api: Api, dialogs: FakeDialogs, tmp_path: Path
) -> None:
    do_import(api, dialogs, tmp_path, 6)
    dialogs.save = tmp_path / "completo.pdf"
    asked = {
        "blocks": ["heart", "sleep", "day_night"],
        "crosses": [["day.hr_avg", "low_minutes"]],
        "detail_nights": ["2026-01-03", ""],
    }
    assert api.create_report("all", asked)["pages"] == 2 + 3 + 1
    assert api.create_report("all", {"blocks": ["weather"]})["error"] == (
        "ValueError: unknown report blocks: weather"
    )
    too_many = {"detail_nights": ["2026-01-01", "2026-01-02", "2026-01-03"]}
    assert api.create_report("all", too_many)["ok"] is False
