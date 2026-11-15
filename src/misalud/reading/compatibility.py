"""Compare an export with the contracts and report every difference.

Samsung changes its export over time: it adds tables and columns, bumps schema
versions and may one day drop or rename something. This module turns those changes
into a report the user sees before any data is written (design decision 10).

The comparison looks at structure only: which tables and columns exist, their
schema versions and whether a column still holds the same kind of value. Checking
the values themselves is the job of the ``transform`` layer.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path
from typing import Final

import pandas as pd

from misalud.reading.contracts import TableContract, load_contracts
from misalud.reading.tables import TableFile, list_tables, read_table

NUMERIC_DTYPE_PREFIXES: Final = ("int", "float")


class ValueKind(StrEnum):
    """Kind of value a column holds."""

    NUMBER = "number"
    TEXT = "text"
    EMPTY = "empty"


class Severity(StrEnum):
    """How much a finding matters to the import."""

    INFO = "info"
    """Worth knowing; nothing is lost."""

    WARNING = "warning"
    """Data Samsung offers is being ignored, or a table changed version."""

    ERROR = "error"
    """A table or column MiSalud depends on is gone or changed kind."""


@dataclass(frozen=True, slots=True)
class Finding:
    """One difference between the export and the contracts.

    Attributes:
        table: Samsung table the finding is about.
        severity: How much it matters.
        code: Stable identifier of the kind of finding, for tests and translations.
        detail: The column name or the versions involved; empty when not needed.
    """

    table: str
    severity: Severity
    code: str
    detail: str = ""


@dataclass(frozen=True, slots=True)
class CompatibilityReport:
    """Result of comparing one export with the contracts.

    Attributes:
        app_versions: Samsung Health versions found on the metadata lines.
        tables_in_export: Number of table files in the export.
        findings: Every difference, in table order.
    """

    app_versions: tuple[str, ...]
    tables_in_export: int
    findings: tuple[Finding, ...] = field(default_factory=tuple)

    def by_severity(self, severity: Severity) -> tuple[Finding, ...]:
        """Return the findings of one severity."""
        return tuple(finding for finding in self.findings if finding.severity is severity)

    @property
    def errors(self) -> tuple[Finding, ...]:
        """Findings that stop a domain from being imported."""
        return self.by_severity(Severity.ERROR)

    @property
    def is_compatible(self) -> bool:
        """Tell whether every table MiSalud uses can be imported as designed."""
        return not self.errors

    def blocked_tables(self) -> frozenset[str]:
        """Return the Samsung tables that cannot be imported."""
        return frozenset(finding.table for finding in self.errors)


def kind_of_dtype(dtype: str) -> ValueKind:
    """Classify a data type recorded in a contract.

    Args:
        dtype: Data type name as stored in ``contracts.json``.

    Returns:
        ``NUMBER`` for integer and float types; ``TEXT`` otherwise. Booleans count
        as text because Samsung writes them as ``True`` and ``False``.
    """
    return ValueKind.NUMBER if dtype.startswith(NUMERIC_DTYPE_PREFIXES) else ValueKind.TEXT


def kind_of_values(values: pd.Series[str]) -> ValueKind:
    """Classify the values of a column read as text.

    Args:
        values: One column of a table, as text with missing values.

    Returns:
        ``EMPTY`` when no cell has a value, ``NUMBER`` when every value parses as
        a number, ``TEXT`` otherwise.
    """
    present = values.dropna()
    if present.empty:
        return ValueKind.EMPTY
    as_numbers = pd.to_numeric(present, errors="coerce")
    return ValueKind.NUMBER if bool(as_numbers.notna().all()) else ValueKind.TEXT


def _compare_table(table: TableFile, contract: TableContract) -> list[Finding]:
    """Compare one table file with its contract.

    Args:
        table: Table found in the export.
        contract: What the importer expects from that table.

    Returns:
        The differences found, possibly none.
    """
    findings: list[Finding] = []
    used = contract.is_used
    if table.schema_version != contract.schema_version:
        detail = f"{contract.schema_version} -> {table.schema_version}"
        severity = Severity.WARNING if used else Severity.INFO
        findings.append(Finding(table.name, severity, "schema_version_changed", detail))

    frame = read_table(table)
    present = set(frame.columns)
    expected = set(contract.columns)
    for column in sorted(expected - present):
        is_key = column in (contract.key, contract.time_column)
        severity = (
            Severity.ERROR if used and is_key else Severity.WARNING if used else Severity.INFO
        )
        findings.append(Finding(table.name, severity, "column_missing", column))
    for column in sorted(present - expected):
        severity = Severity.WARNING if used else Severity.INFO
        findings.append(Finding(table.name, severity, "column_unknown", column))
    for column in sorted(present & expected):
        recorded_column = contract.columns[column]
        if recorded_column.filled_pct == 0:
            # The reference export had no value here, so its type says nothing.
            continue
        observed = kind_of_values(frame[column])
        recorded = kind_of_dtype(recorded_column.dtype)
        # A number stored where text is expected is harmless: text can hold digits.
        if observed is ValueKind.TEXT and recorded is ValueKind.NUMBER:
            severity = Severity.ERROR if used else Severity.INFO
            findings.append(Finding(table.name, severity, "column_kind_changed", column))
    return findings


def compare_with_contracts(
    export_root: Path, contracts: dict[str, TableContract] | None = None
) -> CompatibilityReport:
    """Compare every table of an export with the contracts.

    Severity rules:

    * A table or key column MiSalud uses that is missing, or a used column that
      turned from numbers into text, is an ``ERROR``: that table is not imported.
    * Any other change in a used table is a ``WARNING``.
    * Changes in tables MiSalud does not use are ``INFO``.

    The contracts list every column Samsung writes, not only the ones MiSalud
    reads. Whether a missing non-key column stops a domain is decided by the
    ``transform`` layer, which knows the columns each domain needs.

    Args:
        export_root: Folder that directly holds the table files.
        contracts: Contracts to compare against. Defaults to the ones shipped with
            the package.

    Returns:
        The report with every finding, ordered by table name.
    """
    expected = load_contracts() if contracts is None else contracts
    tables = list_tables(export_root)
    findings: list[Finding] = []
    for name in sorted(set(expected) | set(tables)):
        contract = expected.get(name)
        table = tables.get(name)
        if contract is None:
            findings.append(Finding(name, Severity.WARNING, "table_unknown"))
        elif table is None:
            severity = Severity.ERROR if contract.is_used else Severity.INFO
            findings.append(Finding(name, severity, "table_missing"))
        else:
            findings.extend(_compare_table(table, contract))
    versions = tuple(sorted({table.app_version for table in tables.values()}))
    return CompatibilityReport(versions, len(tables), tuple(findings))
