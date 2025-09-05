# intel/cog.py
from __future__ import annotations

import asyncio
from datetime import datetime
from typing import Optional

import discord
from discord.ext import commands

# Loaders you built
from intel.stock_loader import PolygonClient  # stocks (Polygon + yfinance events/options)
from intel.crypto_loader import CryptoClient  # crypto (Coinbase + Binance + CryptoPanic)

# -----------------------------------------------------------------------------
# Helpers
# -----------------------------------------------------------------------------

def _is_crypto_symbol(sym: str) -> bool:
    s = sym.upper()
    # BTC-USD / ETH-USD / etc. treated as crypto
    if "-" in s and s.endswith("USD"):
        return True
    # Common perp symbol forms (e.g., BTCUSDT, ETHUSDT)
    if s.endswith("USDT") and len(s) >= 7:
        return True
    return False

def _fmt_pct(x: Optional[float]) -> str:
    if x is None:
        return "—"
    return f"{x*100:.3f}%"

def _fmt_usd(x: Optional[float]) -> str:
    if x is None:
        return "—"
    return f"${x:,.2f}"

# -----------------------------------------------------------------------------
# Cog
# -----------------------------------------------------------------------------

class MarketCog(commands.Cog):
    """Market intel for both stocks and crypto."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        # build clients here; they manage their own httpx sessions
        self.stock = PolygonClient()
        self.crypto = CryptoClient()

    def cog_unload(self):
        # close async clients gracefully
        async def _close():
            await asyncio.gather(
                self.stock.aclose(),
                self.crypto.aclose(),
                return_exceptions=True,
            )
        asyncio.create_task(_close())

    # ------------------------------- Commands --------------------------------

    @commands.command(name="price")
    async def price_cmd(self, ctx: commands.Context, symbol: str):
        """
        Show last/prev-close & basic stats for a stock or crypto.
        Usage: !price AAPL  |  !price BTC-USD
        """
        sym = symbol.upper().strip()

        try:
            if _is_crypto_symbol(sym):
                b = await self.crypto.bundle(sym, news_limit=0)
                q = b.quote
                if not q:
                    return await ctx.send(f"Could not fetch quote for `{sym}`.")
                # Derivatives extras (optional display)
                oi_part = ""
                if b.open_interest:
                    # Approx notional = contracts * spot price
                    notional = (b.open_interest.amount or 0.0) * (q.prevClose or 0.0)
                    oi_part = f"\n**Open Interest:** {b.open_interest.amount:,.0f} (~{_fmt_usd(notional)})"
                fund_part = f"\n**Funding:** {_fmt_pct(b.funding.rate)} next {b.funding.next_funding_time}" if b.funding else ""

                embed = discord.Embed(
                    title=f"{sym} — Crypto",
                    description=f"**Prev (24h open proxy):** {_fmt_usd(q.prevClose)}\n"
                                f"**High/Low (24h):** {_fmt_usd(q.high)} / {_fmt_usd(q.low)}\n"
                                f"**Volume (24h):** {q.volume:,}"
                                f"{oi_part}{fund_part}",
                    color=discord.Color.gold(),
                    timestamp=q.as_of,
                )
                embed.set_footer(text="Spot: Coinbase | OI/Funding: Binance Futures")
                return await ctx.send(embed=embed)

            # Stock path
            b = await self.stock.bundle(sym, bars_timespan="day", bars_lookback=1, news_limit=0)
            q = b.quote
            if not q:
                return await ctx.send(f"Could not fetch quote for `{sym}`.")
            embed = discord.Embed(
                title=f"{sym} — Stock",
                description=f"**Prev Close:** {_fmt_usd(q.prevClose)}\n"
                            f"**High/Low (Prev Session):** {_fmt_usd(q.high)} / {_fmt_usd(q.low)}\n"
                            f"**Volume (Prev Session):** {q.volume:,}",
                color=discord.Color.blue(),
                timestamp=q.as_of,
            )
            embed.set_footer(text="Data: Polygon.io")
            await ctx.send(embed=embed)

        except Exception as e:
            await ctx.send(f"⚠️ Error fetching price for `{sym}`: `{e}`")

    @commands.command(name="news")
    async def news_cmd(self, ctx: commands.Context, symbol: str, limit: int = 5):
        """
        Show latest news headlines for a stock or crypto.
        Usage: !news AAPL  |  !news BTC-USD [limit]
        """
        sym = symbol.upper().strip()
        limit = max(1, min(limit, 10))

        try:
            if _is_crypto_symbol(sym):
                b = await self.crypto.bundle(sym, news_limit=limit)
                items = b.news[:limit]
                if not items:
                    return await ctx.send(f"No recent crypto news for `{sym}`.")
                embed = discord.Embed(
                    title=f"News — {sym} (Crypto)",
                    color=discord.Color.gold(),
                )
                for n in items:
                    flags = []
                    if n.importance:
                        flags.append("★ important")
                    if n.score is not None:
                        flags.append(f"score {n.score}")
                    if n.currencies:
                        flags.append(",".join(n.currencies))
                    tag = f" — {' | '.join(flags)}" if flags else ""
                    embed.add_field(
                        name=n.title[:256],
                        value=f"[{n.publisher}]({n.url}) • {n.published_at:%Y-%m-%d %H:%M} UTC{tag}",
                        inline=False,
                    )
                embed.set_footer(text="CryptoPanic aggregator")
                return await ctx.send(embed=embed)

            # Stock path
            b = await self.stock.bundle(sym, news_limit=limit, bars_lookback=1)
            items = b.news[:limit]
            if not items:
                return await ctx.send(f"No recent stock news for `{sym}`.")
            embed = discord.Embed(
                title=f"News — {sym} (Stock)",
                color=discord.Color.blue(),
            )
            for n in items:
                embed.add_field(
                    name=n.title[:256],
                    value=f"[{n.publisher}]({n.url}) • {n.published_at:%Y-%m-%d %H:%M} UTC",
                    inline=False,
                )
            embed.set_footer(text="Polygon.io news")
            await ctx.send(embed=embed)

        except Exception as e:
            await ctx.send(f"⚠️ Error fetching news for `{sym}`: `{e}`")

    @commands.command(name="funding")
    async def funding_cmd(self, ctx: commands.Context, symbol: str):
        """
        Show crypto funding rate & open interest snapshot.
        Usage: !funding BTC-USD
        """
        sym = symbol.upper().strip()
        if not _is_crypto_symbol(sym):
            return await ctx.send("Use a crypto symbol like `BTC-USD` or `ETH-USD`.")

        try:
            b = await self.crypto.bundle(sym, news_limit=0)
            if not b.funding and not b.open_interest:
                return await ctx.send(f"No derivatives data available for `{sym}` right now.")
            lines = []
            if b.funding:
                lines.append(f"**Funding:** {_fmt_pct(b.funding.rate)} "
                             f"(next {b.funding.next_funding_time})")
            if b.open_interest:
                notional = (b.open_interest.amount or 0.0) * (b.quote.prevClose or 0.0 if b.quote else 0.0)
                lines.append(f"**Open Interest:** {b.open_interest.amount:,.0f} "
                             f"(≈ { _fmt_usd(notional) })")
            embed = discord.Embed(
                title=f"Derivatives — {sym}",
                description="\n".join(lines) or "—",
                color=discord.Color.orange(),
                timestamp=b.quote.as_of if b.quote else discord.utils.utcnow(),
            )
            embed.set_footer(text="Binance Futures (public endpoints)")
            await ctx.send(embed=embed)

        except Exception as e:
            await ctx.send(f"⚠️ Error fetching funding/OI for `{sym}`: `{e}`")

    @commands.command(name="expirations")
    async def expirations_cmd(self, ctx: commands.Context, symbol: str):
        """
        List option expirations for a stock (yfinance-backed).
        Usage: !expirations AAPL
        """
        sym = symbol.upper().strip()
        if _is_crypto_symbol(sym):
            return await ctx.send("Options expirations are for equities, not crypto.")

        try:
            exps = await self.stock.option_expirations(sym)
            if not exps:
                return await ctx.send(f"No option expirations found for `{sym}`.")
            # Show the first 10
            lines = [f"- {d:%Y-%m-%d}" for d in exps[:10]]
            more = "" if len(exps) <= 10 else f"\n… and {len(exps)-10} more"
            await ctx.send(f"**{sym} option expirations**\n" + "\n".join(lines) + more)
        except Exception as e:
            await ctx.send(f"⚠️ Error fetching expirations for `{sym}`: `{e}`")

    @commands.command(name="chain")
    async def chain_cmd(self, ctx: commands.Context, symbol: str, expiration: Optional[str] = None):
        """
        Show a quick option chain snapshot (ATM bid/ask & counts).
        Usage: !chain AAPL [YYYY-MM-DD]
        """
        sym = symbol.upper().strip()
        if _is_crypto_symbol(sym):
            return await ctx.send("Options chains are for equities, not crypto.")

        try:
            # pick expiration
            if expiration:
                exp_dt = datetime.fromisoformat(expiration)
            else:
                exps = await self.stock.option_expirations(sym)
                if not exps:
                    return await ctx.send(f"No expirations found for `{sym}`.")
                exp_dt = exps[0]

            chain = await self.stock.option_chain(sym, exp_dt)

            # get prevClose for ATM selection
            b = await self.stock.bundle(sym, bars_lookback=1, news_limit=0)
            px = b.quote.prevClose if b.quote else 0.0

            def closest(lst, x):
                return min(lst, key=lambda s: abs(s.contract.strike - x)) if lst else None

            atm_call = closest(chain.calls, px)
            atm_put  = closest(chain.puts, px)

            desc = [
                f"**Expiration:** {chain.expiration:%Y-%m-%d}",
                f"**Counts:** Calls {len(chain.calls)} | Puts {len(chain.puts)}",
            ]
            if atm_call:
                desc.append(
                    f"**ATM Call {atm_call.contract.strike:.2f}** "
                    f"bid {_fmt_usd(atm_call.quote.bid)} / ask {_fmt_usd(atm_call.quote.ask)} "
                    f"(IV: {atm_call.quote.implied_vol:.3f} if present)"
                )
            if atm_put:
                desc.append(
                    f"**ATM Put  {atm_put.contract.strike:.2f}** "
                    f"bid {_fmt_usd(atm_put.quote.bid)} / ask {_fmt_usd(atm_put.quote.ask)} "
                    f"(IV: {atm_put.quote.implied_vol:.3f} if present)"
                )

            embed = discord.Embed(
                title=f"{sym} — Option chain",
                description="\n".join(desc),
                color=discord.Color.purple(),
            )
            await ctx.send(embed=embed)

        except ValueError:
            await ctx.send("Invalid expiration format. Use `YYYY-MM-DD` (e.g., `!chain AAPL 2025-09-19`).")
        except Exception as e:
            await ctx.send(f"⚠️ Error fetching option chain for `{sym}`: `{e}`")


# -----------------------------------------------------------------------------
# Setup
# -----------------------------------------------------------------------------

async def setup(bot: commands.Bot):
    await bot.add_cog(MarketCog(bot))
    