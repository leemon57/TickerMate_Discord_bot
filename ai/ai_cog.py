from __future__ import annotations
import json, discord
from discord.ext import commands
from intel.stock_loader import PolygonClient
from intel.crypto_loader import CryptoClient
from ai.analyst import build_fact_pack
from ai.client import analyze

def _is_crypto(sym: str) -> bool:
    s = sym.upper()
    return ("-" in s and s.endswith("USD")) or s.endswith("USDT")

class AICog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.stock = PolygonClient()
        self.crypto = CryptoClient()

    def cog_unload(self):
        self.bot.loop.create_task(self.stock.aclose())
        self.bot.loop.create_task(self.crypto.aclose())

    @commands.command(name="ai")
    async def ai_cmd(self, ctx: commands.Context, symbol: str, horizon: str = "swing", risk: str = "medium"):
        """AI analysis with rating using o3-pro (fallback gpt-4.1). Usage: !ai AAPL [horizon] [risk]"""
        sym = symbol.upper().strip()
        bundle = await (self.crypto.bundle(sym, news_limit=3)
                        if _is_crypto(sym)
                        else self.stock.bundle(sym, bars_timespan="day", bars_lookback=240, news_limit=3))

        facts = build_fact_pack(bundle, horizon=horizon, risk=risk)

        try:
            result = analyze(facts, horizon=horizon, risk=risk)
        except Exception as e:
            return await ctx.send(f"AI analysis failed: {e}")

        # Build a consistent embed
        rating = result.get("rating", 3)
        conf   = result.get("confidence", 0.5)
        desc   = result.get("summary", "—")

        embed = discord.Embed(
            title=f"{sym} — Rating {rating}/5 (conf {conf:.2f})",
            description=desc,
            color=discord.Color.dark_teal()
        )

        embed.set_footer(text="Informational only — not investment advice")
        await ctx.send(embed=embed)

async def setup(bot: commands.Bot):
    await bot.add_cog(AICog(bot))
    