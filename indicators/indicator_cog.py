from __future__ import annotations
import io
import discord
from discord.ext import commands
from charts.adapters import bars_to_df
from charts.renderers import (
    render_line_with_overlays,  # keep for price + overlays
    render_line_close,          # keep for price-only
    render_series,              # NEW
    render_multi_series,        # NEW
)
from intel.stock_loader import PolygonClient
from intel.crypto_loader import CryptoClient
from indicators.core import sma, ema, rsi, macd, bollinger_bands, atr, stoch, vwap, obv, vol_sma

def _is_crypto(sym: str) -> bool:
    s = sym.upper()
    return ("-" in s and s.endswith("USD")) or s.endswith("USDT")

class IndicatorCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.stock = PolygonClient()
        self.crypto = CryptoClient()

    def cog_unload(self):
        self.bot.loop.create_task(self.stock.aclose())
        self.bot.loop.create_task(self.crypto.aclose())

    async def _df_for(self, symbol: str, span="day", lookback=200):
        if _is_crypto(symbol):
            b = await self.crypto.bundle(symbol, news_limit=0)
        else:
            b = await self.stock.bundle(symbol, bars_timespan=span, bars_lookback=lookback, news_limit=0)
        return bars_to_df(b.bars)

    @commands.command(name="sma")
    async def sma_cmd(self, ctx, symbol: str, n: int = 50, span: str = "day", lookback: int = 200):
        df = await self._df_for(symbol, span, lookback)
        s = sma(df, n)
        png = render_line_with_overlays(df, {f"SMA({n})": s}, title=f"{symbol.upper()} — SMA({n})")
        await ctx.send(file=discord.File(io.BytesIO(png), filename=f"{symbol.upper()}_SMA{n}.png"))

    @commands.command(name="ema")
    async def ema_cmd(self, ctx, symbol: str, n: int = 21, span: str = "day", lookback: int = 200):
        df = await self._df_for(symbol, span, lookback)
        e = ema(df, n)
        png = render_line_with_overlays(df, {f"EMA({n})": e}, title=f"{symbol.upper()} — EMA({n})")
        await ctx.send(file=discord.File(io.BytesIO(png), filename=f"{symbol.upper()}_EMA{n}.png"))

    @commands.command(name="bb")
    async def bb_cmd(self, ctx, symbol: str, n: int = 20, k: float = 2.0, span: str = "day", lookback: int = 200):
        df = await self._df_for(symbol, span, lookback)
        bb = bollinger_bands(df, n=n, k=k)
        overlays = {f"BB mid({n})": bb["mid"], f"BB upper({n},{k})": bb["upper"], f"BB lower({n},{k})": bb["lower"]}
        png = render_line_with_overlays(df, overlays, title=f"{symbol.upper()} — Bollinger Bands")
        await ctx.send(file=discord.File(io.BytesIO(png), filename=f"{symbol.upper()}_BB.png"))

    @commands.command(name="rsi")
    async def rsi_cmd(self, ctx, symbol: str, n: int = 14, span: str = "day", lookback: int = 200):
        df = await self._df_for(symbol, span, lookback)
        series = rsi(df, n)
        # quick single-panel chart for RSI
        png = render_series(series, title=f"{symbol.upper()} — RSI({n})")
        await ctx.send(file=discord.File(io.BytesIO(png), filename=f"{symbol.upper()}_RSI{n}.png"))

    @commands.command(name="macd")
    async def macd_cmd(self, ctx, symbol: str, fast: int = 12, slow: int = 26, signal: int = 9, span: str = "day", lookback: int = 200):
        df = await self._df_for(symbol, span, lookback)
        line, sig, hist = macd(df, fast=fast, slow=slow, signal=signal)
        overlays = {"MACD": line, "Signal": sig, "Hist": hist}
        png = render_multi_series(
            {"MACD": line, "Signal": sig, "Hist": hist},
            title=f"{symbol.upper()} — MACD({fast},{slow},{signal})"
        )
        await ctx.send(file=discord.File(io.BytesIO(png), filename=f"{symbol.upper()}_MACD.png"))

    @commands.command(name="atr")
    async def atr_cmd(self, ctx, symbol: str, n: int = 14, span: str = "day", lookback: int = 200):
        df = await self._df_for(symbol, span, lookback)
        s = atr(df, n)
        png = render_series(s, title=f"{symbol.upper()} — ATR({n})")
        await ctx.send(file=discord.File(io.BytesIO(png), filename=f"{symbol.upper()}_ATR{n}.png"))

    @commands.command(name="vwap")
    async def vwap_cmd(self, ctx, symbol: str, span: str = "day", lookback: int = 200):
        df = await self._df_for(symbol, span, lookback)
        s = vwap(df)
        png = render_line_with_overlays(df, {"VWAP": s}, title=f"{symbol.upper()} — VWAP")
        await ctx.send(file=discord.File(io.BytesIO(png), filename=f"{symbol.upper()}_VWAP.png"))

    @commands.command(name="stoch")
    async def stoch_cmd(self, ctx, symbol: str, k: int = 14, d: int = 3, span: str = "day", lookback: int = 200):
        df = await self._df_for(symbol, span, lookback)
        st = stoch(df, k=k, d=d)
        png = render_multi_series(
            {"%K": st["%K"], "%D": st["%D"]},
            title=f"{symbol.upper()} — Stoch({k},{d})"
        )
        await ctx.send(file=discord.File(io.BytesIO(png), filename=f"{symbol.upper()}_STOCH.png"))

    @commands.command(name="obv")
    async def obv_cmd(self, ctx, symbol: str, span: str = "day", lookback: int = 200):
        df = await self._df_for(symbol, span, lookback)
        s = obv(df)
        png = render_series(s, title=f"{symbol.upper()} — OBV")
        await ctx.send(file=discord.File(io.BytesIO(png), filename=f"{symbol.upper()}_OBV.png"))

async def setup(bot: commands.Bot):
    await bot.add_cog(IndicatorCog(bot))