# PyInstaller recipe for the portable MiSalud folder.
#
# Run it through ``release/build.py``, which also checks the result. The recipe
# produces ``dist/MiSalud/`` with ``MiSalud.exe`` and an ``_internal`` folder
# that holds Python, the libraries and the files of the app.
#
# The code and its files are taken from ``src/`` and not from an installed copy,
# so the folder always matches the source it was built from.

from pathlib import Path

PROJECT = Path(SPECPATH).resolve().parent
PACKAGE = PROJECT / "src" / "misalud"

# Files the code reads at run time, each with the folder it must land in.
RESOURCE_FOLDERS = (
    "reading",  # contracts.json
    "interface/locales",
    "interface/web",
    "interface/web/vendor",
    "reports/locales",
)
CODE_SUFFIXES = {".py", ".pyc"}

datas = [
    (str(path), f"misalud/{folder}")
    for folder in RESOURCE_FOLDERS
    for path in sorted((PACKAGE / folder).iterdir())
    if path.is_file() and path.suffix not in CODE_SUFFIXES
]

analysis = Analysis(
    [str(PROJECT / "release" / "launcher.py")],
    pathex=[str(PROJECT / "src")],
    datas=datas,
    hiddenimports=[],
    # Not used by the app; left out in case the build computer has them.
    excludes=["tkinter", "pytest", "playwright", "matplotlib", "scipy"],
    noarchive=False,
)
archive = PYZ(analysis.pure)
executable = EXE(
    archive,
    analysis.scripts,
    [],
    exclude_binaries=True,
    name="MiSalud",
    icon=str(PROJECT / "release" / "misalud.ico"),
    console=False,  # a desktop app: no black console window behind it
    upx=False,  # compressed executables trigger more antivirus false alarms
)
COLLECT(
    executable,
    analysis.binaries,
    analysis.datas,
    name="MiSalud",
    upx=False,
)
