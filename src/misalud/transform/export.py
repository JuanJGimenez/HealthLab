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
    "weight": transform_weight,
    "steps": transform_steps,
    "activity_summary": transform_activity_summary,
    "vitality": transform_vitality,
    "movement": transform_movement,
}
"""Every domain and the function that transforms it. A domain is the unit of failure."""


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
    source: Source, domains: dict[str, Transformer] | None = None
) -> TransformResult:
    """Transform every domain of an export.

    Args:
        source: The export.
        domains: Domains to run. Defaults to all of them.

    Returns:
        The tables of the domains that succeeded, every issue found and the
        reason each failed domain could not be transformed.
    """
    result = TransformResult()
    for name, transformer in (DOMAINS if domains is None else domains).items():
        try:
            domain = transformer(source)
        except (ReadingError, TransformError) as error:
            result.failures[name] = str(error)
            continue
        result.tables.update(domain.tables)
        result.issues.extend(domain.issues)
    return result
