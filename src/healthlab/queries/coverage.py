"""Tell when a screen is looking at dates a short-window table does not cover.

Samsung exports some tables with only the last weeks of data. The database keeps
what each import brought, so regular imports build the history; a period that
reaches further back than what is stored deserves a notice where that data is
shown. The contract of each Samsung table declares whether it has such a window.

No table HealthLab uses today has one. The mechanism is ready for the day one does.
"""

from __future__ import annotations

from collections.abc import Mapping

from healthlab.queries.common import ALL_TIME, Period, Record, records
from healthlab.reading.contracts import TableContract, load_contracts
from healthlab.storage.database import Connection
from healthlab.storage.schema import DETAIL_TABLES


def short_window_notices(
    connection: Connection,
    period: Period = ALL_TIME,
    contracts: Mapping[str, TableContract] | None = None,
) -> list[Record]:
    """Return a notice for each short-window table that does not cover the period.

    Args:
        connection: An open connection.
        period: Dates the screen is looking at.
        contracts: Contracts to read the windows from. Defaults to the shipped ones.

    Returns:
        One record per table with ``table``, ``window_days``, ``covered_from``
        and ``covered_to`` (``None`` for an empty table). A table appears when it
        is empty or when the period starts before its first stored date; a period
        without a start counts as starting before everything.
    """
    notices: list[Record] = []
    known = load_contracts() if contracts is None else contracts
    for contract in known.values():
        if contract.rolling_window_days is None:
            continue
        for name in contract.feeds:
            spec = DETAIL_TABLES.get(name)
            if spec is None:
                continue
            covered = records(
                connection,
                f"""SELECT CAST(min("{spec.time_column}") AS DATE) AS covered_from,
                    CAST(max("{spec.time_column}") AS DATE) AS covered_to FROM "{name}\"""",
            )[0]
            first = covered["covered_from"]
            if first is None or period.start is None or period.start.isoformat() < first:
                notices.append(
                    {"table": name, "window_days": contract.rolling_window_days, **covered}
                )
    return sorted(notices, key=lambda notice: str(notice["table"]))
