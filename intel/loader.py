# The purpose of the module is to provide a data layer for my bot
# It outputs clean, structured data that other modules can use
# returns an IntelBundle that consists of
# symbol: uppercase ticker symbol
# quote: prev_close, high, low, volume, asof (datetime of prev bar).
# bars: OHLCV
# News: A list of NewsItem that contains headline and clickable url
# It can request a bundle of data of any requested time frame

# to use this loader

"""
intel.loader
============

Async client for Polygon.io focused on **loading market data** (quotes, bars, news).
This package does NOT calculate indicators or charts — keep it decoupled.
Other packages (e.g. `charts/`, `indicators/`) can build on top of this.

Usage
-----

1. Initialize the client (requires POLYGON_API_KEY in your .env):
    >>> from intel.loader import PolygonClient
    >>> import asyncio
    >>> async def main():
    ...     pg = PolygonClient()
    ...     bundle = await pg.bundle("AAPL", bars_timespan="day", bars_lookback=30)
    ...     print(bundle.quote.prevClose, len(bundle.bars), len(bundle.news))
    ...     await pg.aclose()
    >>> asyncio.run(main())

2. Or call methods individually:
    - `await pg.prev_close("AAPL")` → dict with yesterday's OHLC + volume
    - `await pg.aggregates("AAPL", 1, "day", "2024-01-01", "2024-03-01")`
         → list of OHLCV bars for the given date range
    - `await pg.news("AAPL", limit=5)` → list of NewsItem dataclasses
    - `await pg.bundle("AAPL", bars_timespan="week", bars_lookback=52)`
         → IntelBundle with Quote, Bars, News

3. What you get back:
    - `Quote`: prevClose, high, low, volume, as_of timestamp
    - `Bar`:   t (ms), o, h, l, c, v (candlestick data)
    - `NewsItem`: publisher, title, url, published_at
    - `IntelBundle`: wrapper holding all of the above

Notes
-----
- Always `await pg.aclose()` when done to close the HTTP session.
- Timespans supported: "minute", "hour", "day", "week", "month".
- For charting or indicators, use a separate package (e.g. `charts/`).
"""

from __future__ import annotations

import asyncio
from typing import Any, Dict, List, Optional, Protocol, Tuple
from datetime import datetime, timedelta, timezone

import httpx

from config import settings
from .contract import Quote, Bar, NewsItem, Dividend, Split, Earnings, IntelBundle

# -----------------------------------------------------------------------------
# Config
# -----------------------------------------------------------------------------
_BASE = "https://api.polygon.io"
_API_KEY = settings.POLYGON_API_KEY


# -----------------------------------------------------------------------------
# Helpers
# -----------------------------------------------------------------------------
def _parse_iso_utc(s: Optional[str]) -> Optional[datetime]:
    if not s:
        return None
    s = s.strip()
    if s.endswith("Z"):
        s = s[:-1] + "+00:00"
    try:
        dt = datetime.fromisoformat(s)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except Exception:
        return None

def _epoch_ms_to_utc(ms: Optional[int]) -> Optional[datetime]:
    if ms is None:
        return None
    return datetime.fromtimestamp(ms / 1000, tz=timezone.utc)


async def _request_with_retry(
    http: httpx.AsyncClient,
    method: str,
    url: str,
    *,
    params: Dict[str, Any] | None = None,
    max_retries: int = 3,
) -> httpx.Response:
    tries = 0
    params = dict(params or {})
    if "apiKey" not in params:
        params["apiKey"] = _API_KEY

    while True:
        r = await http.request(method, url, params=params)
        if r.status_code in (401, 403):
            raise RuntimeError(f"Polygon auth/permission error {r.status_code}: {r.text}")

        if r.status_code == 429:
            tries += 1
            if tries > max_retries:
                raise RuntimeError("Polygon rate limited (429) after retries.")
            retry_after = float(r.headers.get("Retry-After", tries * 1.5))
            await asyncio.sleep(retry_after)
            continue

        if r.status_code >= 500:
            tries += 1
            if tries > max_retries:
                r.raise_for_status()
            await asyncio.sleep(1.0 * tries)
            continue

        r.raise_for_status()
        return r


# -----------------------------------------------------------------------------
# Ports (interfaces)
# -----------------------------------------------------------------------------
class EventsPort(Protocol):
    async def dividends(self, symbol: str, *, limit: int = 50) -> List[Dividend]: ...
    async def splits(self, symbol: str, *, limit: int = 50) -> List[Split]: ...
    async def earnings(self, symbol: str, *, limit: int = 12) -> List[Earnings]: ...


# -----------------------------------------------------------------------------
# Polygon events adapter (optional, for dividends/splits via Polygon)
# -----------------------------------------------------------------------------
class PolygonEventsProvider(EventsPort):
    def __init__(self, http: httpx.AsyncClient, *, base: str = "https://api.polygon.io"):
        self.http = http
        self.base = base

    async def dividends(self, symbol: str, *, limit: int = 50) -> List[Dividend]:
        url = f"{self.base}/v3/reference/dividends"
        out: List[Dividend] = []
        cursor: Optional[str] = None

        while True:
            params = {"ticker": symbol.upper(), "limit": min(limit, 1000)}
            if cursor:
                # Polygon supports next_page via "cursor" in some SDKs, or next_url/next in JSON.
                # To stay robust, just add "cursor" if we have one.
                params["cursor"] = cursor
            r = await _request_with_retry(self.http, "GET", url, params=params)
            j = r.json()

            for d in j.get("results", []):
                out.append(
                    Dividend(
                        cash_amount=float(d.get("cash_amount", 0.0)),
                        declaration_date=_parse_iso_utc(d.get("declaration_date")),
                        ex_dividend_date=_parse_iso_utc(d.get("ex_dividend_date")),
                        payment_date=_parse_iso_utc(d.get("pay_date")),
                        record_date=_parse_iso_utc(d.get("record_date")),
                        frequency=d.get("frequency"),
                    )
                )

            cursor = j.get("next_url") or j.get("next_url_cursor") or j.get("next")
            if not cursor or len(out) >= limit:
                break

        return out[:limit]

    async def splits(self, symbol: str, *, limit: int = 50) -> List[Split]:
        url = f"{self.base}/v3/reference/splits"
        out: List[Split] = []
        cursor: Optional[str] = None

        while True:
            params = {"ticker": symbol.upper(), "limit": min(limit, 1000)}
            if cursor:
                params["cursor"] = cursor
            r = await _request_with_retry(self.http, "GET", url, params=params)
            j = r.json()

            for s in j.get("results", []):
                ratio = None
                if s.get("split_from") and s.get("split_to"):
                    ratio = f"{s.get('split_from')}/{s.get('split_to')}"
                else:
                    ratio = s.get("ratio") or "1/1"
                out.append(
                    Split(
                        ratio=ratio,
                        execution_date=_parse_iso_utc(s.get("execution_date")),
                    )
                )

            cursor = j.get("next_url") or j.get("next_url_cursor") or j.get("next")
            if not cursor or len(out) >= limit:
                break

        return out[:limit]

    async def earnings(self, symbol: str, *, limit: int = 12) -> List[Earnings]:
        # Polygon’s earnings endpoints/coverage vary; keep empty so you can combine with another provider.
        return []


# -----------------------------------------------------------------------------
# YFinance events adapter (preferred here; no API key)
# -----------------------------------------------------------------------------
# This provider calls yfinance’s synchronous API from threads so your bot stays async.
class YFinanceEventsProvider(EventsPort):
    def __init__(self):
        import yfinance as yf
        self.yf = yf

    async def dividends(self, symbol: str, *, limit: int = 50) -> List[Dividend]:
        def _fetch() -> List[Dividend]:
            tkr = self.yf.Ticker(symbol)
            s = getattr(tkr, "dividends", None)
            if s is None or getattr(s, "empty", True):
                return []
            out: List[Dividend] = []
            # last N rows only
            for dt, cash in list(s.items())[-limit:]:
                ts = dt.to_pydatetime()
                if ts.tzinfo is None:
                    ts = ts.replace(tzinfo=timezone.utc)
                out.append(
                    Dividend(
                        cash_amount=float(cash) if cash is not None else 0.0,
                        declaration_date=None,
                        ex_dividend_date=ts,   # yfinance exposes payout date-like series; treat as best-effort ex/pay marker
                        payment_date=None,
                        record_date=None,
                        frequency=None,
                    )
                )
            return out
        return await asyncio.to_thread(_fetch)

    async def splits(self, symbol: str, *, limit: int = 50) -> List[Split]:
        def _format_ratio(x: Optional[float]) -> str:
            if x is None:
                return "1/1"
            try:
                r = float(x)
            except Exception:
                return str(x)
            # r >= 1 -> "r/1" (e.g., 4.0 -> "4/1")
            if r >= 1:
                return f"{int(r)}/1" if r.is_integer() else f"{r}/1"
            # r < 1 -> "1/k" if invertible to clean int, else keep decimal
            inv = 1.0 / r
            return f"1/{int(inv)}" if inv.is_integer() else f"1/{inv}"

        def _fetch() -> List[Split]:
            tkr = self.yf.Ticker(symbol)
            s = getattr(tkr, "splits", None)
            if s is None or getattr(s, "empty", True):
                return []
            out: List[Split] = []
            for dt, ratio in list(s.items())[-limit:]:
                ts = dt.to_pydatetime()
                if ts.tzinfo is None:
                    ts = ts.replace(tzinfo=timezone.utc)
                out.append(Split(ratio=_format_ratio(ratio), execution_date=ts))
            return out
        return await asyncio.to_thread(_fetch)

    async def earnings(self, symbol: str, *, limit: int = 12) -> List[Earnings]:
        def _fetch() -> List[Earnings]:
            tkr = self.yf.Ticker(symbol)
            try:
                df = tkr.get_earnings_dates(limit=limit)
            except Exception:
                df = None
            if df is None or df.empty:
                return []

            out: List[Earnings] = []
            rows = df.reset_index().to_dict("records")
            for row in rows[:limit]:
                dt = row.get("Earnings Date") or row.get("Date") or row.get("index")
                rpt = None
                if hasattr(dt, "to_pydatetime"):
                    rpt = dt.to_pydatetime()
                elif isinstance(dt, datetime):
                    rpt = dt
                if rpt is not None and rpt.tzinfo is None:
                    rpt = rpt.replace(tzinfo=timezone.utc)

                # column names vary by yfinance version — be defensive
                eps_act = row.get("Reported EPS") or row.get("EPS Actual") or row.get("ReportedEPS")
                eps_est = row.get("EPS Estimate") or row.get("EPS Est.") or row.get("EPSEstimate")
                eps = float(eps_act) if eps_act is not None else None
                consensus = float(eps_est) if eps_est is not None else None
                surprise_abs = (eps - consensus) if (eps is not None and consensus is not None) else None

                out.append(
                    Earnings(
                        fiscal_period=None,
                        eps=eps,
                        consensus_eps=consensus,
                        report_date=rpt,
                        surprise=surprise_abs,
                        revenue=None,
                    )
                )
            return out
        return await asyncio.to_thread(_fetch)


# -----------------------------------------------------------------------------
# Polygon market data client (quotes/bars/news + pluggable events)
# -----------------------------------------------------------------------------
class PolygonClient:
    """Async client for Polygon quotes/bars/news; events via pluggable EventsPort."""
    def __init__(self, timeout: float = 15.0, events_provider: Optional[EventsPort] = None):
        if not _API_KEY:
            raise RuntimeError("POLYGON_API_KEY missing in environment/.env")
        self.http = httpx.AsyncClient(timeout=timeout)
        # Default to YFinance for events per your request
        self.events: EventsPort = events_provider or YFinanceEventsProvider()

    async def aclose(self):
        await self.http.aclose()

    async def prev_close(self, symbol: str, adjusted: bool = True) -> Dict[str, Any]:
        url = f"{_BASE}/v2/aggs/ticker/{symbol.upper()}/prev"
        r = await _request_with_retry(
            self.http, "GET", url, params={"adjusted": str(adjusted).lower()}
        )
        data = r.json()
        if not data.get("results"):
            raise RuntimeError(f"No prev data for {symbol}")
        return data["results"][0]

    async def aggregates(
        self,
        symbol: str,
        multiplier: int,
        timespan: str,
        start: str,
        end: str,
        adjusted: bool = True,
        limit: int = 50000,
    ) -> List[Dict[str, Any]]:
        url = f"{_BASE}/v2/aggs/ticker/{symbol.upper()}/range/{multiplier}/{timespan}/{start}/{end}"
        r = await _request_with_retry(
            self.http,
            "GET",
            url,
            params={"adjusted": str(adjusted).lower(), "limit": limit},
        )
        return r.json().get("results", [])

    async def news(self, symbol: str, limit: int = 8) -> list[NewsItem]:
        url = f"{_BASE}/v2/reference/news"
        r = await _request_with_retry(
            self.http,
            "GET",
            url,
            params={
                "ticker": symbol.upper(),
                "limit": limit,
                "order": "desc",
                "sort": "published_utc",
            },
        )
        j = r.json()
        items: list[NewsItem] = []
        for n in j.get("results", []):
            published_raw = n.get("published_utc")
            published_at = (
                datetime.fromisoformat(published_raw.replace("Z", "+00:00"))
                if published_raw else datetime.now(timezone.utc)
            )
            items.append(
                NewsItem(
                    publisher=(n.get("publisher", {}) or {}).get("name", "Unknown"),
                    title=n.get("title", "(no title)"),
                    url=n.get("article_url", ""),
                    published_at=published_at,
                )
            )
        return items

    async def bundle(
        self,
        symbol: str,
        *,
        bars_multiplier: int = 1,
        bars_timespan: str = "day",
        bars_start: str | None = None,
        bars_end: str | None = None,
        bars_lookback: int = 60,
        news_limit: int = 6,
        events_limit: int = 20,
    ) -> IntelBundle:
        if not bars_start or not bars_end:
            bars_start, bars_end = _default_range(bars_timespan, bars_lookback)

        # quote
        q = await self.prev_close(symbol)
        ts = q.get("t")
        as_of_dt = _epoch_ms_to_utc(ts) or datetime.now(timezone.utc)
        quote = Quote(
            symbol=symbol.upper(),
            prevClose=q.get("c"),
            high=q.get("h"),
            low=q.get("l"),
            volume=int(q.get("v", 0)),
            as_of=as_of_dt,
        )

        # bars
        bars_raw = await self.aggregates(
            symbol, bars_multiplier, bars_timespan, bars_start, bars_end
        )
        bars = [Bar(t=b["t"], o=b["o"], h=b["h"], l=b["l"], c=b["c"], v=b["v"]) for b in bars_raw]

        # news
        latest_news = await self.news(symbol, limit=news_limit)

        # events (pluggable)
        dividends, splits, earnings = await asyncio.gather(
            self.events.dividends(symbol, limit=events_limit),
            self.events.splits(symbol, limit=events_limit),
            self.events.earnings(symbol, limit=events_limit),
        )

        return IntelBundle(
            symbol=symbol.upper(),
            quote=quote,
            bars=bars,
            news=latest_news,
            dividends=dividends,
            splits=splits,
            earnings=earnings,
        )


# -----------------------------------------------------------------------------
# Range helper
# -----------------------------------------------------------------------------
def _default_range(timespan: str, lookback: int) -> tuple[str, str]:
    end_dt = datetime.now(timezone.utc).date()
    if timespan == "day":
        start_dt = end_dt - timedelta(days=lookback)
    elif timespan == "week":
        start_dt = end_dt - timedelta(weeks=lookback)
    elif timespan == "month":
        start_dt = end_dt - timedelta(days=30 * lookback)
    else:
        start_dt = end_dt - timedelta(days=lookback)
    return (start_dt.isoformat(), end_dt.isoformat())


# -----------------------------------------------------------------------------
# Smoke test
# -----------------------------------------------------------------------------
async def _smoke():
    # By default, uses YFinanceEventsProvider; to force Polygon events, pass:
    #   cli = PolygonClient(events_provider=PolygonEventsProvider(httpx.AsyncClient()))
    cli = PolygonClient()
    try:
        b = await cli.bundle("AAPL", bars_timespan="week", bars_lookback=12, events_limit=10)
        print("Bundle for", b.symbol)
        print("Prev close:", b.quote.prevClose)
        print("Bars:", len(b.bars))
        print("News:", len(b.news))
        print("Dividends:", len(b.dividends))
        print("Splits:", len(b.splits))
        print("Earnings:", len(b.earnings))
    finally:
        await cli.aclose()

if __name__ == "__main__":
    asyncio.run(_smoke())
