import os
import asyncio
import discord
from discord.ext import commands

intents = discord.Intents.default()
intents.message_content = True

bot = commands.Bot(command_prefix="!", intents=intents)

@bot.event
async def on_ready():
    print(f"✅ Logged in as {bot.user} (ID: {bot.user.id})")

async def main():
    async with bot:
        # because cog.py lives in the intel package:
        await bot.load_extension("intel.cog")
        await bot.load_extension("charts.cog")
        await bot.load_extension("indicators.indicator_cog")
        await bot.load_extension("ai.ai_cog")
        await bot.start(os.environ["DISCORD_TOKEN"])

if __name__ == "__main__":
    asyncio.run(main())
    