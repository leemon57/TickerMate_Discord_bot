from discord.ext import commands
from .loader import PolygonClient


# Define a COg for all "intel" commands
class IntelCog(commands.Cog):
    def __init__(self, bot):
        # keep a reference to the main bot
        self.bot = bot
        # create one PolygonClient instance to reuse across commands
        self.pg = PolygonClient()

    async def cog_unload(self):
        await self.pg.aclose()

    # Define a command: !price SYMBOL
    @commands.command(name="price")
    async def price(self, ctx, symbol: str):
        # Send a quick response so the user knows the bot is working
        await ctx.send("Fetching…")
        try:
            # Ask Polygon for the previous close data
            d = await self.pg.prev_close(symbol)
            # Send the nicely formatted result back to Discord
            await ctx.send(f"{symbol.upper()} prev close: {d['c']:.2f} (H:{d['h']:.2f} L:{d['l']:.2f}) Vol:{int(d['v']):,}")
        except Exception as e:
            # If something goes wrong (bad ticker, API down, etc.), show the error
            await ctx.send(f"Error: {e}")

    # Define another command: !sma SYMBOL [WINDOW]
    @commands.command(name="sma")
    async def sma(self, ctx, symbol: str, window: int = 20):
        await ctx.send(f"Calculating SMA({window})…")
        try:
            # Ask Polygon for SMA values
            j = await self.pg.sma(symbol, window=window)
            vals = j.get("results", {}).get("values", [])
            if not vals:
                await ctx.send("No SMA data.")
                return
            # Send the most recent SMA value
            await ctx.send(f"{symbol.upper()} SMA({window}) latest: {vals[-1]['value']:.2f}")
        except Exception as e:
            # Handle and show errors cleanly
            await ctx.send(f"Error: {e}")

# Entry point required by discord.py for loading this cog as an extension
async def setup(bot):
    await bot.add_cog(IntelCog(bot))
