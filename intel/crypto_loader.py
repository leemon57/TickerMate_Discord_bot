from __future__ import annotations

import asyncio
from typing import List, Dict, Any, Optional
from datetime import datetime, timezone

import httpx

from config import settings
from .contract import (
    Quote, Bar, NewsItem,
    Dividend, Split, Earnings,   # present for IntelBundle shape (unused for crypto)
    IntelBundle,
    OpenInterest, Funding,
)

# -----------------------------------------------------------------------------
# Helpers
# -----------------------------------------------------------------------------

def _utc_now() -> datetime:
    return datetime.now(timezone.utc)

def _epoch_sec_to_ms(t: int | float) -> int:
    return int(float(t) * 1000)

def _ms_to_utc(ms: Optional[int]) -> Optional[datetime]:
    if ms is None:
        return None
    return datetime.fromtimestamp(int(ms) / 1000, tz=timezone.utc)

def _symbol_to_binance_perp(product_id: str) -> str:
    """
    Map spot product like 'BTC-USD' -> 'BTCUSDT' (Binance perp).
    If already looks like 'BTCUSDT', return as-is.
    """
    s = product_id.upper().replace("-", "")
    if s.endswith("USD"):
        base = s[:-3]
        return base + "USDT"
    return s

def _product_to_currency(product_id: str) -> str:
    return "USDT" if product_id.upper().endswith("USD") else "USD"

# -----------------------------------------------------------------------------
# Coinbase (spot) client: OHLCV + 24h stats -> Quote + Bars
# -----------------------------------------------------------------------------

_CB_BASE = "https://api.exchange.coinbase.com"

class CoinbaseClient:
    """Spot data: candles/24h stats → Quote + Bars."""
    def __init__(self, timeout: float = 15.0, base: str = _CB_BASE):
        self.http = httpx.AsyncClient(
            base_url=base,
            timeout=timeout,
            headers={"User-Agent": "discord-bot/crypto-intel"}
        )

    async def aclose(self):
        await self.http.aclose()

    async def stats_24h(self, product_id: str) -> Dict[str, Any]:
        r = await self.http.get(f"/products/{product_id}/stats")
        r.raise_for_status()
        return r.json()

    async def candles(
        self,
        product_id: str,
        *,
        granularity: int = 3600,
        limit: int = 300
    ) -> List[List[float]]:
        """
        GET /products/{product_id}/candles?granularity=...
        Returns rows: [ time, low, high, open, close, volume ] (newest first).
        We reverse to oldest->newest and slice to limit.
        """
        r = await self.http.get(
            f"/products/{product_id}/candles",
            params={"granularity": granularity},
        )
        r.raise_for_status()
        data = r.json()
        rows = list(reversed(data)) if isinstance(data, list) else []
        return rows[:limit]

    @staticmethod
    def _rows_to_bars(rows: List[List[float]]) -> List[Bar]:
        bars: List[Bar] = []
        for row in rows:
            # [ time, low, high, open, close, volume ]
            t_sec, low, high, open_, close, vol = row
            bars.append(
                Bar(
                    t=_epoch_sec_to_ms(t_sec),
                    o=float(open_),
                    h=float(high),
                    l=float(low),
                    c=float(close),
                    v=int(float(vol)),
                )
            )
        return bars

    async def quote(self, product_id: str) -> Quote:
        """
        Map Coinbase's 24h stats to Quote:
          - prevClose: 24h 'open' (practical proxy for sessionless markets)
          - high/low: 24h high/low
          - volume: 24h base volume
          - as_of: now
        """
        stats = await self.stats_24h(product_id)
        prev_close = float(stats.get("open") or 0.0)
        high       = float(stats.get("high") or 0.0)
        low        = float(stats.get("low") or 0.0)
        volume     = int(float(stats.get("volume") or 0.0))
        return Quote(
            symbol=product_id.upper(),
            prevClose=prev_close,
            high=high,
            low=low,
            volume=volume,
            as_of=_utc_now(),
        )

    async def bars(
        self,
        product_id: str,
        *,
        granularity: int = 3600,
        lookback: int = 300
    ) -> List[Bar]:
        rows = await self.candles(product_id, granularity=granularity, limit=lookback)
        return self._rows_to_bars(rows)

# -----------------------------------------------------------------------------
# Binance Futures (derivatives): Open Interest + Funding
# -----------------------------------------------------------------------------

_BINANCE_FAPI = "https://fapi.binance.com"  # public; no key required

class BinanceDerivatives:
    def __init__(self, timeout: float = 10.0):
        self.http = httpx.AsyncClient(
            base_url=_BINANCE_FAPI,
            timeout=timeout,
            headers={"User-Agent": "discord-bot/derivs"}
        )

    async def aclose(self):
        await self.http.aclose()

    async def open_interest(self, symbol_perp: str) -> Optional[OpenInterest]:
        """
        GET /fapi/v1/openInterest?symbol=BTCUSDT -> {"openInterest":"12345.6789"}
        Returns number of contracts (for USDT-M BTCUSDT, effectively base units ≈ BTC).
        """
        r = await self.http.get("/fapi/v1/openInterest", params={"symbol": symbol_perp})
        r.raise_for_status()
        j = r.json()
        amount = float(j.get("openInterest", 0.0))
        return OpenInterest(symbol=symbol_perp, amount=amount, ts=_utc_now(), currency=None)

    async def funding(self, symbol_perp: str) -> Optional[Funding]:
        """
        GET /fapi/v1/premiumIndex?symbol=BTCUSDT
          -> {"lastFundingRate":"0.0001","nextFundingTime":1693910400000,...}
        """
        r = await self.http.get("/fapi/v1/premiumIndex", params={"symbol": symbol_perp})
        r.raise_for_status()
        j = r.json()
        rate = float(j.get("lastFundingRate") or j.get("fundingRate") or 0.0)
        nft  = j.get("nextFundingTime")
        return Funding(symbol=symbol_perp, rate=rate, next_funding_time=_ms_to_utc(int(nft)) if nft else None)

# -----------------------------------------------------------------------------
# CryptoPanic news (with richer fields)
# -----------------------------------------------------------------------------

class CryptoPanicNews:
    """
    Lightweight wrapper for CryptoPanic News API.
    Sign up: https://cryptopanic.com/developers/api/
    Put key in .env as CRYPTOPANIC_API_KEY and ensure config.settings reads it.
    """
    def __init__(self, api_key: Optional[str], timeout: float = 10.0):
        self.api_key = api_key
        self.http = httpx.AsyncClient(
            timeout=timeout,
            headers={"User-Agent": "discord-bot/cryptonews"}
        )

    async def aclose(self):
        await self.http.aclose()

    async def news(self, base_symbol: str, *, limit: int = 10) -> List[NewsItem]:
        if not self.api_key:
            return []

        params = {
            "auth_token": self.api_key,
            "currencies": base_symbol.upper(),  # e.g., "BTC"
            "public": "true",
            "filter": "hot",     # "hot" | "rising" | "important" | "all"
            "kind": "news",
            "page": 1,
        }

        # Try the current developer API first, follow redirects just in case.
        url = "https://cryptopanic.com/api/developer/v2/posts/"
        r = await self.http.get(url, params=params, follow_redirects=True)

        # Fallback to v1 (developer) if some keys/accounts are still on it.
        if r.status_code == 404:
            url = "https://cryptopanic.com/api/developer/v1/posts/"
            r = await self.http.get(url, params=params, follow_redirects=True)

        r.raise_for_status()
        j = r.json()

        out: List[NewsItem] = []
        for item in j.get("results", [])[:limit]:
            pub = item.get("published_at")
            dt = datetime.fromisoformat(pub.replace("Z", "+00:00")) if pub else _utc_now()

            title = item.get("title") or (item.get("source", {}) or {}).get("title") or "(no title)"
            url   = item.get("url") or (item.get("source", {}) or {}).get("domain") or ""
            src   = (item.get("source", {}) or {}).get("domain", "CryptoPanic")

            kind = item.get("kind")
            currs = [c.get("code") for c in (item.get("currencies") or []) if isinstance(c, dict) and c.get("code")]

            votes = item.get("votes") or {}
            liked = int(votes.get("liked") or 0)
            disliked = int(votes.get("disliked") or 0)
            important_flag = bool(votes.get("important")) if votes.get("important") is not None else None
            score = liked - disliked

            out.append(
                NewsItem(
                    publisher=src,
                    title=title,
                    url=url,
                    published_at=dt,
                    sentiment=None,
                    importance=important_flag,
                    kind=kind,
                    currencies=currs,
                    score=score,
                )
            )
        return out

# -----------------------------------------------------------------------------
# Public facade: CryptoClient
# -----------------------------------------------------------------------------

class CryptoClient:
    """
    High-level crypto loader that:
      - pulls spot OHLCV/24h stats from Coinbase,
      - pulls funding & open interest from Binance perps,
      - pulls crypto-specific news from CryptoPanic (with metadata),
      - maps all of it into your IntelBundle shape.
    """
    def __init__(
        self,
        *,
        cryptopanic_api_key: Optional[str] = settings.CRYPTOPANIC_API_KEY,
        granularity: int = 3600,
        lookback: int = 300,
    ):
        self.spot = CoinbaseClient()
        self.derivs = BinanceDerivatives()
        self.newsprov = CryptoPanicNews(api_key=cryptopanic_api_key)
        self.granularity = granularity
        self.lookback = lookback

    async def aclose(self):
        await asyncio.gather(
            self.spot.aclose(),
            self.derivs.aclose(),
            self.newsprov.aclose(),
        )

    async def bundle(self, product_id: str, *, news_limit: int = 8) -> IntelBundle:
        """
        product_id: e.g. 'BTC-USD', 'ETH-USD' (spot). We'll derive 'BTCUSDT' etc. for perps/news.
        """
        perp = _symbol_to_binance_perp(product_id)
        base = perp.removesuffix("USDT").removesuffix("USD")  # "BTC" from "BTCUSDT"

        quote_coro = self.spot.quote(product_id)
        bars_coro  = self.spot.bars(product_id, granularity=self.granularity, lookback=self.lookback)
        oi_coro    = self.derivs.open_interest(perp)
        fund_coro  = self.derivs.funding(perp)
        news_coro  = self.newsprov.news(base, limit=news_limit)

        quote, bars, oi, fund, news_items = await asyncio.gather(
            quote_coro, bars_coro, oi_coro, fund_coro, news_coro
        )

        # Label OI with a currency hint for UI context
        if oi and oi.currency is None:
            oi.currency = _product_to_currency(product_id)

        return IntelBundle(
            symbol=product_id.upper(),
            quote=quote,
            bars=bars,
            news=news_items,
            dividends=[],     # not applicable for crypto
            splits=[],
            earnings=[],
            open_interest=oi,
            funding=fund,
        )

# -----------------------------------------------------------------------------
# Smoke test
# -----------------------------------------------------------------------------

async def _smoke():
    cli = CryptoClient(
        cryptopanic_api_key=settings.CRYPTOPANIC_API_KEY,  # None => news []
        granularity=3600,
        lookback=200,
    )
    try:
        b = await cli.bundle("BTC-USD", news_limit=5)
        print("Crypto bundle for", b.symbol)
        print("Prev close:", b.quote.prevClose)
        print("Bars:", len(b.bars))
        if b.open_interest:
            notional = b.open_interest.amount * (b.quote.prevClose or 0.0)
            print(f"Open interest: {b.open_interest.amount:.3f} (≈ ${notional:,.0f} notional)")
        if b.funding:
            print(f"Funding rate: {b.funding.rate:.6f}  next: {b.funding.next_funding_time}")
        print("News:", len(b.news))
        for n in b.news:
            flags = []
            if n.importance: flags.append("★")
            if n.score is not None: flags.append(f"score={n.score}")
            if n.currencies: flags.append(",".join(n.currencies))
            tag = f" [{' '.join(flags)}]" if flags else ""
            print("-", n.publisher, "|", n.title, tag)
    finally:
        await cli.aclose()

if __name__ == "__main__":
    asyncio.run(_smoke())
