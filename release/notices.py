"""Collect the licences of the libraries the built folder carries.

The built folder ships Python and every library the app needs, and their
licences ask that their copyright notices travel with them. This module finds
those libraries by following the declared requirements of the app from the
installed package metadata, and writes one text file with the name, version,
licence and licence files of each.

The list is taken from the environment the build runs in, so it matches the
libraries PyInstaller actually packs.
"""

from __future__ import annotations

import sys
from collections.abc import Callable, Iterable
from importlib.metadata import Distribution, PackageNotFoundError, distribution
from pathlib import Path

from packaging.requirements import Requirement
from packaging.utils import canonicalize_name

APP_DISTRIBUTION = "healthlab"
APP_EXTRAS = ("ui",)
"""Optional parts of the app that go into the built folder: the window."""

BUNDLED_TOOLS = ("pyinstaller",)
"""Packages outside the requirements whose code still lands in the folder.

PyInstaller puts its small start-up program inside ``HealthLab.exe``.
"""

LICENCE_FILE_PREFIXES = ("LICENSE", "LICENCE", "COPYING", "NOTICE", "AUTHORS")
SEPARATOR = "=" * 78

Finder = Callable[[str], Distribution]


def _wanted(requirement: Requirement, extras: Iterable[str]) -> bool:
    """Tell whether a requirement applies here, with the extras asked for."""
    if requirement.marker is None:
        return True
    return any(requirement.marker.evaluate({"extra": extra}) for extra in ("", *extras))


def runtime_distributions(
    root: str = APP_DISTRIBUTION,
    extras: Iterable[str] = APP_EXTRAS,
    *,
    find: Finder = distribution,
) -> list[Distribution]:
    """Return the installed libraries the app needs to run, without the app itself.

    The requirements are followed from ``root`` down, keeping only those whose
    conditions (operating system, Python version, extras) hold here. A library
    that is required but not installed is skipped: PyInstaller cannot pack it
    either.

    Args:
        root: Name of the app's distribution.
        extras: Optional parts of the app to include.
        find: Looks up an installed distribution by name.

    Returns:
        The libraries, sorted by name, each once.
    """
    found: dict[str, Distribution] = {}
    pending: list[tuple[str, tuple[str, ...]]] = [(root, tuple(extras))]
    pending += [(tool, ()) for tool in BUNDLED_TOOLS]
    while pending:
        name, chosen = pending.pop()
        key = canonicalize_name(name)
        if key in found:
            continue
        try:
            current = find(name)
        except PackageNotFoundError:
            continue
        found[key] = current
        for text in current.requires or ():
            requirement = Requirement(text)
            if _wanted(requirement, chosen):
                pending.append((requirement.name, tuple(requirement.extras)))
    found.pop(canonicalize_name(root), None)
    return [found[key] for key in sorted(found)]


def _licence_name(library: Distribution) -> str:
    """Return the licence a library declares, in the most precise form it gives."""
    metadata = library.metadata
    expression = metadata.get("License-Expression")
    if expression:
        return str(expression)
    classifiers = [
        value.split(" :: ")[-1]
        for value in metadata.get_all("Classifier") or ()
        if value.startswith("License ::")
    ]
    short = (metadata.get("License") or "").strip()
    if classifiers:
        return ", ".join(classifiers)
    return short if short and "\n" not in short else "see the licence text below"


def _licence_files(library: Distribution) -> list[tuple[str, str]]:
    """Return the name and text of each licence file a library installed."""
    texts = []
    for entry in library.files or ():
        name = entry.name.upper()
        if name.startswith(LICENCE_FILE_PREFIXES) or "/licenses/" in str(entry).lower():
            path = Path(str(library.locate_file(entry)))
            if path.is_file():
                texts.append((entry.name, path.read_text(encoding="utf-8", errors="replace")))
    return texts


def _python_section() -> str:
    """Return the section about Python itself, which the folder also carries."""
    version = ".".join(str(part) for part in sys.version_info[:3])
    lines = [SEPARATOR, f"Python {version}", "Licence: Python Software Foundation License"]
    candidates = (Path(sys.base_prefix) / "LICENSE.txt", Path(sys.base_prefix) / "LICENSE")
    text = next((path for path in candidates if path.is_file()), None)
    if text is not None:
        lines += ["", text.read_text(encoding="utf-8", errors="replace").strip()]
    return "\n".join(lines)


def _library_section(library: Distribution) -> str:
    """Return the section about one library: name, version, licence and its files."""
    metadata = library.metadata
    lines = [
        SEPARATOR,
        f"{metadata['Name']} {library.version}",
        f"Licence: {_licence_name(library)}",
    ]
    home = metadata.get("Home-page") or next(
        (value.split(", ", 1)[-1] for value in metadata.get_all("Project-URL") or ()), None
    )
    if home:
        lines.append(f"Project: {home}")
    for name, text in _licence_files(library):
        lines += ["", f"--- {name} ---", text.strip()]
    return "\n".join(lines)


def third_party_notices(libraries: Iterable[Distribution], extra: Iterable[Path] = ()) -> str:
    """Return the text of the third-party licence file.

    Args:
        libraries: The libraries the folder carries.
        extra: More licence files to include whole, such as those of the chart
            library copied into the page.

    Returns:
        The full text, one section per component.
    """
    sections = [
        "HealthLab includes the following third-party components. Each keeps its own"
        " licence,\nreproduced or named below. The licence of HealthLab itself is in"
        " LICENSE.txt.",
        _python_section(),
        *(_library_section(library) for library in libraries),
    ]
    for path in extra:
        sections.append(f"{SEPARATOR}\n{path.name}\n\n{path.read_text(encoding='utf-8').strip()}")
    return "\n\n".join(sections) + "\n"
