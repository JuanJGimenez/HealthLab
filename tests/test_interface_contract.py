"""Tests for the agreement between ``Api`` and the page about the shape of answers."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any, TypedDict, is_typeddict

import pytest

from misalud.config import Paths
from misalud.interface.api import Api
from misalud.interface.window import WEB_DIR
from tests.support.contract import (
    ContractError,
    answer_problems,
    checked,
    declared_answer,
    problems_in,
    public_methods,
)
from tests.support.fake_dialogs import FakeDialogs


class _Row(TypedDict):
    name: str
    size: int
    ratio: float | None


class _Answer(TypedDict):
    rows: list[_Row]
    by_name: dict[str, list[int]]
    anything: Any


@pytest.fixture
def api(tmp_path: Path) -> Api:
    return Api(Paths(tmp_path / "app"), FakeDialogs())


def test_every_method_declares_the_shape_of_its_answer(api: Api) -> None:
    names = public_methods(api)
    assert len(names) == 28
    undeclared = [name for name in names if not is_typeddict(declared_answer(name))]
    assert undeclared == []


def test_the_page_calls_only_methods_that_exist_and_uses_them_all(api: Api) -> None:
    script = (WEB_DIR / "app.js").read_text(encoding="utf-8")
    called = set(re.findall(r"\bcall\('([a-z_]+)'", script))
    assert called == set(public_methods(api))


def test_a_value_that_fits_has_no_problems() -> None:
    answer = {
        "rows": [{"name": "a", "size": 1, "ratio": None}, {"name": "b", "size": 2, "ratio": 1}],
        "by_name": {"a": [1, 2], "b": []},
        "anything": object(),
    }
    assert problems_in(answer, _Answer) == []


def test_each_kind_of_difference_is_reported_with_its_place() -> None:
    answer = {
        "rows": [{"name": "a", "size": True, "extra": 1}, "text"],
        "by_name": {"a": [1, "2"], "b": 3},
    }
    assert problems_in(answer, _Answer) == [
        "answer.anything: missing",
        "answer.by_name.a[1]: expected int, got '2'",
        "answer.by_name.b: expected list, got int",
        "answer.rows[0].ratio: missing",
        "answer.rows[0].extra: not declared",
        "answer.rows[0].size: expected int, got True",
        "answer.rows[1]: expected _Row, got str",
    ]
    assert problems_in({"name": "a", "size": 1, "ratio": "high"}, _Row) == [
        "answer.ratio: expected float, got 'high'"
    ]
    assert problems_in(1.5, str | None, "x") == ["x: expected str, got 1.5"]


def test_a_failure_is_accepted_only_in_its_own_shape() -> None:
    assert answer_problems("tags", {"ok": False, "error": "ValueError: no"}) == []
    assert answer_problems("tags", {"ok": False}) == ["tags: malformed failure {'ok': False}"]
    assert answer_problems("tags", {"ok": True, "tags": []}) == []
    assert answer_problems("tags", {"ok": True}) == ["tags.tags: missing"]


def test_a_watched_api_refuses_an_answer_out_of_shape(tmp_path: Path) -> None:
    watched = checked(Api(Paths(tmp_path / "app"), FakeDialogs()))
    assert watched.import_step() == {"ok": True, "step": ""}
    assert watched.set_theme("purple")["ok"] is False

    drifted = Api(Paths(tmp_path / "other"), FakeDialogs())
    drifted.import_step = lambda: {"ok": True, "stage": ""}  # type: ignore[method-assign]
    with pytest.raises(ContractError, match=r"import_step.step: missing"):
        checked(drifted).import_step()
