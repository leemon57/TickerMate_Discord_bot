# test_cog.py
import asyncio
import discord
from discord.ext import commands
from config import settings

async def main():
    intents = discord.Intents.default()
    intents.message_content = True
    bot = commands.Bot(command_prefix="!", intents=intents)

    @bot.event
    async def on_ready():
        print(f"✅ Logged in as {bot.user}. Try in your server:\n"
              f"  !price AAPL\n  !news AAPL 3")

    # load only the intel cog
    await bot.load_extension("intel.cog")
    await bot.start(settings.DISCORD_TOKEN)

if __name__ == "__main__":
    asyncio.run(main())
    