"""Ticker-prefix exclusion for the main (non-15m) auto-trader.

Used by whale / momentum / convergence trade gates. The 15-minute crypto
executor must never import or call this module — Multi-Run / KXBTC15M-style
markets are owned exclusively by crypto15m_trader.
"""
from __future__ import annotations

from typing import Any, Iterable, Optional


DEFAULT_EXCLUDED_MARKET_PREFIXES: list[str] = [
    "KXNBA",
    "KXNCAAMB",
    "KXBTCD",
    "KXBTC",
]


def normalize_excluded_prefixes(raw: Any) -> list[str]:
    """Coerce a config value to a clean, uppercased, de-duplicated prefix list.

    Empty / missing / non-list → []. Order of first occurrence is kept.
    """
    if not isinstance(raw, list):
        return []
    out: list[str] = []
    seen: set[str] = set()
    for item in raw:
        if not isinstance(item, str):
            continue
        p = item.strip().upper()
        if not p or p in seen:
            continue
        # Keep prefixes short and ticker-safe (Kalshi series are alnum).
        if len(p) > 64 or not all(ch.isalnum() or ch in "-_" for ch in p):
            continue
        seen.add(p)
        out.append(p)
        if len(out) >= 200:
            break
    return out


def _candidates(
    ticker: str,
    event_ticker: str = "",
    series_ticker: str = "",
) -> list[str]:
    vals: list[str] = []
    for v in (ticker, event_ticker, series_ticker):
        s = (v or "").strip().upper()
        if s and s not in vals:
            vals.append(s)
    # Series is conventionally the segment before the first '-'.
    if ticker:
        head = ticker.strip().upper().split("-", 1)[0]
        if head and head not in vals:
            vals.append(head)
    return vals


def matching_excluded_prefix(
    ticker: str,
    prefixes: Iterable[str],
    *,
    event_ticker: str = "",
    series_ticker: str = "",
) -> Optional[str]:
    """Return the matching exclusion prefix, or None if nothing matches.

    Matching is case-insensitive startswith against the market ticker and,
    when provided, the event/series tickers. An empty prefix list means no
    filtering. Longest matching prefix wins when several apply.
    """
    prefs = normalize_excluded_prefixes(list(prefixes) if not isinstance(prefixes, list) else prefixes)
    if not prefs:
        return None
    cands = _candidates(ticker, event_ticker, series_ticker)
    if not cands:
        return None
    best: Optional[str] = None
    for pref in prefs:
        for c in cands:
            if c.startswith(pref):
                if best is None or len(pref) > len(best):
                    best = pref
                break
    return best


def is_excluded_market(
    ticker: str,
    prefixes: Iterable[str],
    *,
    event_ticker: str = "",
    series_ticker: str = "",
) -> bool:
    return matching_excluded_prefix(
        ticker, prefixes, event_ticker=event_ticker, series_ticker=series_ticker,
    ) is not None


def exclusion_skip_reason(
    ticker: str,
    cfg: dict,
    *,
    event_ticker: str = "",
    series_ticker: str = "",
) -> Optional[str]:
    """Reason string for should_trade / logs, or None if the market is allowed."""
    pref = matching_excluded_prefix(
        ticker,
        cfg.get("excluded_market_prefixes") or [],
        event_ticker=event_ticker,
        series_ticker=series_ticker,
    )
    if pref is None:
        return None
    return f"skipped: excluded market prefix {pref}"
