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
    known = {tag["tag_id"] for tag in list_tags(connection, include_inactive=True)}
    if tag_id not in known:
        msg = f"unknown tag: {tag_id}"
        raise AnnotationError(msg)
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
