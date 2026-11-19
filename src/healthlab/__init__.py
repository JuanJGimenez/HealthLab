"""HealthLab: local desktop app that accumulates and analyses Samsung Health exports.

The code is organised in layers. A layer may import only the layers listed before it:

``config``, ``reading``, ``transform``, ``storage``, ``derived``, ``annotations``,
``queries``, ``pipeline``, ``reports``, ``interface``.

``tests/test_architecture.py`` enforces that rule.
"""

from typing import Final

__version__: Final = "1.1.0"

LAYERS: Final = (
    "config",
    "reading",
    "transform",
    "storage",
    "derived",
    "annotations",
    "queries",
    "pipeline",
    "reports",
    "interface",
)
"""Layers from the lowest to the highest. A layer may import only the ones before it."""
