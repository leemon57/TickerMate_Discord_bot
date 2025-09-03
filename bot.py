import asyncio, logging
import discord
from discord.ext import commands
from config import settings

# set up logging
logging.basicConfig(level=logging.INFO)

# setting up bot intents so that it can have accesss to all events
intents = discord.Intents.default()
intents.message_content = True

# create a bot instance
bot = commands.Bot(command_prefix="!", intents=intents)

# list of extensions (cogs) to load
EXTENSIONS = [
    "modules.ai.cog",
    "modules.backtesting.cog",
    "modules.intel.cog",
]

# event handler for when the bot is ready
@bot.event
async def on_ready():
    print(f"✅ Logged in as {bot.user} ({bot.user.id})")

# runs the bot
async def main():
    for ext in EXTENSIONS:
        await bot.load_extension(ext)
    await bot.start(settings.DISCORD_TOKEN)


# entry point for running the bot
if __name__ == "__main__":
    asyncio.run(main())