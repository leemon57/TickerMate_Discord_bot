# intel/cog.py
from __future__ import annotations

import asyncio
import discord
from discord.ext import commands
from discord import Embed

from .loader import PolygonClient


class IntelCog(commands.Cog):
    """Commands for market intel: prices & headlines (via Polygon)."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.pg = PolygonClient()  # reuse one async HTTP client

    # discord.py doesn't await async cog_unload; schedule the close instead
    def cog_unload(self):
        asyncio.create_task(self.pg.aclose())

    @commands.command(name="price")
    async def price(self, ctx: commands.Context, symbol: str):
        """Show previous close (and H/L/Vol) for a symbol. Usage: !price AAPL"""
        clean = symbol.upper().strip()
        await ctx.send(f"Fetching {clean}…")
        try:
            d = await self.pg.prev_close(clean)
            msg = (
                f"**{clean}** prev close: **{d['c']:.2f}**  "
                f"(H:{d['h']:.2f} • L:{d['l']:.2f})  Vol:{int(d['v']):,}"
            )
            await ctx.send(msg)
        except Exception as e:
            await ctx.send(f"Error fetching price for {clean}: {e}")

    @commands.command(name="news")
    async def news(self, ctx: commands.Context, symbol: str, limit: int = 5):
        """Show latest headlines (with URLs). Usage: !news AAPL 5"""
        clean = symbol.upper().strip()
        limit = max(1, min(int(limit), 10))  # keep it sane
        await ctx.send(f"Fetching {clean} news…")
        try:
            items = await self.pg.news(clean, limit=limit)
            if not items:
                await ctx.send("No recent news found.")
                return

            emb = Embed(title=f"{clean} — Latest Headlines")
            for n in items[:limit]:
                when = n.published_at.strftime("%Y-%m-%d %H:%M UTC")
                # raw URL (<...>) is reliably clickable in Discord
                emb.add_field(
                    name=n.title[:256],  # field name limit
                    value=f"{n.publisher} • {when}\n<{n.url}>",
                    inline=False,
                )

            await ctx.send(embed=emb)
        except Exception as e:
            await ctx.send(f"Error fetching news for {clean}: {e}")


async def setup(bot: commands.Bot):
    """Entry point for discord.py extension loading."""
    await bot.add_cog(IntelCog(bot))
    