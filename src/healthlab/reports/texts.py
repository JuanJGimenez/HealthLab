"""Words and number formats of the report, one file per language."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date
from decimal import ROUND_HALF_UP, Decimal
from functools import cache
from pathlib import Path
from typing import Any

LOCALES_DIR = Path(__file__).resolve().parent / "locales"
REPORT_LANGUAGES = ("es", "en")


@dataclass(frozen=True, slots=True)
class ReportTexts:
    """The texts of one language, with the formats that go with them.

    Attributes:
        language: ``es`` or ``en``.
        words: Every text, by key.
    """

    language: str
    words: dict[str, str]

    def text(self, key: str, **values: object) -> str:
        """Return a text with its placeholders filled in."""
        return self.words[key].format(**values)

    def number(self, value: float | None, digits: int = 0) -> str:
        """Write a number with the decimal mark of the language; a dash when missing.

        Halves round up, as people expect on paper: 57.5 is written 58.
        """
        if value is None:
            return self.words["none"]
        step = Decimal(1).scaleb(-digits)
        rounded = Decimal(str(float(value))).quantize(step, rounding=ROUND_HALF_UP)
        if rounded == 0:
            rounded = abs(rounded)
        return f"{rounded:.{digits}f}".replace(".", self.words["decimal"])

    def day(self, value: str | date | None) -> str:
        """Write a date as day, short month and year; a dash when missing."""
        if value is None:
            return self.words["none"]
        when = date.fromisoformat(value) if isinstance(value, str) else value
        return f"{when.day} {self.month(when.month)} {when.year}"

    def month(self, number: int) -> str:
        """Return the short name of a month, 1 for January."""
        return self.words["months"].split(",")[number - 1]

    def weekday(self, number: int) -> str:
        """Return the short name of a weekday, 1 for Monday."""
        return self.words["weekdays"].split(",")[number - 1]

    def tag(self, tag: dict[str, Any]) -> str:
        """Return the name of a tag: translated while built-in and not renamed."""
        key = tag["builtin_key"]
        if key is not None and tag["name"] == key:
            return self.words[f"tag.{key}"]
        return str(tag["name"])


@cache
def load_report_texts(language: str) -> ReportTexts:
    """Return the report texts of a language.

    Raises:
        ValueError: If the report does not exist in that language.
    """
    if language not in REPORT_LANGUAGES:
        msg = f"unknown report language: {language}"
        raise ValueError(msg)
    content = json.loads((LOCALES_DIR / f"{language}.json").read_text(encoding="utf-8"))
    return ReportTexts(language, {str(key): str(value) for key, value in content.items()})
