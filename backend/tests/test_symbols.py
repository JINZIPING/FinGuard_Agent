from __future__ import annotations

from app.symbols import DEFAULT_SYMBOLS, STOCK_SYMBOLS, get_all_symbols, get_symbols_by_sector


def test_get_all_symbols_returns_sorted_flat_catalog():
    symbols = get_all_symbols()

    assert symbols
    assert [item["symbol"] for item in symbols] == sorted(
        item["symbol"] for item in symbols
    )
    assert {"symbol": "AAPL", "name": "Apple Inc.", "sector": "Technology"} in symbols


def test_default_symbols_are_present_in_catalog():
    all_symbols = {item["symbol"] for item in get_all_symbols()}

    assert set(DEFAULT_SYMBOLS).issubset(all_symbols)


def test_get_symbols_by_sector_returns_sector_catalog():
    sectors = get_symbols_by_sector()

    assert sectors is STOCK_SYMBOLS
    assert "technology" in sectors
    assert all(item["sector"] == "Technology" for item in sectors["technology"])
