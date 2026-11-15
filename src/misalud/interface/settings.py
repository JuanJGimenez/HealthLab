"""Remember the user's choices between runs: language and colour theme."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Final

from misalud.queries.night_detail import DEFAULT_TRACKS, TRACKS

LANGUAGES: Final = ("es", "en")
THEMES: Final = ("system", "light", "dark")
SETTINGS_FILE: Final = "settings.json"
DEFAULT_LANGUAGE: Final = "es"
DEFAULT_THEME: Final = "system"


@dataclass(frozen=True, slots=True)
class Settings:
    """Choices the user made in the app.

    Attributes:
        language: Interface language, ``es`` or ``en``.
        theme: ``system`` follows the computer; ``light`` and ``dark`` force one.
        tracks: Tracks shown on the "one night" screen.
    """

    language: str = DEFAULT_LANGUAGE
    theme: str = DEFAULT_THEME
    tracks: tuple[str, ...] = DEFAULT_TRACKS


def load_settings(data_dir: Path) -> Settings:
    """Read the saved settings; anything missing or invalid falls back to the default.

    Args:
        data_dir: Folder that holds the user's data.

    Returns:
        The settings to use.
    """
    try:
        saved = json.loads((data_dir / SETTINGS_FILE).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return Settings()
    if not isinstance(saved, dict):
        return Settings()
    language = saved.get("language")
    theme = saved.get("theme")
    tracks = saved.get("tracks")
    chosen = (
        tuple(str(track) for track in tracks)
        if isinstance(tracks, list) and all(track in TRACKS for track in tracks)
        else DEFAULT_TRACKS
    )
    return Settings(
        language=language if language in LANGUAGES else DEFAULT_LANGUAGE,
        theme=theme if theme in THEMES else DEFAULT_THEME,
        tracks=chosen,
    )


def save_settings(data_dir: Path, settings: Settings) -> None:
    """Write the settings next to the database.

    Args:
        data_dir: Folder that holds the user's data; created if missing.
        settings: The choices to remember.
    """
    data_dir.mkdir(parents=True, exist_ok=True)
    text = json.dumps(asdict(settings), indent=2)
    (data_dir / SETTINGS_FILE).write_text(text, encoding="utf-8")
