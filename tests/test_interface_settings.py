"""Tests for the saved settings and the interface texts."""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from misalud.interface.i18n import load_texts
from misalud.interface.settings import LANGUAGES, Settings, load_settings, save_settings
from misalud.interface.window import WEB_DIR
from misalud.queries.nights import NIGHT_METRICS

PLACEHOLDER = re.compile(r"\{(\w+)\}")
SOURCE_ROOT = Path(__file__).resolve().parents[1] / "src" / "misalud"


def test_settings_start_with_defaults_and_survive_a_restart(tmp_path: Path) -> None:
    defaults = ("stages", "oxygen", "pulse", "snoring")
    assert load_settings(tmp_path) == Settings(language="es", theme="system", tracks=defaults)
    chosen = Settings(language="en", theme="dark", tracks=("oxygen", "movement"))
    save_settings(tmp_path / "data", chosen)
    assert load_settings(tmp_path / "data") == chosen


@pytest.mark.parametrize(
    "content",
    [
        "not json",
        "[1, 2]",
        json.dumps({"language": "fr", "theme": "neon", "tracks": ["oxygen", "aura"]}),
        json.dumps({"tracks": "oxygen"}),
        json.dumps({}),
    ],
)
def test_damaged_or_unknown_settings_fall_back_to_defaults(tmp_path: Path, content: str) -> None:
    (tmp_path / "settings.json").write_text(content, encoding="utf-8")
    assert load_settings(tmp_path) == Settings()


def test_an_unknown_language_is_refused() -> None:
    with pytest.raises(ValueError, match="unknown language: fr"):
        load_texts("fr")


def test_every_language_has_the_same_texts_with_the_same_placeholders() -> None:
    reference = load_texts(LANGUAGES[0])
    for language in LANGUAGES[1:]:
        texts = load_texts(language)
        assert set(texts) == set(reference), language
        for key, text in texts.items():
            assert set(PLACEHOLDER.findall(text)) == set(PLACEHOLDER.findall(reference[key])), key
            assert text.strip(), key


def test_every_text_the_page_asks_for_exists() -> None:
    texts = load_texts("es")
    script = (WEB_DIR / "app.js").read_text(encoding="utf-8")
    markup = (WEB_DIR / "index.html").read_text(encoding="utf-8")
    asked = set(re.findall(r"\bt\('([a-z0-9_.]+)'", script))
    asked |= set(re.findall(r'data-(?:t|label)="([a-z0-9_.]+)"', markup))
    asked = {key for key in asked if not key.endswith(".")}
    assert len(asked) > 100
    assert asked - set(texts) == set()
    for metric in NIGHT_METRICS:
        assert f"metric.{metric}" in texts, metric
    for day in range(1, 8):
        assert f"weekday.{day}" in texts
    for step in ("opening", "checking", "transforming", "comparing"):
        assert f"import.step.{step}" in texts


def test_every_validation_rule_has_a_text() -> None:
    texts = load_texts("es")
    rules: set[str] = set()
    for path in (SOURCE_ROOT / "transform").glob("*.py"):
        source = path.read_text(encoding="utf-8")
        rules |= set(re.findall(r'rule="([a-z0-9_]+)"', source))
        rules |= set(re.findall(r'ValidationIssue\(\s*[^,]+,\s*[^,]+,\s*"([a-z0-9_]+)"', source))
    assert len(rules) >= 15
    assert {rule for rule in rules if f"rule.{rule}" not in texts} == set()
