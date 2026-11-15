"""Tests for the user's own tags and notes."""

from __future__ import annotations

from collections.abc import Iterator
from datetime import date, datetime

import pandas as pd
import pytest

from misalud.annotations.store import (
    AnnotationError,
    add_tag,
    day_annotations,
    list_tags,
    rename_tag,
    set_note,
    set_tag,
    set_tag_active,
)
from misalud.storage.database import Connection, open_database
from misalud.storage.merge import ImportInfo, apply_merge

DAY = date(2026, 1, 5)
NOW = datetime(2026, 1, 6, 9, 0)
LATER = datetime(2026, 1, 7, 9, 0)


@pytest.fixture
def db() -> Iterator[Connection]:
    """An empty database in memory."""
    with open_database(None) as connection:
        yield connection


def test_the_app_ships_with_the_agreed_tags(db: Connection) -> None:
    tags = list_tags(db)
    assert [tag["builtin_key"] for tag in tags] == [
        "alcohol",
        "late_dinner",
        "nasal_congestion",
        "nap",
        "illness",
        "travel",
        "medication",
        "intense_training",
    ]
    assert tags[0] == {"tag_id": 1, "name": "alcohol", "builtin_key": "alcohol", "is_active": True}


def test_switched_off_tags_are_listed_only_on_request(db: Connection) -> None:
    db.execute("UPDATE tag SET is_active = FALSE WHERE tag_id = 2")
    db.execute("INSERT INTO tag (tag_id, name, is_active) VALUES (50, 'mate', TRUE)")
    assert [tag["tag_id"] for tag in list_tags(db)] == [1, 3, 4, 5, 6, 7, 8, 50]
    everything = list_tags(db, include_inactive=True)
    assert len(everything) == 9
    assert everything[-1] == {"tag_id": 50, "name": "mate", "builtin_key": None, "is_active": True}


def test_a_date_starts_without_annotations(db: Connection) -> None:
    assert day_annotations(db, DAY) == {"tags": [], "note": None}


def test_tags_are_set_and_cleared_on_a_date(db: Connection) -> None:
    set_tag(db, DAY, 3, True, now=NOW)
    set_tag(db, DAY, 1, True, now=NOW)
    set_tag(db, DAY, 1, True, now=LATER)
    assert day_annotations(db, DAY) == {"tags": [1, 3], "note": None}
    assert db.execute("SELECT created_at FROM annotation WHERE tag_id = 1").fetchall() == [(NOW,)]
    assert day_annotations(db, date(2026, 1, 6)) == {"tags": [], "note": None}
    set_tag(db, DAY, 1, False)
    set_tag(db, DAY, 8, False)
    assert day_annotations(db, DAY)["tags"] == [3]


def test_an_unknown_tag_or_the_note_tag_cannot_be_set(db: Connection) -> None:
    with pytest.raises(AnnotationError, match="unknown tag: 99"):
        set_tag(db, DAY, 99, True)
    with pytest.raises(AnnotationError, match="unknown tag: 9"):
        set_tag(db, DAY, 9, True)


def test_a_free_note_is_saved_edited_and_removed(db: Connection) -> None:
    set_note(db, DAY, "  dormí en el sillón  ", now=NOW)
    set_tag(db, DAY, 4, True, now=NOW)
    assert day_annotations(db, DAY) == {"tags": [4], "note": "dormí en el sillón"}
    set_note(db, DAY, "dormí en el sillón, con ventilador", now=LATER)
    assert day_annotations(db, DAY)["note"] == "dormí en el sillón, con ventilador"
    times = db.execute("SELECT created_at, updated_at FROM annotation WHERE note IS NOT NULL")
    assert times.fetchall() == [(NOW, LATER)]
    set_note(db, DAY, "   ")
    assert day_annotations(db, DAY) == {"tags": [4], "note": None}


def test_an_import_never_touches_annotations(db: Connection) -> None:
    set_tag(db, DAY, 1, True, now=NOW)
    set_note(db, DAY, "cumpleaños", now=NOW)
    frame = pd.DataFrame(
        {
            "samsung_id": pd.Series(["a"], dtype="string"),
            "day": pd.to_datetime(["2026-01-05"]),
            "steps": [9000.0],
            "distance_m": [1.0],
            "calorie_kcal": [1.0],
        }
    )
    apply_merge(db, {"steps_day": frame}, info=ImportInfo("x.zip", datetime(2026, 1, 6)))
    assert day_annotations(db, DAY) == {"tags": [1], "note": "cumpleaños"}


def test_the_user_can_add_tags_of_their_own(db: Connection) -> None:
    new_id = add_tag(db, "  mate   de noche ")
    assert new_id == 10
    assert list_tags(db)[-1] == {
        "tag_id": 10,
        "name": "mate de noche",
        "builtin_key": None,
        "is_active": True,
    }
    set_tag(db, DAY, new_id, True)
    assert day_annotations(db, DAY)["tags"] == [10]
    for name, reason in [
        ("  ", "needs a name"),
        ("Mate de Noche", "already"),
        ("alcohol", "already"),
    ]:
        with pytest.raises(AnnotationError, match=reason):
            add_tag(db, name)


def test_a_tag_can_be_renamed_and_keeps_its_dates(db: Connection) -> None:
    set_tag(db, DAY, 2, True)
    rename_tag(db, 2, "Cena después de las 22")
    assert list_tags(db)[1]["name"] == "Cena después de las 22"
    assert list_tags(db)[1]["builtin_key"] == "late_dinner"
    assert day_annotations(db, DAY)["tags"] == [2]
    rename_tag(db, 2, "cena después de las 22")
    with pytest.raises(AnnotationError, match="already a tag named alcohol"):
        rename_tag(db, 2, "alcohol")
    with pytest.raises(AnnotationError, match="needs a name"):
        rename_tag(db, 2, "")
    with pytest.raises(AnnotationError, match="unknown tag: 9"):
        rename_tag(db, 9, "notas")


def test_a_tag_switched_off_keeps_its_dates_and_can_come_back(db: Connection) -> None:
    set_tag(db, DAY, 4, True)
    set_tag_active(db, 4, False)
    assert 4 not in [tag["tag_id"] for tag in list_tags(db)]
    assert day_annotations(db, DAY)["tags"] == [4]
    set_tag_active(db, 4, True)
    assert 4 in [tag["tag_id"] for tag in list_tags(db)]
    with pytest.raises(AnnotationError, match="unknown tag: 77"):
        set_tag_active(db, 77, False)
