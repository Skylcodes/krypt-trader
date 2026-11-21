"""Excluded-market prefix filter for the main (non-15m) auto-trader and AI paths."""
from __future__ import annotations

import asyncio
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


def test_whitespace_and_blank_entries_never_become_match_all():
    """startswith('') matches every string — blanks must be dropped."""
    assert market_exclude.normalize_excluded_prefixes(
        ["", "  ", "\t", "\n", None, "KXNBA"],
    ) == ["KXNBA"]
    assert market_exclude.matching_excluded_prefix(
        "KXOTHER-1", ["", "  ", "\n"],
    ) is None
    assert market_exclude.matching_excluded_prefix(
        "ANYTHING", ["", ""],
    ) is None


def test_kxbtc_prefix_matches_btc_series_but_not_unrelated():
    prefs = ["KXBTC"]
    assert market_exclude.matching_excluded_prefix("KXBTC-26JUN30", prefs) == "KXBTC"
    assert market_exclude.matching_excluded_prefix("KXBTCD-1", prefs) == "KXBTC"
    assert market_exclude.matching_excluded_prefix("KXBTC15M-1", prefs) == "KXBTC"
    assert market_exclude.matching_excluded_prefix("KXETH-1", prefs) is None
    assert market_exclude.matching_excluded_prefix("KXNBA-1", prefs) is None


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


def test_drop_excluded_rows():
    cfg = {"excluded_market_prefixes": ["KXNBA", "KXBTC"]}
    rows = [
        {"ticker": "KXNBA-1", "title": "nba"},
        {"ticker": "KXETH-1", "title": "eth"},
        {"ticker": "KXBTC-1", "title": "btc"},
        {"ticker": "KXOTHER-1", "seriesTicker": "KXNBA"},
    ]
    kept, dropped = market_exclude.drop_excluded_rows(rows, cfg)
    assert dropped == 3
    assert [r["ticker"] for r in kept] == ["KXETH-1"]


def test_panel_ai_analyze_does_not_call_llm_on_excluded(monkeypatch, cfg):
    """No Anthropic/OpenAI spend when the ticker matches Excluded markets."""
    import ai_analyst
    import service
    import terminal

    cfg["excluded_market_prefixes"] = ["KXNBA"]
    called = {"analyze": 0, "detail": 0}

    async def _detail(ticker, *, authed=False):
        called["detail"] += 1
        return {"market": {"ticker": ticker}}

    def _analyze(detail, c):
        called["analyze"] += 1
        return {"fairValueCents": 50, "model": "x", "summary": "nope"}

    monkeypatch.setattr(terminal, "market_detail", _detail)
    monkeypatch.setattr(ai_analyst, "analyze", _analyze)
    monkeypatch.setattr(service.STATE, "cfg", cfg)
    monkeypatch.setattr(service.STATE, "auth_ok", False)

    res = asyncio.run(service._h_ai_analyze({"ticker": "KXNBA-26JAN15-BOS"}))
    assert res["ok"] is False
    assert res.get("excluded") is True
    assert "Excluded markets" in res["error"]
    assert called["analyze"] == 0
    assert called["detail"] == 0  # refused before Kalshi fetch too


def test_panel_ai_analyze_still_runs_for_allowed(monkeypatch, cfg):
    import ai_analyst
    import service
    import terminal

    cfg["excluded_market_prefixes"] = ["KXNBA"]
    called = {"analyze": 0}

    async def _detail(ticker, *, authed=False):
        return {"market": {"ticker": ticker, "midCents": 50}}

    def _analyze(detail, c):
        called["analyze"] += 1
        return {"fairValueCents": None, "model": "m", "summary": "ok", "verdict": "unclear"}

    monkeypatch.setattr(terminal, "market_detail", _detail)
    monkeypatch.setattr(ai_analyst, "analyze", _analyze)
    monkeypatch.setattr(service.STATE, "cfg", cfg)
    monkeypatch.setattr(service.STATE, "auth_ok", False)

    res = asyncio.run(service._h_ai_analyze({"ticker": "KXETH-26JUN30"}))
    assert res["ok"] is True
    assert called["analyze"] == 1


def test_mcp_discover_strips_excluded(monkeypatch, cfg):
    import mcp_server
    import terminal

    cfg["excluded_market_prefixes"] = ["KXNBA"]

    async def _discover(column, limit=25):
        return {"note": "", "rows": [
            {"ticker": "KXNBA-1", "title": "nba", "category": "Sports"},
            {"ticker": "KXETH-1", "title": "eth", "category": "Crypto"},
        ]}

    monkeypatch.setattr(terminal, "discover", _discover)
    monkeypatch.setattr(mcp_server.HOOKS, "get_cfg", lambda: cfg)
    out = asyncio.run(mcp_server.t_discover({"column": "trending", "limit": 25}, {}))
    tickers = [m["ticker"] for m in out["markets"]]
    assert tickers == ["KXETH-1"]
    assert "excluded" in (out.get("note") or "").lower()


def test_mcp_vet_blocks_buy_on_excluded(monkeypatch, cfg):
    import mcp_server

    cfg["excluded_market_prefixes"] = ["KXNBA"]
    cfg["mcp_trade_mode"] = "paper"

    async def _row(ticker):
        return {"ticker": ticker, "status": "active", "category": "Sports",
                "yesBid": 40, "yesAsk": 45}

    monkeypatch.setattr(mcp_server, "_market_row", _row)
    v = asyncio.run(mcp_server.vet(
        {"ticker": "KXNBA-1", "side": "yes", "action": "buy",
         "count": 1, "price_cents": 45},
        cfg, "paper",
    ))
    assert v.blockers
    assert any("Excluded markets" in b for b in v.blockers)


def test_mcp_forecast_refuses_excluded(monkeypatch, cfg):
    import mcp_server

    cfg["excluded_market_prefixes"] = ["KXBTC"]
    monkeypatch.setattr(mcp_server.HOOKS, "get_cfg", lambda: cfg)

    with pytest.raises(mcp_server.ToolError, match="Excluded markets"):
        asyncio.run(mcp_server.t_forecast({
            "ticker": "KXBTC-26JUN30",
            "fair_value_cents": 55,
            "rationale": "A long enough rationale for the gate to accept length.",
        }, {"agent": "default"}))


def test_exclusion_prompt_note_lists_prefixes(cfg):
    note = market_exclude.exclusion_prompt_note(cfg)
    assert "KXNBA" in note and "KXBTC" in note
    assert market_exclude.exclusion_prompt_note({"excluded_market_prefixes": []}) == ""
