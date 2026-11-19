"""The shape of every answer the page receives from ``Api``.

The page is JavaScript and reads these answers by field name, so a renamed or
missing field would only show up on screen. Declaring each answer here gives
that agreement one written form, checked twice: the type checker compares it
with the code of ``Api``, and the tests compare it with every real answer.

Rows that come straight from a query (a night, a month, an import) are declared
as ``Record``: their columns are described in ``docs/data_dictionary.md``.

Every answer also carries ``ok``; a failed call carries only ``ok`` and
``error``. ``Api`` adds both, so they are not repeated in each shape.

This module does not postpone the evaluation of annotations (no
``from __future__ import annotations``): Python must see ``NotRequired`` when
each class is created to know which fields are optional.
"""

from typing import NotRequired, TypedDict

from healthlab.annotations.profile import Profile
from healthlab.annotations.store import DayAnnotations
from healthlab.queries.common import Record
from healthlab.queries.database import DataPeriod
from healthlab.queries.night_detail import NightDetail


class Failure(TypedDict):
    """What any method answers when it could not do its work."""

    ok: bool
    error: str


class Nothing(TypedDict):
    """Answer of an action that has nothing to report."""


class BootstrapAnswer(TypedDict):
    """What the page needs to start."""

    version: str
    language: str
    languages: list[str]
    theme: str
    texts: dict[str, str]
    available: DataPeriod
    night_metrics: list[str]
    relate_metrics: list[str]
    day_tracks: list[str]
    tags: list[Record]
    tracks: list[str]
    shown_tracks: list[str]
    sustained_low_min: int
    low_spo2_pct: int


class LanguageAnswer(TypedDict):
    """The language now in use, with its texts."""

    language: str
    texts: dict[str, str]


class ThemeAnswer(TypedDict):
    """The colour theme now in use."""

    theme: str


class TracksAnswer(TypedDict):
    """The tracks the "one night" screen now shows."""

    shown_tracks: list[str]


class NightAnswer(TypedDict):
    """One night; only ``found`` when there is no night on that date."""

    found: bool
    night: NotRequired[Record]
    tracks: NotRequired[dict[str, list[Record]]]
    low_spans: NotRequired[list[Record]]
    previous: NotRequired[str | None]
    next: NotRequired[str | None]
    tags: NotRequired[list[Record]]
    annotations: NotRequired[DayAnnotations]


class NightSide(NightDetail):
    """One of the two nights of a comparison, with what the user noted."""

    annotations: DayAnnotations


class CompareAnswer(TypedDict):
    """Two nights side by side, or the dates that have no night."""

    found: bool
    missing: NotRequired[list[str]]
    a: NotRequired[NightSide]
    b: NotRequired[NightSide]
    differences: NotRequired[Record]
    tags: NotRequired[list[Record]]


class DateAnswer(TypedDict):
    """What is noted on a date, and whether it has a night and a day to open."""

    has_night: bool
    has_day: bool
    tags: list[Record]
    annotations: DayAnnotations


class DayAnswer(TypedDict):
    """One day; only ``found`` when the day has no records."""

    found: bool
    day: NotRequired[Record]
    tracks: NotRequired[dict[str, list[Record]]]
    previous: NotRequired[str | None]
    next: NotRequired[str | None]
    tags: NotRequired[list[Record]]
    annotations: NotRequired[DayAnnotations]


class TagsAnswer(TypedDict):
    """Every tag, including the ones switched off."""

    tags: list[Record]


class AnnotationsAnswer(TypedDict):
    """What is noted on a date after a change."""

    annotations: DayAnnotations


class DashboardAnswer(TypedDict):
    """The figures of every view for one choice of filters."""

    overview: Record
    nights: list[Record]
    oxygen_weekdays: Record
    sleep_months: list[Record]
    hrv_trend: list[Record]
    pulse_trend: list[Record]
    hrv_weekdays: list[Record]
    pulse_weekdays: list[Record]
    activity_months: list[Record]
    hourly: Record
    notices: list[Record]


class WorstNightsAnswer(TypedDict):
    """The hardest nights for oxygen, ranked."""

    nights: list[Record]


class SavedAnswer(TypedDict):
    """Whether a file was saved; ``saved`` is false when the user cancelled."""

    saved: bool
    file_name: NotRequired[str]
    pages: NotRequired[int]


class ReportOptionsAnswer(TypedDict):
    """What the report form starts with."""

    profile: Profile
    watch_model: str


class ImportTotals(TypedDict):
    """Records of an import, by what the merge would do with them."""

    new: int
    updated: int
    unchanged: int
    kept: int
    superseded: int
    updated_old: int


class ImportTableRow(TypedDict):
    """What an import would do to one table."""

    table: str
    new: int
    updated: int
    unchanged: int
    kept: int
    superseded: int


class FailedDomain(TypedDict):
    """A group of tables that could not be read, and why."""

    domain: str
    reason: str


class CompatibilityFinding(TypedDict):
    """A difference between the export and the format the app expects."""

    table: str
    severity: str
    code: str
    detail: str


class ImportPreviewAnswer(TypedDict):
    """The preview of an import; only ``chosen`` when the user cancelled."""

    chosen: bool
    file_name: NotRequired[str]
    exported_at: NotRequired[str]
    samsung_app_version: NotRequired[str | None]
    first_date: NotRequired[str | None]
    last_date: NotRequired[str | None]
    is_older_export: NotRequired[bool]
    totals: NotRequired[ImportTotals]
    tables: NotRequired[list[ImportTableRow]]
    rejected: NotRequired[int]
    noticed: NotRequired[int]
    failed_domains: NotRequired[list[FailedDomain]]
    compatibility: NotRequired[list[CompatibilityFinding]]


class ImportStepAnswer(TypedDict):
    """The step a running import is on; empty when none is running."""

    step: str


class ImportDoneAnswer(TypedDict):
    """What a confirmed import changed."""

    import_id: int
    new_records: int
    updated_records: int
    new_nights: int
    new_days: int
    backup: str | None


class BackupRow(TypedDict):
    """A backup of the database that can be restored."""

    name: str
    size_bytes: int
    saved_at: str


class DatabasePanelAnswer(TypedDict):
    """The state of the database."""

    available: DataPeriod
    history: list[Record]
    tables: list[Record]
    issues: list[Record]
    version: str
    folder: str
    size_bytes: int
    last_import: str | None
    backups: list[BackupRow]


class RestoredAnswer(TypedDict):
    """The backup that replaced the database."""

    restored: str
