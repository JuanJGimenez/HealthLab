"""Tests that run the app page in a real browser, from an empty app to a full dashboard.

They need Playwright and its Chromium; without them the tests are skipped. The
rest of the suite covers every Python line either way.
"""

from __future__ import annotations

import zipfile
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest

from misalud.config import Paths
from misalud.interface.api import Api
from tests.support.fake_dialogs import FakeDialogs
from tests.support.page_bridge import api_methods, open_page
from tests.support.synthetic_export import build_export

playwright = pytest.importorskip("playwright.sync_api")


@pytest.fixture(scope="module")
def browser() -> Iterator[Any]:
    """A headless Chromium shared by the tests of this module."""
    with playwright.sync_playwright() as driver:
        try:
            chromium = driver.chromium.launch()
        except playwright.Error as error:  # pragma: no cover - depends on the machine
            pytest.skip(f"Chromium is not available: {error}")
        yield chromium
        chromium.close()


@pytest.fixture
def export_archive(tmp_path: Path) -> Path:
    """A zipped synthetic export of six days."""
    export = build_export(tmp_path / "export", n_days=6)
    target = tmp_path / "samsunghealth_test.zip"
    with zipfile.ZipFile(target, "w") as bundle:
        for path in sorted(export.root.rglob("*")):
            if path.is_file():
                bundle.write(path, path.relative_to(export.root.parent))
    return target


def test_the_bridge_exposes_only_the_public_methods(tmp_path: Path) -> None:
    names = api_methods(Api(Paths(tmp_path / "app"), FakeDialogs()))
    assert "start_import" in names
    assert "dashboard" in names
    assert not [name for name in names if name.startswith("_")]


def test_from_an_empty_app_to_a_dashboard_in_two_languages(
    browser: Any, tmp_path: Path, export_archive: Path
) -> None:
    dialogs = FakeDialogs(export=export_archive, save=tmp_path / "nights.csv")
    api = Api(Paths(tmp_path / "app"), dialogs)
    page = browser.new_page(
        viewport={"width": 1280, "height": 900}, timezone_id="America/Argentina/Buenos_Aires"
    )
    problems = open_page(page, api)

    # An empty app invites the user to import.
    assert page.is_visible("#welcome")
    assert not page.is_visible("#content")
    assert page.inner_text("#btn-import") == "Actualizar datos"

    # Importing shows a preview first; nothing is stored until it is confirmed.
    page.click("#btn-import-first")
    page.wait_for_selector("#dialog-foot .btn.primary")
    assert page.inner_text("#dialog-title") == "Vista previa de la importación"
    assert "samsunghealth_test.zip" in page.inner_text("#dialog-body")
    assert api.bootstrap()["available"]["nights"] == 0
    page.click("#dialog-foot .btn.primary")
    page.wait_for_function(
        "document.querySelector('#dialog-title').textContent === 'Importación terminada'"
    )
    page.click("#dialog-foot .btn.primary")

    # The dashboard appears with the headline figures.
    page.wait_for_selector("#kpis .kpi")
    assert page.is_visible("#content")
    assert page.inner_text("#kpis .kpi:first-child .v") == "5"
    assert "5 noches" in page.inner_text("#meta")
    assert page.locator("#worst tbody tr").count() == 5

    # Every view draws without errors, including the ones without data.
    for tab in ("sleep", "heart", "activity", "relate", "data"):
        page.click(f"#tabs button[data-tab={tab}]")
        assert page.is_visible(f"#p-{tab}")
    assert page.locator("#dt tbody tr").count() == 5
    page.click("#csv")
    page.wait_for_function("document.querySelector('#csv-done').textContent !== ''")
    assert (tmp_path / "nights.csv").read_text(encoding="utf-8-sig").count("\n") == 6

    # A click on a night opens its detail, with tracks, tags and a note.
    page.click("#tabs button[data-tab=oxygen]")
    page.click("#worst tbody tr:first-child")
    page.wait_for_selector("#night:not([hidden])")
    assert not page.is_visible("#content")
    assert "Noche del" in page.inner_text("#night-title")
    assert page.locator("#night-facts .fact").count() == 9
    assert page.locator("#night-tags .chip").count() == 8
    assert page.locator("#night-toggles .chip[aria-pressed=true]").count() == 4
    page.click("#night-tags .chip:first-child")
    page.wait_for_selector("#night-tags .chip:first-child[aria-pressed=true]")
    page.fill("#night-note", "prueba")
    page.click("#night-note-save")
    page.wait_for_function("document.querySelector('#night-note-done').textContent === 'Guardado'")
    noted_day = api.dashboard("all", "all")["nights"][2]["night_date"]
    assert api.night(noted_day)["annotations"] == {"tags": [1], "note": "prueba"}
    page.click("#night-toggles [data-track=movement]")
    page.wait_for_selector("#night-toggles [data-track=movement][aria-pressed=true]")
    assert api.bootstrap()["shown_tracks"][-1] == "movement"
    title = page.inner_text("#night-title")
    page.click("#night-next")
    page.wait_for_function(f"document.querySelector('#night-title').textContent !== {title!r}")
    # Two nights can be compared, aligned by elapsed time or by the clock.
    page.click("#night-compare")
    page.wait_for_selector("#compare:not([hidden])")
    page.wait_for_function("document.querySelectorAll('#cmp-table tbody tr').length === 11")
    assert page.inner_text("#cmp-table thead th:last-child").startswith("Diferencia")
    page.click("#cmp-align button[data-v=clock]")
    page.wait_for_selector("#cmp-align button[data-v=clock][aria-pressed=true]")
    page.fill("#cmp-b", "2025-06-01")
    page.dispatch_event("#cmp-b", "change")
    page.wait_for_function("document.querySelector('#cmp-message').textContent.includes('No hay')")
    page.click("#compare-back")
    assert page.is_visible("#night")
    page.click("#night-back")
    assert page.is_visible("#content")

    # A click on the calendar annotates any day.
    page.locator("#o4").scroll_into_view_if_needed()
    cell = page.evaluate(
        """() => {
            const node = document.getElementById('o4');
            const chart = echarts.getInstanceByDom(node);
            const point = chart.convertToPixel({seriesIndex: 0}, '2026-01-03');
            const box = node.getBoundingClientRect();
            return [box.x + point[0], box.y + point[1]];
        }"""
    )
    page.mouse.click(cell[0], cell[1])
    page.wait_for_selector("#overlay:not([hidden])")
    assert page.inner_text("#dialog-title").startswith("Anotar el")
    assert api.set_tag("2026-01-03", 5, True)["ok"]
    assert "3" in page.inner_text("#dialog-title").split()[2]
    assert page.locator("#dialog-body .chip").count() == 8
    page.click("#dialog-close")

    # The user manages tags, and a tag filters every view.
    page.click("#btn-tags")
    page.wait_for_selector("#tag-new")
    page.fill("#tag-new", "Mate")
    page.click("#tag-add")
    page.wait_for_function("document.querySelectorAll('#tag-list .tagrow').length === 9")
    page.click("#dialog-close")
    assert "Con Mate" in page.inner_text("#f-tag")
    page.select_option("#f-tag", "1:with")
    page.wait_for_function("document.querySelector('#kpis .kpi .v').textContent === '1'")
    page.click("#tabs button[data-tab=relate]")
    page.select_option("#cmp-tag", "1")
    page.wait_for_selector("#tagcompare table")
    assert "menos de 10 noches" in page.inner_text("#tagcompare")
    page.select_option("#r-highlight", "1")
    page.select_option("#f-tag", "")
    page.wait_for_function("document.querySelector('#kpis .kpi .v').textContent === '5'")

    # The filters ask Python again.
    page.click("#tabs button[data-tab=data]")
    page.click("#f-nights button[data-v=weekend]")
    page.wait_for_function("document.querySelectorAll('#dt tbody tr').length < 5")

    # The database panel lists the import.
    page.click("#btn-database")
    page.wait_for_selector("#overlay:not([hidden])")
    assert "samsunghealth_test.zip" in page.inner_text("#dialog-body")
    page.click("#dialog-close")

    # Changing the language rewrites every text and is remembered.
    page.select_option("#language", "en")
    page.wait_for_function("document.querySelector('#btn-import').textContent === 'Update data'")
    assert page.inner_text("#tabs button[data-tab=oxygen]") == "Oxygen"
    assert api.bootstrap()["language"] == "en"

    assert problems == []
    page.close()
