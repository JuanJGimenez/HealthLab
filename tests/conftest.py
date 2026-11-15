"""Fixtures shared by the tests."""

from __future__ import annotations

import zipfile
from pathlib import Path

import pytest

from tests.support.synthetic_export import SyntheticExport, build_export


@pytest.fixture
def export(tmp_path: Path) -> SyntheticExport:
    """A four-day synthetic export: three nights and a partial export day."""
    return build_export(tmp_path / "export", n_days=4)


@pytest.fixture
def export_zip(export: SyntheticExport, tmp_path: Path) -> Path:
    """The synthetic export zipped the way a user would: with its folder inside."""
    archive = tmp_path / "export.zip"
    with zipfile.ZipFile(archive, "w") as bundle:
        for path in sorted(export.root.rglob("*")):
            if path.is_file():
                bundle.write(path, Path("Samsung Health") / path.relative_to(export.root.parent))
    return archive
