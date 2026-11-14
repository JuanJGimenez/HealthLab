"""Tests for the Samsung table contracts."""

from __future__ import annotations

from misalud.reading.contracts import ColumnContract, TableContract, load_contracts

ROLLING_WINDOW_TABLES = {
    "tracker.pedometer_step_count",
    "oxygen_saturation.raw",
    "sleep_raw_data",
    "insight_message",
}


def test_reference_export_has_59_tables() -> None:
    assert len(load_contracts()) == 59


def test_contracts_are_typed() -> None:
    contracts = load_contracts()
    sleep = contracts["sleep"]
    assert isinstance(sleep, TableContract)
    assert isinstance(sleep.columns["sleep_score"], ColumnContract)
    assert sleep.schema_version == 12
    assert sleep.key == "datauuid"
    assert sleep.time_column == "start_time"


def test_every_used_table_has_a_key_and_full_history() -> None:
    used = [contract for contract in load_contracts().values() if contract.is_used]
    assert len(used) == 20
    for contract in used:
        assert contract.key == "datauuid", contract.name
    windowed = {contract.name for contract in used if contract.rolling_window_days}
    # Minute-by-minute steps are fed from another table; this one is listed only as a source.
    assert windowed <= {"tracker.pedometer_step_count"}


def test_rolling_window_tables_are_flagged() -> None:
    flagged = {name for name, contract in load_contracts().items() if contract.rolling_window_days}
    assert flagged == ROLLING_WINDOW_TABLES


def test_detail_file_columns_are_recorded() -> None:
    contracts = load_contracts()
    assert "binning" in contracts["tracker.oxygen_saturation"].detail_file_columns
    assert "binning_data" in contracts["step_daily_trend"].detail_file_columns


def test_contracts_are_loaded_once() -> None:
    assert load_contracts() is load_contracts()
