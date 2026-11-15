"""The user's personal data for the report: name, birth year, sex and height.

Kept only in the database on this computer. The report includes it only when the
user asks for it, each time.
"""

from __future__ import annotations

from datetime import date
from typing import Any

from misalud.annotations.store import AnnotationError
from misalud.storage.database import Connection

EARLIEST_BIRTH_YEAR = 1900


def load_profile(connection: Connection) -> dict[str, Any]:
    """Return the saved personal data, with height and weight proposed from the watch.

    Args:
        connection: An open connection.

    Returns:
        ``name``, ``birth_year``, ``sex`` and ``height_cm`` as saved (``None``
        when never saved), and ``weight_kg``: the most recent weight Samsung
        Health has. When no height was saved, the most recent one from Samsung
        Health is proposed.
    """
    saved = connection.execute(
        "SELECT name, birth_year, sex, height_cm FROM user_profile LIMIT 1"
    ).fetchall()
    name, birth_year, sex, height = saved[0] if saved else (None, None, None, None)
    measured = connection.execute(
        """SELECT arg_max(weight_kg, measured_at) FILTER (weight_kg IS NOT NULL),
            arg_max(height_cm, measured_at) FILTER (height_cm IS NOT NULL) FROM weight"""
    ).fetchall()[0]
    return {
        "name": name,
        "birth_year": birth_year,
        "sex": sex,
        "height_cm": height if height is not None else measured[1],
        "weight_kg": measured[0],
    }


def save_profile(
    connection: Connection,
    *,
    name: str | None,
    birth_year: int | None,
    sex: str | None,
    height_cm: float | None,
) -> None:
    """Save the personal data, replacing what was there.

    Args:
        connection: An open connection.
        name: As the user wants it printed; blank counts as missing.
        birth_year: Four-digit year, or ``None``.
        sex: Free text as the user wants it printed, or ``None``.
        height_cm: Height in centimetres, or ``None``.

    Raises:
        AnnotationError: If the birth year is not between 1900 and this year.
    """
    if birth_year is not None and not EARLIEST_BIRTH_YEAR <= birth_year <= date.today().year:
        msg = f"birth year out of range: {birth_year}"
        raise AnnotationError(msg)
    connection.execute("DELETE FROM user_profile")
    connection.execute(
        "INSERT INTO user_profile VALUES (?, ?, ?, ?)",
        [(name or "").strip() or None, birth_year, (sex or "").strip() or None, height_cm],
    )
