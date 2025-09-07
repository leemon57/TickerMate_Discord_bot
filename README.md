# AI Market Bot for Discord (Stocks & Crypto)

> **Modular** Discord bot for market data, charts, options snapshots, and AI summaries. Works with stocks (Polygon + yfinance) and crypto (Coinbase/Binance + CryptoPanic). Includes a strict-JSON AI analyst powered by OpenAI.

> **Disclaimer**: Educational use only. Not investment advice.

---

## ✨ Features

* **Market intel** for both **stocks** and **crypto** with a unified syntax
* **AI analysis** (`!ai`) that returns a structured rating (1–5), confidence, and a concise summary
* **Charts** (`!chart`) with line or candlesticks, optional resampling, exported as PNG
* **CSV export** (`!csv`) of OHLCV data
* **News** (`!news`) from Polygon (equities) and CryptoPanic (crypto)
* **Derivatives (crypto)** funding rate & open interest (`!funding`)
* **Options (equities)** expirations (`!expirations`) and an ATM **chain snapshot** (`!chain`)
* **Async** clients with graceful shutdowns
* Clear, minimal **Embeds** formatted for Discord

---

## 📁 Project Structure

```
.
├─ ai/
│  ├─ analyst.py            # Build compact fact pack: price, indicators, S/R, events, derivs, news
│  └─ client.py             # Calls OpenAI; structured output (rating/conf/summary/…)
│  └─ ai_cog.py
├─ intel/
│  ├─ stock_loader.py       # Polygon + yfinance-based loader for stocks & options
│  ├─ crypto_loader.py      # Coinbase/Binance/CryptoPanic loader for crypto
│  └─ cog.py                # MarketCog: !price, !news, !funding, !expirations, !chain
├─ charts/
│  ├─ __init__.py           # adapters, exporters, renderers
│  ├─ adapters.py           # bars_to_df, resampling
│  ├─ exporters.py          # df_to_csv_bytes
│  └─ renderers.py          # render_line_close, render_candles
│  └─ cog.py                # MarketCog: !price, !news, !funding, !expirations, !chain
├─ indicators/
│  ├─ core.py               # SMA, EMA, RSI, MACD, BB, ATR, OBV, etc.
│  └─ indicator_cog.py      # (optional) commands like !sma, !rsi, !macd
├─ bot.py                  # bot entrypoint (example below)
├─ requirements.txt         # pinned deps (see below)
└─ README.md                # this file
```

> Names may vary slightly in your repo; adjust imports accordingly.

---

## 🔧 Requirements

* **Python** 3.11+ (recommended)
* **Discord bot** with *Message Content Intent* enabled
* Accounts/keys:

  * **Discord**: `DISCORD_TOKEN`
  * **OpenAI**: `OPENAI_API_KEY` (for AI analysis)
  * **Polygon.io**: `POLYGON_API_KEY` (equities; free tier works for testing)
  * **CryptoPanic** (optional): `CRYPTOPANIC_API_KEY` if you use curated crypto news
  * **Binance/Coinbase**: public endpoints used; no key needed for shown features

### Suggested `requirements.txt`

```
discord.py>=2.3
httpx>=0.27
pydantic>=2.7
pandas>=2.2
numpy>=1.26
matplotlib>=3.8
python-dateutil>=2.9
yfinance>=0.2
openai>=1.43
```

> **Headless Linux?** Set `MPLBACKEND=Agg` in the environment or ensure your `charts` module does so before plotting.

---

## 🔐 Environment Variables (.env)

Create a `.env` (or use your secret manager):

```
DISCORD_TOKEN=your_discord_bot_token
OPENAI_API_KEY=sk-...
POLYGON_API_KEY=...
CRYPTOPANIC_API_KEY=...            # optional

# AI tuning
AI_MODEL_PRIMARY=gpt-5              # or your strongest model
AI_MODEL_FALLBACK=gpt-4.1
AI_TEMPERATURE=0.1
AI_MAX_TOKENS=900
AI_DEBUG=0                          # set 1 to log raw model payloads

# Bot
COMMAND_PREFIX=!
```

> **Never commit real keys**. Add `.env` to your `.gitignore`.

---

## 🚀 Run Locally

1. Create & activate a virtualenv

```bash
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
```

2. Install deps

```bash
pip install -r requirements.txt
```

3. Add your `.env`

4. Use this minimal `main.py` to boot the bot:

```python
# main.py
from __future__ import annotations
import os, asyncio, discord
from discord.ext import commands

PREFIX = os.getenv("COMMAND_PREFIX", "!")

intents = discord.Intents.default()
intents.message_content = True  # required for prefix commands

bot = commands.Bot(command_prefix=PREFIX, intents=intents)

async def load_cogs():
    await bot.load_extension("cogs.ai_cog")
    await bot.load_extension("cogs.chart_cog")
    await bot.load_extension("intel.cog")      # MarketCog

async def main():
    async with bot:
        await load_cogs()
        await bot.start(os.environ["DISCORD_TOKEN"])

if __name__ == "__main__":
    asyncio.run(main())
```

5. Start the bot

```bash
python main.py
```

6. Invite the bot to your server with appropriate permissions (Read/Send Messages, Embed Links, Attach Files).

---

## 🧭 Symbol Rules

* **Stocks:** `AAPL`, `NVDA`, `MSFT`, etc.
* **Crypto:** `BTC-USD`, `ETH-USD` or `BTCUSDT`/`ETHUSDT` style.

> The bot auto-detects crypto symbols via `BTC-USD` or `*USDT` suffixes.

---

## 🗺️ Command Reference

### `!ai SYMBOL [horizon] [risk]`

AI analysis with rating (1–5), confidence (0–1), and a one-liner.

* **Horizon:** `scalp | day | swing | position` (free-form accepted)
* **Risk:** `low | medium | high` (free-form accepted)

**Examples**

```
!ai AAPL
!ai NVDA swing medium
!ai BTC-USD day low
```

**Notes**

* Uses `ai/analyst.py` to build a compact fact pack: price, indicators, support/resistance, events (earnings/dividends), derivatives (funding/open interest), and news.
* Calls `ai/client.py` which returns strict JSON (enforced via structured outputs/function-calling when available).
* The embed shows `Rating X/5 (conf Y.YY)` + summary.

---

### `!chart SYMBOL [line|candle] [day|week|month] [lookback] [resample? H|D|W|M]`

Render a PNG chart. Defaults: `line day 180`.

**Examples**

```
!chart AAPL
!chart AAPL candle day 180
!chart BTC-USD line day 90 H
```

**Notes**

* Stocks: Polygon bars with `timespan` & `lookback` parameters
* Crypto: default bundle (24h/spot), then optional resampling to `H`, `D`, `W`, `M`
* Uses `charts/` to convert, optionally resample, and render to PNG

---

### `!csv SYMBOL [day|week|month] [lookback] [resample? H|D|W|M]`

Export OHLCV as CSV.

**Examples**

```
!csv AAPL
!csv AAPL week 104
!csv ETH-USD day 90 D
```

---

### `!price SYMBOL`

Quick snapshot of prev close and session ranges.

**Examples**

```
!price AAPL
!price BTC-USD
```

**Notes**

* **Stocks**: Polygon previous session OHLCV
* **Crypto**: Coinbase spot; optional derivatives notional if OI available

---

### `!news SYMBOL [limit]`

Latest headlines for a ticker.

**Examples**

```
!news AAPL
!news BTC-USD 7
```

**Sources**

* **Stocks**: Polygon News API
* **Crypto**: CryptoPanic aggregator (optionally filtered/scored)

---

### `!funding SYMBOL`

Crypto funding rate and open interest snapshot.

**Example**

```
!funding BTC-USD
```

**Notes**

* Pulls funding and OI from Binance Futures public endpoints when available.

---

### `!expirations SYMBOL`

List upcoming option expiries for an equity (yfinance-backed).

**Example**

```
!expirations AAPL
```

---

### `!chain SYMBOL [YYYY-MM-DD]`

ATM call/put snapshot and counts for the specified (or nearest) expiry.

**Examples**

```
!chain AAPL
!chain AAPL 2025-09-19
```

**Notes**

* Picks ATM strikes based on previous close.
* Shows bid/ask and (if present) implied vol for the two ATM legs.

---

## 🧠 AI Output Schema

The AI response (rendered by `!ai`) includes:

```json
{
  "symbol": "TICKER",
  "rating": 1,
  "confidence": 0.62,
  "summary": "One-liner",
  "trend": {"dir":"up|down|side","rsi":61.2,"sma20_above50":true,"price_vs_sma200":"above"},
  "levels": {"support":[236.5], "resistance":[242.0]},
  "signals_bull": ["..."],
  "signals_bear": ["..."],
  "derivs": {"funding":0.0001,"oi_chg_24h":0.03,"iv_rank":0.62},
  "events": {"next_earn":"YYYY-MM-DD","div_ex":"YYYY-MM-DD"},
  "news": ["headline1","headline2"],
  "risk_notes": ["..."]
}
```

> The concrete schema is enforced in `ai/client.py` (Structured Outputs / Function Calling). If the model lacks support, the client falls back to JSON mode with runtime validation.

---

## 🔌 Data Sources

* **Polygon.io** (equities: quotes, bars, news)
* **yfinance** (events like earnings/dividends, and options expirations/chains)
* **Coinbase** (spot)
* **Binance Futures** (funding rate, open interest)
* **CryptoPanic** (crypto news aggregator)

> Some endpoints are best-effort and may be rate-limited or temporarily unavailable.

---

## 🧪 Local Testing Tips

* Add a `scripts/check_events.py` that fetches a bundle and prints upcoming `next_earn` / dividend to verify the events pipeline.
* Temporarily enable `AI_DEBUG=1` to log raw AI payloads.
* Use a private channel to try commands without rate-limiting the bot across servers.

```python
# scripts/check_events.py (example)
import asyncio, os
from intel.stock_loader import PolygonClient

async def main():
    sym = os.getenv("SYM", "AAPL")
    pc = PolygonClient()
    b = await pc.bundle(sym, bars_lookback=10, news_limit=1)
    print("next_earn:", getattr(b.events, "next_earn", None))
    print("div_ex:", getattr(b.events, "div_ex", None))
    await pc.aclose()

if __name__ == "__main__":
    asyncio.run(main())
```

---

## 🧰 Troubleshooting

* **The bot doesn’t respond to `!` commands**

  * Ensure *Message Content Intent* is enabled in the Discord Developer Portal
  * Verify the bot has `Read Messages/View Channels`, `Send Messages`, `Embed Links`, `Attach Files`

* **`AI analysis failed: ...`**

  * Check `OPENAI_API_KEY` and org access to your chosen model
  * Try switching to a known-good fallback model via `AI_MODEL_FALLBACK`
  * Set `AI_DEBUG=1` and inspect logs

* **Always getting rating `3/5`**

  * Ensure your `ai/client.py` doesn’t bias toward 3 and that schema enforcement/validation is enabled

* **`No data to chart`**

  * Symbol typo or illiquid/unsupported pair; try a popular ticker first

* **`insufficient_quota` / 429**

  * You’ve hit a provider’s rate limit/quota (OpenAI/Polygon). Reduce frequency or upgrade plan.

* **`Invalid expiration format`** on `!chain`

  * Use `YYYY-MM-DD` (e.g., `!chain AAPL 2025-09-19`) or omit to let the bot pick the nearest

---

## 🗺️ Roadmap (optional)

* Multi-panel charts (price + RSI/MACD/ATR stacked)
* Per-symbol caching of AI outputs for a short TTL to reduce costs
* Slash command equivalents for all prefix commands
* Backtesting hooks & signals preview exported as CSV/PNG
* Per-guild settings: default horizon/risk, default chart lookback

---

## 🙏 Acknowledgements

* Thanks to Polygon.io, Coinbase, Binance, and CryptoPanic for their public APIs.
* Built with `discord.py` and OpenAI’s Chat Completions API.
