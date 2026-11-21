"""Paper whale path: why zero placed trades is often filter math, not Paper mode.

Pinned from the Nov 19–21 paper-account log investigation:

  * Factory reset wipes whale_trades / positions / autopilot_runs — not settings.
  * Default min_whale_usd is $2500 and min_edge_pts_whale is 5.0 (upstream same).
  * Net edge = confidence − implied − taker fee (when fee_aware_edge).
  * KXMVE* parlays must not become whale candidates (micro-market filter).
  * A whale that clears the scanner still dies in should_trade when net edge
    is below the user's min (e.g. 5.2 < 6.5) — Paper mode is not the reject.
"""
from __future__ import annotations

import pytest

import db
import trader
from categorize import is_micro_market
from config import DEFAULT_CONFIG, merge_with_defaults


@pytest.fixture
def fresh_db(tmp_path, monkeypatch):
    dbfile = tmp_path / "paper-whale.db"
    monkeypatch.setattr(db, "db_path", lambda: dbfile)
    db.init_db()
    return dbfile


def test_factory_reset_wipes_whale_rows_not_config(fresh_db):
    with db.get_db() as conn:
        db.insert_whale_trade(conn, {
            "trade_id": "w1", "ticker": "KXTEST-A", "count_fp": 100,
            "price": 0.6, "dollar_value": 60, "taker_side": "yes",
            "event_ticker": "", "title": "", "yes_sub_title": "",
            "category": "", "market_volume": 0, "open_interest": 0,
            "confidence": 60,
        })
    summary = db.factory_reset()
    assert summary.get("whale_trades", 0) >= 1
    with db.get_db() as conn:
        assert conn.execute("SELECT COUNT(*) FROM whale_trades").fetchone()[0] == 0
    # Settings live outside the DB; defaults stay available after a wipe.
    cfg = merge_with_defaults({})
    assert cfg["min_whale_usd"] == 2500.0
    assert cfg["min_edge_pts_whale"] == 5.0
    assert cfg["excluded_market_prefixes"]  # denylist still present


def test_defaults_match_upstream_edge_and_whale_floor():
    """Do not loosen these in sky releases — report them; user tunes in Settings."""
    assert DEFAULT_CONFIG["min_whale_usd"] == 2500.0
    assert DEFAULT_CONFIG["min_entry_price_frac"] == 0.50
    assert DEFAULT_CONFIG["min_edge_pts_whale"] == 5.0
    assert DEFAULT_CONFIG["min_edge_pts_momentum"] == 5.0
    assert DEFAULT_CONFIG["fee_aware_edge"] is True
    assert DEFAULT_CONFIG["max_trade_age_min"] == 15


def test_kxmve_parlays_are_not_whale_candidates():
    assert is_micro_market("KXMVECROSSCATEGORY-XYZ")
    assert is_micro_market("KXMVE-FOO")
    assert not is_micro_market("KXATPCHALLENGERMATCH-KWON")
    assert not is_micro_market("KXNBA-GAME")


def test_net_edge_reject_matches_log_shape():
    """User log: '[filter] … whale: net edge 5.2 < 6.5' — Paper is irrelevant."""
    cfg = merge_with_defaults({
        "account_mode": "paper",
        "enable_trading": True,
        "trade_whales": True,
        "min_edge_pts_whale": 6.5,
        "min_confidence_whale": 55.0,
        "excluded_market_prefixes": [],
        "fee_aware_edge": True,
    })
    # confidence 62, price 0.55 → gross edge 7; fee at ~55c ≈ 1.73 → net ≈ 5.27
    signal = {
        "ticker": "KXATPCHALLENGERMATCH-KWON",
        "confidence": 62.0,
        "price": 0.55,
        "direction": "yes",
    }
    ok, reason = trader.should_trade(signal, "whale", cfg)
    assert ok is False
    assert "net edge" in reason
    assert "< 6.5" in reason
    net = trader._net_edge(signal, "whale", cfg)
    assert 5.0 <= net < 6.5


def test_same_signal_passes_at_default_min_edge():
    cfg = merge_with_defaults({
        "account_mode": "paper",
        "enable_trading": True,
        "trade_whales": True,
        "min_confidence_whale": 55.0,
        "excluded_market_prefixes": [],
    })
    assert cfg["min_edge_pts_whale"] == 5.0
    signal = {
        "ticker": "KXATPCHALLENGERMATCH-KWON",
        "confidence": 62.0,
        "price": 0.55,
        "direction": "yes",
    }
    ok, reason = trader.should_trade(signal, "whale", cfg)
    assert ok is True, reason
