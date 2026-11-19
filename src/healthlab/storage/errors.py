"""Errors raised by the storage layer."""

from __future__ import annotations


class StorageError(Exception):
    """Base class for every problem found while working with the database."""


class SchemaVersionError(StorageError):
    """The database was made by a newer HealthLab than the one running."""


class MergeError(StorageError):
    """Incoming data cannot be merged: unknown table, wrong columns or a broken key."""
