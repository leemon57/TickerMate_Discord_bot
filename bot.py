import os, sys, logging, httpx, asyncio
from dotenv import load_dotenv
from AI_Module import ai
import discord

logging.basicConfig(level=logging.INFO, stream=sys.stdout)
load_dotenv()

TOKEN = os.getenv("DISCORD_TOKEN")
API_KEY = os.getenv("POLYGON_API_KEY")
if not TOKEN:
    print("No DISCORD_TOKEN found. Check .env")
    raise SystemExit(1)
if not API_KEY:
    print("No POLYGON_API_KEY found. Check .env")
    raise SystemExit(1)

intents = discord.Intents.default()
intents.message_content = True  # <-- REQUIRED for reading messages
client = discord.Client(intents=intents)

async def fetch_prev_close(symbol: str) -> str:
    url = f"https://api.polygon.io/v2/aggs/ticker/{symbol.upper()}/prev"
    params = {"adjusted": "true", "apiKey": API_KEY}
    async with httpx.AsyncClient(timeout=15) as http:
        r = await http.get(url, params=params)
        if r.status_code == 401:
            return "Polygon auth failed (401). Check API key."
        if r.status_code == 403:
            return "Polygon key not authorized for this endpoint (403)."
        if r.status_code == 429:
            return "Rate limited by Polygon (429). Try again later."
        r.raise_for_status()
        data = r.json()
        if not data.get("results"):
            return f"No data for {symbol.upper()}."
        res = data["results"][0]
        c = res["c"]; h = res["h"]; l = res["l"]; v = res["v"]
        return f"{symbol.upper()} prev close: {c:.2f} (H:{h:.2f} L:{l:.2f}) Vol:{int(v):,}"

@client.event
async def on_ready():
    print(f"✅ Logged in as {client.user} (id: {client.user.id})")
    await client.change_presence(status=discord.Status.online,
                                 activity=discord.Game("Booting…"))

# fetching price
@client.event
async def on_message(message: discord.Message):
    if message.author.bot:
        return
    if message.content.startswith("!price"):
        parts = message.content.split()
        if len(parts) != 2:
            await message.channel.send("Usage: `!price AAPL`")
            return
        symbol = parts[1]
        await message.channel.send("Fetching…")
        try:
            reply = await fetch_prev_close(symbol)
        except httpx.HTTPError as e:
            reply = f"HTTP error: {e}"
        except Exception as e:
            reply = f"Unexpected error: {e}"
        await message.channel.send(reply)



client.run(TOKEN)