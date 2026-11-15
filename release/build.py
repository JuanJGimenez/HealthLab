r"""Build the portable MiSalud folder, check it, and install it over an old one.

Usage, from the project folder::

    python release/build.py                      # build and check dist/MiSalud
    python release/build.py --install C:\MiSalud  # also copy it to that folder
    python release/build.py --sample export.zip  # also try a whole import

Installing replaces the program files in the target folder and leaves its
``data`` folder untouched, so the same command serves the first installation
and every later update.

The build needs the libraries of the app plus PyInstaller:
``pip install ".[ui,build]"``.
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

PROJECT = Path(__file__).resolve().parent.parent
SPEC = PROJECT / "release" / "misalud.spec"
MANUAL = PROJECT / "docs" / "manual.md"
DIST = PROJECT / "dist"
WORK = PROJECT / "build"

APP_FOLDER = "MiSalud"
EXECUTABLE = "MiSalud.exe" if sys.platform == "win32" else "MiSalud"
INTERNAL_FOLDER = "_internal"
MANUAL_NAME = "Manual.md"
DATA_FOLDER = "data"
"""Folder with the user's data. Nothing in this script writes to or deletes it."""

PROGRAM_ITEMS = (EXECUTABLE, INTERNAL_FOLDER, MANUAL_NAME)
"""Everything a version of the app consists of. An update replaces exactly these."""

HOME_ENV_VAR = "MISALUD_HOME"


class BuildError(Exception):
    """A step of the build did not give the expected result."""


def build(dist: Path = DIST, work: Path = WORK) -> Path:
    """Run PyInstaller and return the folder it produced.

    Args:
        dist: Where the app folder is created.
        work: Scratch folder of PyInstaller.

    Returns:
        The app folder, ``dist / "MiSalud"``.

    Raises:
        BuildError: If PyInstaller fails.
    """
    command = [
        sys.executable,
        "-m",
        "PyInstaller",
        str(SPEC),
        "--noconfirm",
        "--clean",
        "--distpath",
        str(dist),
        "--workpath",
        str(work),
    ]
    if subprocess.run(command, cwd=PROJECT, check=False).returncode != 0:
        msg = "PyInstaller failed; the lines above say why"
        raise BuildError(msg)
    folder = dist / APP_FOLDER
    shutil.copyfile(MANUAL, folder / MANUAL_NAME)
    return folder


def verify(folder: Path, sample: Path | None = None) -> str:
    """Run the self-check of the built app and return its report.

    The check runs with a temporary data folder, so the built folder stays free
    of data and can be copied over an installation without risk.

    Args:
        folder: The built app folder.
        sample: A Samsung Health export the built app imports into a temporary
            folder, to prove the whole import works; ``None`` to skip it.

    Returns:
        The text of the self-check report.

    Raises:
        BuildError: If the app does not start or a check fails.
    """
    with tempfile.TemporaryDirectory() as home:
        environment = {**os.environ, HOME_ENV_VAR: home}
        command = [str(folder / EXECUTABLE), "--check"]
        if sample is not None:
            command.append(str(sample.resolve()))
        done = subprocess.run(command, env=environment, check=False, timeout=1800)
        report_file = Path(home) / DATA_FOLDER / "logs" / "check.txt"
        report = report_file.read_text(encoding="utf-8") if report_file.is_file() else ""
    if done.returncode != 0 or not report.endswith("RESULT: OK\n"):
        msg = f"the built app failed its self-check (exit code {done.returncode}):\n{report}"
        raise BuildError(msg)
    if (folder / DATA_FOLDER).exists():
        msg = f"the built folder must not contain {DATA_FOLDER}/"
        raise BuildError(msg)
    return report


def install(source: Path, target: Path) -> list[str]:
    """Copy the program files of a built folder into the folder the user runs.

    Only the items in ``PROGRAM_ITEMS`` are replaced. The ``data`` folder of
    the target, and anything else the user keeps there, is left as it is.

    Args:
        source: The built app folder.
        target: The folder the app is used from; created when missing.

    Returns:
        The names of the items that were copied.

    Raises:
        BuildError: If the source carries a data folder, is the target itself,
            or lacks the executable.
    """
    source, target = source.resolve(), target.resolve()
    if source == target:
        msg = "the installation folder must be different from the built folder"
        raise BuildError(msg)
    if (source / DATA_FOLDER).exists():
        msg = f"refusing to install from a folder that contains {DATA_FOLDER}/"
        raise BuildError(msg)
    if not (source / EXECUTABLE).is_file():
        msg = f"{EXECUTABLE} is missing in {source}"
        raise BuildError(msg)
    target.mkdir(parents=True, exist_ok=True)
    copied = []
    for name in PROGRAM_ITEMS:
        new, old = source / name, target / name
        if not new.exists():
            continue
        if old.is_dir():
            shutil.rmtree(old)
        elif old.exists():
            old.unlink()
        if new.is_dir():
            shutil.copytree(new, old)
        else:
            shutil.copy2(new, old)
        copied.append(name)
    return copied


def main(arguments: list[str] | None = None) -> int:
    """Build, check and optionally install. Return the process exit code."""
    parser = argparse.ArgumentParser(description="Build the portable MiSalud folder.")
    parser.add_argument(
        "--install",
        metavar="FOLDER",
        type=Path,
        help="after a successful build, put the program in this folder, keeping its data",
    )
    parser.add_argument(
        "--sample",
        metavar="ZIP",
        type=Path,
        help="a Samsung Health export to import into a temporary folder as one more check",
    )
    options = parser.parse_args(arguments)
    try:
        folder = build()
        print(verify(folder, options.sample))
        print(f"Built and checked: {folder}")
        if options.install:
            install(folder, options.install)
            print(f"Installed in: {options.install.resolve()}")
    except (BuildError, OSError) as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
