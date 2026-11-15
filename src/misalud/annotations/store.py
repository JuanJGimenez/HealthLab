"""Save and read what the user notes about a date: tags and a free note.

A tag is a yes-or-no mark on a calendar day ("alcohol", "late dinner"). It holds
for that day and for the night that begins that evening, the same date
convention as the ``night`` table. Nothing here is ever written by an import.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Any

from misalud.storage.database import Connection
from misalud.storage.schema import NOTE_TAG_KEY


class AnnotationError(ValueError):
    """An annotation cannot be saved, for example because its tag does not exist."""


def list_tags(connection: Connection, *, include_inactive: bool = False) -> list[dict[str, Any]]:
    """Return the tags a date can be marked with, in creation order.

    Args:
        connection: An open connection.
        include_inactive: Whether to include tags the user switched off.

    Returns:
        One record per tag with ``tag_id``, ``name``, ``builtin_key`` (``None``
        for a tag the user created) and ``is_active``. The reserved note tag is
        never listed.
    """
    rows = connection.execute(
        """SELECT tag_id, name, builtin_key, is_active FROM tag
        WHERE builtin_key IS DISTINCT FROM ? AND (is_active OR ?) ORDER BY tag_id""",
        [NOTE_TAG_KEY, include_inactive],
    ).fetchall()
    names = ("tag_id", "name", "builtin_key", "is_active")
    return [dict(zip(names, row, strict=True)) for row in rows]


def _note_tag_id(connection: Connection) -> int:
    """Return the id of the reserved tag that carries free notes."""
    rows = connection.execute(
        "SELECT tag_id FROM tag WHERE builtin_key = ?", [NOTE_TAG_KEY]
    ).fetchall()
    return int(rows[0][0])


def day_annotations(connection: Connection, day: date) -> dict[str, Any]:
    """Return what the user noted about a date.

    Args:
        connection: An open connection.
        day: The calendar day.

    Returns:
        ``tags``: ids of the tags set on that day, in order. ``note``: the free
        note, or ``None``.
    """
    note_tag = _note_tag_id(connection)
    rows = connection.execute(
        "SELECT tag_id, note FROM annotation WHERE day = ? ORDER BY tag_id", [day]
    ).fetchall()
    return {
        "tags": [tag_id for tag_id, _ in rows if tag_id != note_tag],
        "note": next((note for tag_id, note in rows if tag_id == note_tag), None),
    }


def set_tag(
    connection: Connection, day: date, tag_id: int, present: bool, *, now: datetime | None = None
) -> None:
    """Mark or unmark a date with a tag.

    Setting a tag that is already set, or clearing one that is not, changes
    nothing.

    Args:
        connection: An open connection.
        day: The calendar day.
        tag_id: A tag from ``list_tags``.
        present: True to mark the date, False to unmark it.
        now: Moment recorded as creation time. Defaults to the clock.

    Raises:
        AnnotationError: If the tag does not exist or is the reserved note tag.
    """
    _require_tag(connection, tag_id)
    if not present:
        connection.execute("DELETE FROM annotation WHERE day = ? AND tag_id = ?", [day, tag_id])
        return
    moment = now or datetime.now()
    connection.execute(
        """INSERT INTO annotation (day, tag_id, note, created_at, updated_at)
        VALUES (?, ?, NULL, ?, ?) ON CONFLICT DO NOTHING""",
        [day, tag_id, moment, moment],
    )


def set_note(connection: Connection, day: date, text: str, *, now: datetime | None = None) -> None:
    """Save the free note of a date; an empty text removes it.

    Args:
        connection: An open connection.
        day: The calendar day.
        text: The note. Surrounding blank space is dropped.
        now: Moment recorded as creation or edit time. Defaults to the clock.
    """
    note_tag = _note_tag_id(connection)
    cleaned = text.strip()
    if not cleaned:
        connection.execute("DELETE FROM annotation WHERE day = ? AND tag_id = ?", [day, note_tag])
        return
    moment = now or datetime.now()
    connection.execute(
        """INSERT INTO annotation (day, tag_id, note, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?)
        ON CONFLICT DO UPDATE SET note = excluded.note, updated_at = excluded.updated_at""",
        [day, note_tag, cleaned, moment, moment],
    )


def _clean_name(connection: Connection, name: str, *, except_tag: int | None = None) -> str:
    """Return a tag name ready to store, or refuse it.

    Raises:
        AnnotationError: If the name is empty or another tag already uses it.
    """
    cleaned = " ".join(name.split())
    if not cleaned:
        msg = "a tag needs a name"
        raise AnnotationError(msg)
    taken = connection.execute(
        "SELECT count(*) FROM tag WHERE lower(name) = lower(?) AND tag_id IS DISTINCT FROM ?",
        [cleaned, except_tag],
    ).fetchall()
    if taken[0][0]:
        msg = f"there is already a tag named {cleaned}"
        raise AnnotationError(msg)
    return cleaned


def _require_tag(connection: Connection, tag_id: int) -> None:
    """Make sure a tag exists and is not the reserved note tag.

    Raises:
        AnnotationError: Otherwise.
    """
    if tag_id not in {tag["tag_id"] for tag in list_tags(connection, include_inactive=True)}:
        msg = f"unknown tag: {tag_id}"
        raise AnnotationError(msg)


def add_tag(connection: Connection, name: str) -> int:
    """Create a tag of the user's own.

    Args:
        connection: An open connection.
        name: The name to show. Repeated blank space is collapsed.

    Returns:
        The id of the new tag.

    Raises:
        AnnotationError: If the name is empty or already in use.
    """
    cleaned = _clean_name(connection, name)
    rows = connection.execute(
        """INSERT INTO tag (tag_id, name, is_active, builtin_key)
        SELECT coalesce(max(tag_id), 0) + 1, ?, TRUE, NULL FROM tag RETURNING tag_id""",
        [cleaned],
    ).fetchall()
    return int(rows[0][0])


def rename_tag(connection: Connection, tag_id: int, name: str) -> None:
    """Change the name of a tag; the dates marked with it keep their mark.

    A built-in tag that is renamed stops being translated: it shows the name
    the user gave it, in every language.

    Raises:
        AnnotationError: If the tag does not exist, or the name is empty or in use.
    """
    _require_tag(connection, tag_id)
    cleaned = _clean_name(connection, name, except_tag=tag_id)
    connection.execute("UPDATE tag SET name = ? WHERE tag_id = ?", [cleaned, tag_id])


def set_tag_active(connection: Connection, tag_id: int, active: bool) -> None:
    """Switch a tag off or back on.

    A tag that is off is no longer offered when annotating, but the dates
    already marked with it keep their mark: nothing is deleted.

    Raises:
        AnnotationError: If the tag does not exist.
    """
    _require_tag(connection, tag_id)
    connection.execute("UPDATE tag SET is_active = ? WHERE tag_id = ?", [active, tag_id])
