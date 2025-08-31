import os
import asyncio
from datetime import datetime, timedelta, timezone
from dotenv import load_dotenv

import yfinance as yf
import discord
from discord import app_commands
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from openai import OpenAI

load_dotenv()
DISCORD_TOKEN   = os.getenv("DISCORD_TOKEN")
OPENAI_API_KEY  = os.getenv("OPENAI_API_KEY")
DAILY_CHANNEL_ID = int(os.getenv("DAILY_CHANNEL_ID", "0"))
POST_HOUR       = int(os.getenv("POST_HOUR", "16"))
POST_MINUTE     = int(os.getenv("POST_MINUTE", "10"))

print("DISCORD_TOKEN:", os.getenv("DISCORD_TOKEN"))
print("OPENAI_API_KEY:", os.getenv("OPENAI_API_KEY"))
print("DAILY_CHANNEL_ID:", os.getenv("DAILY_CHANNEL_ID"))
print("POST_HOUR:", os.getenv("POST_HOUR"))
print("POST_MINUTE:", os.getenv("POST_MINUTE"))

# --- OpenAI client (Responses API) ---
client = OpenAI(api_key=OPENAI_API_KEY)

# --- Discord client & tree for slash commands ---
intents = discord.Intents.default()
bot = discord.Client(intents=intents)
tree = app_commands.CommandTree(bot)

# --- Helpers ---------------------------------------------------------------

def fetch_quote(symbol: str):
    """Fetch latest daily OHLC and percent change using yfinance."""
    ticker = yf.Ticker(symbol)
    hist = ticker.history(period="5d", interval="1d")
    if hist.empty:
        raise ValueError(f"No data for {symbol}")

    last = hist.iloc[-1]
    # If markets are open, intraday price may be in 'currentPrice'; fallback to Close
    price = float(last["Close"])
    open_ = float(last["Open"])
    high  = float(last["High"])
    low   = float(last["Low"])
    change_pct = ((price - open_) / open_) * 100 if open_ != 0 else 0.0
    return {
        "symbol": symbol.upper(),
        "price": price,
        "open": open_,
        "high": high,
        "low": low,
        "change_pct": change_pct,
        "date": hist.index[-1].strftime("%Y-%m-%d")
    }

def summarize_with_chatgpt(title: str, bullet_items: list[str]) -> str:
    """Ask ChatGPT to turn raw bullets into a concise Discord-friendly post."""
    prompt = f"""Write a concise, upbeat Discord post titled "{title}".
Use short bullets. Emphasize notable movers and risk disclaimers. Keep to ~6 bullets.
Bullets:
{chr(10).join('- ' + b for b in bullet_items)}
"""
    # Responses API (recommended); simple text output
    # Docs: https://platform.openai.com/docs/api-reference/responses
    resp = client.responses.create(
        model="gpt-4o-mini",  # swap to your preferred model
        input=prompt,
    )
    return resp.output_text

async def post_daily_wrap(channel: discord.TextChannel):
    """Collect a market snapshot and post a ChatGPT-written wrap."""
    # Customize the tickers you care about:
    tickers = ["SPY", "QQQ", "AAPL", "MSFT", "NVDA", "TSLA"]
    bullets = []
    for t in tickers:
        try:
            q = fetch_quote(t)
            bullets.append(
                f"{q['symbol']}: ${q['price']:.2f} "
                f"(Open {q['open']:.2f}, H {q['high']:.2f}, L {q['low']:.2f}, "
                f"{q['change_pct']:+.2f}% vs open) [{q['date']}]"
            )
        except Exception as e:
            bullets.append(f"{t}: data error ({e})")

    text = summarize_with_chatgpt(
        title=f"Daily Market Wrap • {datetime.now().strftime('%Y-%m-%d')}",
        bullet_items=bullets
    )
    await channel.send(text)

# --- Slash command: /stock SYMBOL -----------------------------------------

@tree.command(name="stock", description="Get a quick summary for a stock (e.g., /stock AAPL)")
@app_commands.describe(symbol="Ticker symbol, e.g., AAPL")
async def stock(interaction: discord.Interaction, symbol: str):
    await interaction.response.defer(thinking=True)
    try:
        q = fetch_quote(symbol)
        bullets = [
            f"{q['symbol']} on {q['date']}",
            f"Last: ${q['price']:.2f}",
            f"Open: {q['open']:.2f} • High: {q['high']:.2f} • Low: {q['low']:.2f}",
            f"Change vs open: {q['change_pct']:+.2f}%",
            "Note: Data is delayed and for education only."
        ]
        text = summarize_with_chatgpt(
            title=f"{q['symbol']} Snapshot",
            bullet_items=bullets
        )
        await interaction.followup.send(text)
    except Exception as e:
        await interaction.followup.send(f"Could not fetch {symbol}: {e}")

# --- Scheduler (daily post) ------------------------------------------------

scheduler = AsyncIOScheduler()

@bot.event
async def on_ready():
    await tree.sync()
    print(f"Logged in as {bot.user} (latency {bot.latency:.3f}s)")
    # Schedule the job at your local (server) time. For Eastern Time posting,
    # consider running the host in ET or convert appropriately.
    scheduler.start()

    async def job_wrapper():
        channel = bot.get_channel(DAILY_CHANNEL_ID)
        if isinstance(channel, discord.TextChannel):
            await post_daily_wrap(channel)

    # Run every weekday at POST_HOUR:POST_MINUTE. Adjust to DAILY if you prefer.
    scheduler.add_job(
        lambda: asyncio.create_task(job_wrapper()),
        trigger="cron",
        day_of_week="mon-fri",
        hour=POST_HOUR,
        minute=POST_MINUTE,
        timezone="America/Toronto"  # keep in sync with your target audience
    )

bot.run(DISCORD_TOKEN)
