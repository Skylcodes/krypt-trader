"""Excluded-market prefix filter for the main (non-15m) auto-trader."""
from __future__ import annotations

import inspect

import pytest

import crypto15m_trader
import market_exclude
import trader
from config import merge_with_defaults


@pytest.fixture
def cfg() -> dict:
    return merge_with_defaults({})


def test_default_list_present_for_existing_users(cfg):
    """A settings file that never saved the new key still gets the defaults."""
    assert cfg["excluded_market_prefixes"] == [
        "KXNBA", "KXNCAAMB", "KXBTCD", "KXBTC",
    ]


def test_prefix_match_on_ticker():
    assert market_exclude.matching_excluded_prefix(
        "KXNBA-26JAN15-BOS", ["KXNBA"],
    ) == "KXNBA"
    assert market_exclude.is_excluded_market("KXNCAAMB-FOO", ["KXNCAAMB"])


def test_prefix_match_case_insensitive():
    assert market_exclude.matching_excluded_prefix(
        "kxnba-26jan15-bos", ["kxnba"],
    ) == "KXNBA"
    assert market_exclude.matching_excluded_prefix(
        "KXNBA-26JAN15-BOS", ["kxNba"],
    ) == "KXNBA"


def test_prefix_match_on_event_and_series_tickers():
    assert market_exclude.matching_excluded_prefix(
        "LEG-1", ["KXNBA"], event_ticker="KXNBA-26JAN15",
    ) == "KXNBA"
    assert market_exclude.matching_excluded_prefix(
        "LEG-1", ["KXBTCD"], series_ticker="KXBTCD",
    ) == "KXBTCD"


def test_empty_list_means_no_filtering():
    assert market_exclude.matching_excluded_prefix("KXNBA-1", []) is None
    assert market_exclude.is_excluded_market("KXNBA-1", []) is False


def test_longest_prefix_wins():
    assert market_exclude.matching_excluded_prefix(
        "KXBTCD-26JUN1400", ["KXBTC", "KXBTCD"],
    ) == "KXBTCD"


def test_should_trade_skips_excluded_and_logs_reason(cfg):
    cfg["excluded_market_prefixes"] = ["KXNBA"]
    ok, why = trader.should_trade(
        {"ticker": "KXNBA-26JAN15-BOS", "price": 0.60, "confidence": 90.0,
         "taker_side": "yes", "category": "sports"},
        "whale", cfg,
    )
    assert ok is False
    assert why == "skipped: excluded market prefix KXNBA"


def test_should_trade_allows_when_list_empty(cfg):
    cfg["excluded_market_prefixes"] = []
    ok, why = trader.should_trade(
        {"ticker": "KXNBA-26JAN15-BOS", "price": 0.60, "confidence": 90.0,
         "taker_side": "yes", "category": "sports"},
        "whale", cfg,
    )
    assert ok is True and why == "ok"


def test_should_trade_momentum_also_filtered(cfg):
    cfg["excluded_market_prefixes"] = ["KXBTC"]
    cfg["allowed_momentum_signal_types"] = ["trade_cluster"]
    ok, why = trader.should_trade(
        {"ticker": "KXBTC-26JUN30", "price": 0.40, "confidence": 90.0,
         "direction": "yes", "signal_type": "trade_cluster", "category": "crypto"},
        "momentum", cfg,
    )
    assert ok is False
    assert "excluded market prefix KXBTC" in why


def test_crypto15m_series_still_owned_by_15m_executor_not_exclusion(cfg):
    """15m tickers hit the dedicated early return, not the exclusion list —
    even when KXBTC is excluded (which would otherwise prefix-match KXBTC15M)."""
    cfg["excluded_market_prefixes"] = ["KXBTC", "KXNBA"]
    ok, why = trader.should_trade(
        {"ticker": "KXBTC15M-26JUL011500", "price": 0.80, "confidence": 90.0,
         "taker_side": "yes"},
        "whale", cfg,
    )
    assert ok is False
    assert "crypto15m" in why
    assert "excluded" not in why


def test_crypto15m_trader_never_consults_exclusion_list():
    src = inspect.getsource(crypto15m_trader)
    assert "market_exclude" not in src
    assert "excluded_market_prefixes" not in src
    assert "excludedMarketPrefixes" not in src


def test_normalize_rejects_junk_and_dedupes():
    assert market_exclude.normalize_excluded_prefixes(
        [" kxnba ", "KXNBA", "", None, "bad prefix!", "KX_OK"],
    ) == ["KXNBA", "KX_OK"]


def test_merge_with_defaults_applies_default_list_when_absent():
    out = merge_with_defaults({"minWhaleUsd": 3000})
    assert out["excluded_market_prefixes"] == list(
        market_exclude.DEFAULT_EXCLUDED_MARKET_PREFIXES,
    )


def test_merge_respects_explicit_empty_list():
    out = merge_with_defaults({"excludedMarketPrefixes": []})
    assert out["excluded_market_prefixes"] == []
