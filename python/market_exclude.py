"""Ticker-prefix exclusion for the main (non-15m) auto-trader and AI paths.

Used by whale / momentum / convergence trade gates, panel AI Analyse, Autopilot
and MCP discover/search/forecast/place. The 15-minute crypto *executor*
(crypto15m_trader) must never import or call this module — Multi-Run /
KXBTC15M-style markets are owned exclusively by that runner. Autopilot/MCP
still hide KXBTC* (including 15m series) when KXBTC is on the denylist, so
Claude is not spent analysing markets the user asked to skip.
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

    Empty / missing / non-list → []. Blank strings and whitespace-only entries
    are dropped (never become '' — startswith('') would match every ticker).
    Order of first occurrence is kept.
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


def prefixes_from_cfg(cfg: Optional[dict]) -> list[str]:
    if not isinstance(cfg, dict):
        return []
    return normalize_excluded_prefixes(cfg.get("excluded_market_prefixes") or [])


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
    prefs = normalize_excluded_prefixes(
        list(prefixes) if not isinstance(prefixes, list) else prefixes,
    )
    if not prefs:
        return None
    cands = _candidates(ticker, event_ticker, series_ticker)
    if not cands:
        return None
    best: Optional[str] = None
    for pref in prefs:
        # Defensive: never treat an empty prefix as a match-all.
        if not pref:
            continue
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
    """Reason string for should_trade / logs / AI refuse, or None if allowed."""
    pref = matching_excluded_prefix(
        ticker,
        prefixes_from_cfg(cfg),
        event_ticker=event_ticker,
        series_ticker=series_ticker,
    )
    if pref is None:
        return None
    return f"skipped: excluded market prefix {pref}"


def row_tickers(row: Optional[dict]) -> tuple[str, str, str]:
    """Pull (ticker, event, series) from a terminal/MCP market row or detail."""
    if not isinstance(row, dict):
        return "", "", ""
    # market_detail nests under "market"; flat rows use top-level keys.
    m = row.get("market") if isinstance(row.get("market"), dict) else row
    ticker = str(m.get("ticker") or row.get("ticker") or "")
    event = str(
        m.get("eventTicker") or m.get("event_ticker")
        or row.get("eventTicker") or row.get("event_ticker") or ""
    )
    series = str(
        m.get("seriesTicker") or m.get("series_ticker")
        or row.get("seriesTicker") or row.get("series_ticker") or ""
    )
    return ticker, event, series


def exclusion_skip_reason_for_row(row: Optional[dict], cfg: dict) -> Optional[str]:
    ticker, event, series = row_tickers(row)
    return exclusion_skip_reason(
        ticker, cfg, event_ticker=event, series_ticker=series,
    )


def drop_excluded_rows(
    rows: Iterable[dict],
    cfg: dict,
) -> tuple[list[dict], int]:
    """Filter market rows; return (kept, n_dropped)."""
    prefs = prefixes_from_cfg(cfg)
    if not prefs:
        kept = [r for r in rows if isinstance(r, dict)]
        return kept, 0
    kept: list[dict] = []
    dropped = 0
    for r in rows:
        if not isinstance(r, dict):
            continue
        if exclusion_skip_reason_for_row(r, cfg):
            dropped += 1
            continue
        kept.append(r)
    return kept, dropped


def exclusion_prompt_note(cfg: dict) -> str:
    """Short instruction block for Autopilot / MCP system prompts."""
    prefs = prefixes_from_cfg(cfg)
    if not prefs:
        return ""
    joined = ", ".join(prefs)
    return (
        f"\nEXCLUDED MARKET PREFIXES (hard rule — do not analyse, forecast, or "
        f"trade these): {joined}. discover_markets / search_markets already "
        f"omit them; get_market / record_forecast / place_order refuse them. "
        f"Spend your steps on other markets.\n"
    )
