"""Tests for the file that lists the licences of the bundled libraries."""

from __future__ import annotations

import sys
from dataclasses import dataclass, field
from email.message import Message
from importlib.metadata import PackageNotFoundError
from pathlib import Path
from typing import Any, cast

import pytest
from release.notices import runtime_distributions, third_party_notices


@dataclass
class FakeFile:
    """A file recorded in the metadata of a fake library."""

    relative: str

    @property
    def name(self) -> str:
        """Return the file name, without its folders."""
        return Path(self.relative).name

    def __str__(self) -> str:
        """Return the path relative to the library's install folder."""
        return self.relative


@dataclass
class FakeLibrary:
    """Just enough of ``importlib.metadata.Distribution`` for these tests."""

    name: str
    requires: list[str] | None = None
    headers: dict[str, list[str]] = field(default_factory=dict)
    files: list[FakeFile] = field(default_factory=list)
    root: Path = Path()
    version: str = "1.0"

    @property
    def metadata(self) -> Message:
        """Return the headers of the library, as Python's metadata does."""
        message = Message()
        message["Name"] = self.name
        for key, values in self.headers.items():
            for value in values:
                message[key] = value
        return message

    def locate_file(self, entry: FakeFile) -> Path:
        """Return where a recorded file sits on disk."""
        return self.root / entry.relative


def finder(libraries: list[FakeLibrary]) -> Any:
    table = {library.name.lower(): library for library in libraries}

    def find(name: str) -> FakeLibrary:
        if name.lower() not in table:
            raise PackageNotFoundError(name)
        return table[name.lower()]

    return find


def test_requirements_are_followed_with_their_conditions() -> None:
    world = [
        FakeLibrary(
            "healthlab",
            [
                "pandas>=2",
                "pywebview>=6; extra == 'ui'",
                "pytest; extra == 'dev'",
                "pythonnet; sys_platform == 'never'",
                "missing-lib",
            ],
        ),
        FakeLibrary("pandas", ["numpy>=1", "tzdata; python_version >= '3'"]),
        FakeLibrary("numpy"),
        FakeLibrary("tzdata"),
        FakeLibrary("pywebview", ["proxy_tools", "bottle[extra]"]),
        FakeLibrary("proxy_tools"),
        FakeLibrary("bottle", ["Numpy"]),
        FakeLibrary("pytest"),
        FakeLibrary("pythonnet"),
        FakeLibrary("pyinstaller", ["altgraph"]),
        FakeLibrary("altgraph"),
    ]
    names = [library.name for library in runtime_distributions(find=finder(world))]
    assert names == [
        "altgraph",
        "bottle",
        "numpy",
        "pandas",
        "proxy_tools",
        "pyinstaller",
        "pywebview",
        "tzdata",
    ]


def test_each_library_gets_its_licence_and_files(tmp_path: Path) -> None:
    (tmp_path / "lib-1.0.dist-info" / "licenses").mkdir(parents=True)
    (tmp_path / "lib-1.0.dist-info" / "LICENSE").write_text("MIT text\n", encoding="utf-8")
    (tmp_path / "lib-1.0.dist-info" / "licenses" / "extra.txt").write_text("more", "utf-8")
    files = [
        FakeFile("lib/__init__.py"),
        FakeFile("lib-1.0.dist-info/LICENSE"),
        FakeFile("lib-1.0.dist-info/licenses/extra.txt"),
        FakeFile("lib-1.0.dist-info/NOTICE"),  # listed but not on disk
    ]
    libraries = [
        FakeLibrary(
            "lib",
            headers={"License-Expression": ["MIT"], "Home-page": ["https://lib.example"]},
            files=files,
            root=tmp_path,
        ),
        FakeLibrary(
            "classic",
            headers={
                "Classifier": ["License :: OSI Approved :: BSD License", "Topic :: Science"],
                "Project-URL": ["Source, https://classic.example"],
            },
            version="2.3",
        ),
        FakeLibrary("plain", headers={"License": ["Apache 2.0"]}),
        FakeLibrary("wordy", headers={"License": ["Line one\nline two"]}),
    ]
    chart = tmp_path / "echarts.NOTICE"
    chart.write_text("Apache ECharts\n", encoding="utf-8")
    text = third_party_notices(cast(list[Any], libraries), [chart])
    assert text.startswith("HealthLab includes the following third-party components.")
    assert "Python 3." in text
    assert (
        "lib 1.0\nLicence: MIT\nProject: https://lib.example\n\n--- LICENSE ---\nMIT text" in text
    )
    assert "--- extra.txt ---\nmore" in text
    assert "NOTICE ---" not in text
    assert "classic 2.3\nLicence: BSD License\nProject: https://classic.example" in text
    assert "plain 1.0\nLicence: Apache 2.0" in text
    assert "wordy 1.0\nLicence: see the licence text below" in text
    assert text.endswith("echarts.NOTICE\n\nApache ECharts\n")


def test_python_section_includes_its_licence_when_found(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (tmp_path / "LICENSE.txt").write_text("PSF terms\n", encoding="utf-8")
    monkeypatch.setattr(sys, "base_prefix", str(tmp_path))
    assert third_party_notices([]).endswith(
        "Licence: Python Software Foundation License\n\nPSF terms\n"
    )
    monkeypatch.setattr(sys, "base_prefix", str(tmp_path / "nowhere"))
    assert third_party_notices([]).endswith("Licence: Python Software Foundation License\n")
