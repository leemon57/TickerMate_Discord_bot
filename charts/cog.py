from __future__ import annotations
import io
import discord
from discord.ext import commands

from charts import (
    bars_to_df,
    df_to_csv_bytes,
    render_line_close,
    render_candles,
    resample_df,
)
from intel.stock_loader import PolygonClient
from intel.crypto_loader import CryptoClient


def _is_crypto(sym: str) -> bool:
    s = sym.upper()
    return ("-" in s and s.endswith("USD")) or s.endswith("USDT")


class ChartCog(commands.Cog):
    """Render charts and export CSV for stocks & crypto."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.stock = PolygonClient()
        self.crypto = CryptoClient()

    def cog_unload(self):
        # close clients gracefully
        self.bot.loop.create_task(self.stock.aclose())
        self.bot.loop.create_task(self.crypto.aclose())

    @commands.command(name="chart")
    async def chart_cmd(
        self,
        ctx: commands.Context,
        symbol: str,
        kind: str = "line",
        span: str = "day",
        lookback: int = 180,
        resample: str | None = None,
    ):
        """
        Render a PNG chart.
        Usage: !chart AAPL [line|candle] [day|week|month] [lookback] [resample? H|D|W|M]
        Examples:
          !chart AAPL
          !chart AAPL candle day 180
          !chart BTC-USD line day 90 H
        """
        sym = symbol.upper().strip()

        if _is_crypto(sym):
            b = await self.crypto.bundle(sym, news_limit=0)
        else:
            b = await self.stock.bundle(
                sym, bars_timespan=span, bars_lookback=lookback, news_limit=0
            )

        df = bars_to_df(b.bars)
        if resample:
            df = resample_df(df, resample)

        title = f"{sym} — {span} x {lookback}" + (f" ({resample})" if resample else "")
        try:
            if kind.lower().startswith("cand"):
                png = render_candles(df, title=title)
            else:
                png = render_line_close(df, title=title)
        except ValueError as e:
            return await ctx.send(f"No data to chart for `{sym}`: {e}")

        await ctx.send(file=discord.File(io.BytesIO(png), filename=f"{sym}_{kind}.png"))

    @commands.command(name="csv")
    async def csv_cmd(
        self,
        ctx: commands.Context,
        symbol: str,
        span: str = "day",
        lookback: int = 180,
        resample: str | None = None,
    ):
        """Export OHLCV to CSV. Usage: !csv AAPL [day|week|month] [lookback] [resample? H|D|W|M]"""
        sym = symbol.upper().strip()

        if _is_crypto(sym):
            b = await self.crypto.bundle(sym, news_limit=0)
        else:
            b = await self.stock.bundle(
                sym, bars_timespan=span, bars_lookback=lookback, news_limit=0
            )

        df = bars_to_df(b.bars)
        if resample:
            df = resample_df(df, resample)
        data = df_to_csv_bytes(df)
        await ctx.send(
            file=discord.File(io.BytesIO(data), filename=f"{sym}_{span}.csv")
        )


# --- REQUIRED entry point for discord.py 2.x ---
async def setup(bot: commands.Bot):
    await bot.add_cog(ChartCog(bot))
