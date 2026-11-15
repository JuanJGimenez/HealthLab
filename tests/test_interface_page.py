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
    page = browser.new_page(viewport={"width": 1280, "height": 900})
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

    # The filters ask Python again.
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
