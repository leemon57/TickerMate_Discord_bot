import asyncio
import json
import math
from typing import Any, Dict, List, Optional, Tuple

import httpx
from config import settings

_BASE = "https://api.polygon.io"
_API_KEY = settings.POLYGON_API_KEY

# this function makes an HTTP request and retries if it fails
async def _request_with_retry(http: httpx.AsyncClient, method: str, url: str, *,
                              params: Dict[str, Any] | None = None,
                              max_retries: int = 3) -> httpx.Response:
    tries = 0
    params = dict(params or {})
    params.setdefault("apiKey", _API_KEY)

    while True:
        r = await http.request(method, url, params=params)

        # handle common auth/rate-limit explicitly
        if r.status_code in (401, 403):
            raise RuntimeError(f"Polygon auth/permission error {r.status_code}: {r.text}")

        if r.status_code == 429:   # too many requests
            tries += 1
            if tries > max_retries:
                raise RuntimeError("Polygon rate limited (429) after retries.")
            await asyncio.sleep(1.5 * tries)  # wait a bit longer each retry
            continue

        if r.status_code >= 500:  # server-side error
            tries += 1
            if tries > max_retries:
                r.raise_for_status()
            await asyncio.sleep(1.0 * tries)
            continue

        r.raise_for_status()  # raise if it’s any other 4xx client error
        return r

#client wrapper

# ---- client wrapper ---------------------------------------------------------
class PolygonClient:
    """
    Lightweight async client for Polygon endpoints you’ll use most often.
    Create *one* instance and reuse it (keeps TCP connections warm).
    """
    def __init__(self, timeout: float = 15.0):
        if not _API_KEY:
            raise RuntimeError("POLYGON_API_KEY missing in environment/.env")
        self.http = httpx.AsyncClient(timeout=timeout)

    async def aclose(self):
        await self.http.aclose()

    # 1) Previous close (daily)
    async def prev_close(self, symbol: str, adjusted: bool = True) -> Dict[str, Any]:
        url = f"{_BASE}/v2/aggs/ticker/{symbol.upper()}/prev"
        r = await _request_with_retry(self.http, "GET", url, params={"adjusted": str(adjusted).lower()})
        data = r.json()
        # shape: {"results":[{"c":close,"h":high,"l":low,"o":open,"v":volume,"t":ts}], ...}
        if not data.get("results"):
            raise RuntimeError(f"No prev data for {symbol}")
        return data["results"][0]

    # 2) Aggregates (OHLCV bars)
    async def aggregates(self, symbol: str, multiplier: int, timespan: str,
                         start: str, end: str, adjusted: bool = True,
                         limit: int = 50000) -> List[Dict[str, Any]]:
        """
        timespan: 'minute', 'hour', 'day', etc.
        start/end: ISO dates like '2025-09-01' or timestamps supported by Polygon.
        """
        url = f"{_BASE}/v2/aggs/ticker/{symbol.upper()}/range/{multiplier}/{timespan}/{start}/{end}"
        r = await _request_with_retry(
            self.http, "GET", url,
            params={"adjusted": str(adjusted).lower(), "limit": limit}
        )
        j = r.json()
        return j.get("results", [])

    # 3) SMA via Polygon technical indicators
    async def sma(self, symbol: str, window: int = 20, timespan: str = "day",
                  series_type: str = "close", expand_underlying: bool = False) -> Dict[str, Any]:
        """
        Returns the indicator payload; values under 'results.values'
        """
        url = f"{_BASE}/v1/indicators/sma/{symbol.upper()}"
        r = await _request_with_retry(
            self.http, "GET", url,
            params={
                "timespan": timespan,
                "window": window,
                "series_type": series_type,
                "expand_underlying": str(expand_underlying).lower(),
            }
        )
        return r.json()

# ---- quick standalone test ---------------------------------------------------
async def _smoke():
    cli = PolygonClient()
    try:
        prev = await cli.prev_close("AAPL")
        print("AAPL prev close:", prev["c"], "H/L:", prev["h"], prev["l"], "Vol:", prev["v"])

        bars = await cli.aggregates("AAPL", 1, "day", "2025-08-15", "2025-09-03")
        print("AAPL bars:", len(bars), "most recent close:", bars[-1]["c"] if bars else None)

        ind = await cli.sma("AAPL", window=10, timespan="day")
        vals = ind.get("results", {}).get("values", [])
        print("AAPL SMA(10) last:", vals[-1]["value"] if vals else None)
    finally:
        await cli.aclose()

if __name__ == "__main__":
    # Run:  python -m modules.intel.loader
    asyncio.run(_smoke())