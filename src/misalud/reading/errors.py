"""Errors raised while reading a Samsung Health export."""

from __future__ import annotations


class ReadingError(Exception):
    """Base class for every problem found while reading an export."""


class ExportNotFoundError(ReadingError):
    """The archive or folder does not contain a Samsung Health export."""


class UnsafeArchiveError(ReadingError):
    """The archive holds an entry that would be written outside the target folder."""


class TableFormatError(ReadingError):
    """A CSV file does not follow the layout of a Samsung Health table."""


class DetailFileError(ReadingError):
    """A detail file referenced from a table is missing or cannot be parsed."""
