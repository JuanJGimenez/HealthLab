"""Tests that keep the layered structure honest."""

from __future__ import annotations

import ast
from pathlib import Path

import misalud

PACKAGE_DIR = Path(misalud.__file__).resolve().parent
ORDER = {name: position for position, name in enumerate(misalud.LAYERS)}


def layer_of(path: Path) -> str | None:
    """Return the layer a source file belongs to, or ``None`` for the package root."""
    name = path.relative_to(PACKAGE_DIR).parts[0].removesuffix(".py")
    return None if name == "__init__" else name


def imported_layers(source: str, package: tuple[str, ...]) -> set[str]:
    """Return the MiSalud layers a piece of source code imports.

    Args:
        source: Python source code.
        package: Dotted package the code lives in, as parts, used to resolve
            relative imports. For ``misalud/reading/csv.py`` it is
            ``("misalud", "reading")``.

    Returns:
        The names of the imported layers.
    """
    found: set[str] = set()
    for node in ast.walk(ast.parse(source)):
        targets: list[str] = []
        if isinstance(node, ast.Import):
            targets = [alias.name for alias in node.names]
        elif isinstance(node, ast.ImportFrom):
            base = package[: len(package) - node.level + 1] if node.level else ()
            module = (*base, *(node.module.split(".") if node.module else ()))
            targets = [".".join((*module, alias.name)) for alias in node.names]
        for target in targets:
            parts = target.split(".")
            if parts[0] == "misalud" and len(parts) > 1 and parts[1] in ORDER:
                found.add(parts[1])
    return found


def upward_imports(layer: str, imported: set[str]) -> set[str]:
    """Return the imported layers that sit above ``layer``."""
    return {name for name in imported if ORDER[name] > ORDER[layer]}


def test_layers_on_disk_match_the_declared_order() -> None:
    on_disk = {
        entry.name.removesuffix(".py")
        for entry in PACKAGE_DIR.iterdir()
        if (entry.is_dir() and (entry / "__init__.py").is_file())
        or (entry.suffix == ".py" and entry.name != "__init__.py")
    }
    assert on_disk == set(misalud.LAYERS)


def test_a_layer_imports_only_lower_layers() -> None:
    violations = []
    for path in sorted(PACKAGE_DIR.rglob("*.py")):
        layer = layer_of(path)
        if layer is None:
            continue
        package = ("misalud", *path.relative_to(PACKAGE_DIR).parts[:-1])
        imported = imported_layers(path.read_text(encoding="utf-8"), package)
        violations += [
            f"{path.relative_to(PACKAGE_DIR)} imports {name}"
            for name in sorted(upward_imports(layer, imported))
        ]
    assert violations == []


def test_the_check_sees_absolute_and_relative_imports() -> None:
    source = (
        "import misalud.storage.merge\n"
        "from misalud.interface import window\n"
        "from ..queries import nights\n"
        "from . import contracts\n"
        "from .. import config\n"
        "import json\n"
    )
    found = imported_layers(source, ("misalud", "reading"))
    assert found == {"storage", "interface", "queries", "reading", "config"}


def test_the_check_flags_only_upward_imports() -> None:
    imported = {"config", "reading", "storage", "interface"}
    assert upward_imports("transform", imported) == {"storage", "interface"}
    assert upward_imports("interface", imported) == set()


def test_every_layer_states_its_responsibility() -> None:
    for layer in misalud.LAYERS:
        module = PACKAGE_DIR / layer / "__init__.py"
        path = module if module.is_file() else PACKAGE_DIR / f"{layer}.py"
        docstring = ast.get_docstring(ast.parse(path.read_text(encoding="utf-8")))
        assert docstring, layer
        assert len(docstring.splitlines()) >= 3, layer
