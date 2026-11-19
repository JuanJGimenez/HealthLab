"""Interface texts, one file per language (design decision 14).

No screen carries a sentence written in code: every visible text has a key, and
each language file gives the words for that key.
"""

from __future__ import annotations

import json
from functools import cache
from pathlib import Path

from healthlab.interface.settings import LANGUAGES

LOCALES_DIR = Path(__file__).resolve().parent / "locales"


@cache
def load_texts(language: str) -> dict[str, str]:
    """Return every interface text of a language, by key.

    Args:
        language: ``es`` or ``en``.

    Returns:
        The texts of that language.

    Raises:
        ValueError: If the language is not one the app has.
    """
    if language not in LANGUAGES:
        msg = f"unknown language: {language}"
        raise ValueError(msg)
    content = json.loads((LOCALES_DIR / f"{language}.json").read_text(encoding="utf-8"))
    return {str(key): str(value) for key, value in content.items()}
