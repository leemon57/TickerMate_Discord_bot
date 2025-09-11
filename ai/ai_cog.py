from __future__ import annotations
import json
import traceback
import discord
from discord.ext import commands

# loaders
from intel.stock_loader import PolygonClient
from intel.crypto_loader import CryptoClient

# AI pipeline
from ai.analyst import build_fact_pack
from ai.client import analyze


def _is_crypto(sym: str) -> bool:
    s = sym.upper()
    return ("-" in s and s.endswith("USD")) or s.endswith("USDT")


def _fmt_json(d: dict | list | None, limit_list: int | None = None) -> str:
    if d is None:
        return "-"
    if isinstance(d, list) and limit_list is not None:
        d = d[:limit_list]
    try:
        return json.dumps(d, separators=(",", ":"))
    except Exception:
        return str(d)


class AICog(commands.Cog):
    """AI market analyst: rating, action, entry/exit plan."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.stock = PolygonClient()
        self.crypto = CryptoClient()

    def cog_unload(self):
        # Close async clients gracefully
        self.bot.loop.create_task(self.stock.aclose())
        self.bot.loop.create_task(self.crypto.aclose())

    # --- quick sanity command -------------------------------------------------
    @commands.command(name="pingai")
    async def pingai(self, ctx: commands.Context):
        await ctx.send("AI cog is loaded ✅")

    # --- main command ---------------------------------------------------------
    @commands.command(name="ai")
    async def ai_cmd(
        self,
        ctx: commands.Context,
        symbol: str,
        horizon: str = "swing",    # intraday | swing | position
        risk: str = "medium",      # low | medium | high
    ):
        """
        Usage: !ai SYMBOL [horizon] [risk]
        Example: !ai AAPL swing medium
                 !ai BTC-USD position low
        """
        sym = symbol.upper().strip()

        # Fetch bundle (stocks include events; crypto doesn't need events_limit)
        try:
            if _is_crypto(sym):
                bundle = await self.crypto.bundle(sym, news_limit=3)
            else:
                bundle = await self.stock.bundle(
                    sym,
                    bars_timespan="day",
                    bars_lookback=240,
                    news_limit=3,
                    events_limit=25,   # ensure earnings/divs are fetched
                )
        except Exception as e:
            err = f"Data load failed for {sym}: {e}"
            await ctx.send(err)
            return

        # Build facts and ask the model
        try:
            facts = build_fact_pack(bundle, horizon=horizon, risk=risk)
        except Exception as e:
            await ctx.send(f"Failed to build facts for {sym}: {e}")
            return

        try:
            result = analyze(facts, horizon=horizon, risk=risk)
        except Exception as e:
            # Show a short message; log details server-side if you keep logs
            await ctx.send(f"AI analysis failed: {e}")
            return

        # ---- Hardening / fallbacks ------------------------------------------
        # Ensure levels exist (fallback to our computed ones inside facts)
        if not result.get("levels") or \
           not result["levels"].get("support") or \
           not result["levels"].get("resistance"):
            result["levels"] = facts.get("levels", result.get("levels", {}))

        # Derive action if model omitted (schema should prevent this, but be safe)
        rating = int(result.get("rating", 3))
        conf = float(result.get("confidence", 0.5))
        action = result.get("action")
        if action not in ("buy", "hold", "sell"):
            if rating >= 4 and conf >= 0.65:
                action = "buy"
            elif rating <= 2 and conf >= 0.65:
                action = "sell"
            else:
                action = "hold"
            result["action"] = action

        # ---- Build the embed -------------------------------------------------
        desc = result.get("summary", "—")
        color = (
            discord.Color.green()
            if action == "buy"
            else discord.Color.red()
            if action == "sell"
            else discord.Color.blurple()
        )

        embed = discord.Embed(
            title=f"{sym} — {action.upper()} | Rating {rating}/5 (conf {conf:.2f})",
            description=desc,
            color=color,
        )

        # Core sections
        embed.add_field(
            name="Trend",
            value=_fmt_json(result.get("trend", {})),
            inline=False,
        )
        embed.add_field(
            name="Levels",
            value=_fmt_json(result.get("levels", {})),
            inline=False,
        )

        # Entry / Exit plans
        ep = result.get("entry_plan", {})
        xp = result.get("exit_plan", {})

        # Pretty-print entries/stops/targets while staying robust
        def _fmt_nums(arr, places=2, max_n=3):
            if not isinstance(arr, list):
                return "-"
            arr = [a for a in arr if isinstance(a, (int, float))][:max_n]
            if not arr:
                return "-"
            return ", ".join(f"{a:.{places}f}" for a in arr)

        if ep:
            entries = _fmt_nums(ep.get("entries"), 2, 2)
            ep_notes = ep.get("notes", "")
            ep_method = ep.get("method", "-")
            embed.add_field(
                name="Entry Plan",
                value=f"Method: {ep_method}\nEntries: {entries}\n{ep_notes}".strip(),
                inline=False,
            )

        if xp:
            stops = _fmt_nums(xp.get("stops"), 2, 2)
            targets = _fmt_nums(xp.get("targets"), 2, 3)
            xp_notes = xp.get("notes", "")
            embed.add_field(
                name="Exit Plan",
                value=f"Stops: {stops}\nTargets: {targets}\n{xp_notes}".strip(),
                inline=False,
            )

        # Optional sections (only if present)
        optional_blocks = [
            ("Bull Signals", "signals_bull"),
            ("Bear Signals", "signals_bear"),
            ("Derivs", "derivs"),
            ("Events", "events"),
            ("News", "news"),
            ("Risks", "risk_notes"),
        ]
        for title, key in optional_blocks:
            val = result.get(key)
            if not val:
                continue
            if isinstance(val, list):
                bullets = "• " + "\n• ".join(map(str, val[:4]))
                embed.add_field(name=title, value=bullets, inline=False)
            else:
                embed.add_field(name=title, value=_fmt_json(val), inline=False)

        embed.set_footer(text="Informational only — not investment advice")

        # Send it!
        try:
            await ctx.send(embed=embed)
        except discord.Forbidden:
            await ctx.send("I need **Embed Links** permission in this channel to show the analysis.")
        except Exception:
            # As a last resort, send plain text if embed failed
            fallback = (
                f"{sym} — {action.upper()} | Rating {rating}/5 (conf {conf:.2f})\n"
                f"{desc}\n"
                f"Levels: {result.get('levels')}\n"
                f"Entry: {result.get('entry_plan')}\n"
                f"Exit: {result.get('exit_plan')}\n"
                "Informational only — not investment advice"
            )
            await ctx.send(fallback)
            traceback.print_exc()


async def setup(bot: commands.Bot):
    await bot.add_cog(AICog(bot))
    