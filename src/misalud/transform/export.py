"""Transform a whole export, one domain at a time.

Each domain is transformed on its own. If one fails, for example because Samsung
removed a table, the failure is recorded and the other domains still go through
(design decision 10).
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Final

import pandas as pd

from misalud.reading.errors import ReadingError
from misalud.transform.activity import (
    transform_activity_summary,
    transform_custom_exercises,
    transform_exercise,
    transform_movement,
    transform_steps,
    transform_vitality,
    transform_weight,
)
from misalud.transform.common import DomainResult, Source, TransformError, ValidationIssue
from misalud.transform.heart import (
    transform_ecg,
    transform_heart_rate,
    transform_hrv,
    transform_stress,
)
from misalud.transform.night_signals import (
    transform_respiratory_rate,
    transform_skin_temperature,
    transform_snoring,
)
from misalud.transform.oxygen import transform_oxygen
from misalud.transform.sleep import transform_sleep

Transformer = Callable[[Source], DomainResult]

DOMAINS: Final[dict[str, Transformer]] = {
    "sleep": transform_sleep,
    "oxygen": transform_oxygen,
    "skin_temperature": transform_skin_temperature,
    "respiratory_rate": transform_respiratory_rate,
    "snoring": transform_snoring,
    "heart_rate": transform_heart_rate,
    "hrv": transform_hrv,
    "stress": transform_stress,
    "ecg": transform_ecg,
    "exercise": transform_exercise,
    "custom_exercise": transform_custom_exercises,
    "weight": transform_weight,
    "steps": transform_steps,
    "activity_summary": transform_activity_summary,
    "vitality": transform_vitality,
    "movement": transform_movement,
}
"""Every domain and the function that transforms it. A domain is the unit of failure."""

DOMAIN_SOURCES: Final[dict[str, tuple[str, ...]]] = {
    "sleep": ("sleep", "sleep_stage"),
    "oxygen": ("tracker.oxygen_saturation",),
    "skin_temperature": ("skin_temperature",),
    "respiratory_rate": ("respiratory_rate",),
    "snoring": ("sleep_snoring",),
    "heart_rate": ("tracker.heart_rate",),
    "hrv": ("hrv",),
    "stress": ("stress",),
    "ecg": ("ecg",),
    "exercise": ("exercise",),
    "custom_exercise": ("exercise.custom_exercise",),
    "weight": ("weight",),
    "steps": ("step_daily_trend",),
    "activity_summary": ("activity.day_summary",),
    "vitality": ("vitality_score",),
    "movement": ("movement",),
}
"""Samsung tables each domain cannot work without. A domain is skipped when one is blocked.

``sleep_combined`` is not listed: the sleep domain uses it when present and works
without it.
"""


@dataclass(slots=True)
class TransformResult:
    """Output of transforming a whole export.

    Attributes:
        tables: Clean MiSalud tables by name, from the domains that succeeded.
        issues: Records rejected or kept with a caveat, across all domains.
        failures: Reason of failure by domain, for the domains that did not succeed.
    """

    tables: dict[str, pd.DataFrame] = field(default_factory=dict)
    issues: list[ValidationIssue] = field(default_factory=list)
    failures: dict[str, str] = field(default_factory=dict)


def transform_export(
    source: Source,
    domains: dict[str, Transformer] | None = None,
    *,
    blocked_tables: frozenset[str] = frozenset(),
) -> TransformResult:
    """Transform every domain of an export.

    Args:
        source: The export.
        domains: Domains to run. Defaults to all of them.
        blocked_tables: Samsung tables the compatibility report found unusable.
            A domain that reads one of them is not run and counts as failed: a
            column that changed meaning could otherwise pass as valid data.

    Returns:
        The tables of the domains that succeeded, every issue found and the
        reason each failed domain could not be transformed.
    """
    result = TransformResult()
    for name, transformer in (DOMAINS if domains is None else domains).items():
        blocked = sorted(blocked_tables.intersection(DOMAIN_SOURCES.get(name, ())))
        if blocked:
            result.failures[name] = f"incompatible tables: {', '.join(blocked)}"
            continue
        try:
            domain = transformer(source)
        except (ReadingError, TransformError) as error:
            result.failures[name] = str(error)
            continue
        result.tables.update(domain.tables)
        result.issues.extend(domain.issues)
    return result
