import os, sys, logging
from dotenv import load_dotenv
import discord

logging.basicConfig(level=logging.INFO, stream=sys.stdout)
load_dotenv()

TOKEN = os.getenv("DISCORD_TOKEN")
if not TOKEN:
    print("No DISCORD_TOKEN found. Check .env")
    raise SystemExit(1)

intents = discord.Intents.default()
client = discord.Client(intents=intents)

@client.event
async def on_ready():
    print(f"✅ Logged in as {client.user} (id: {client.user.id})")
    # Set a visible presence so you can see it change
    await client.change_presence(status=discord.Status.online, activity=discord.Game("Booting…"))

client.run(TOKEN)
