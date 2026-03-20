"""
cogs/alert_commands.py — All 6 /alert slash commands.

All state lives in AlertCache — no database reads or writes anywhere.
Alert IDs are session-scoped incrementing integers (resets on bot restart).
"""

import logging
from decimal import Decimal, InvalidOperation
from typing import Optional

import discord
from discord import app_commands
from discord.ext import commands

from alerts import AlertCache
from config import settings
from price_stream import PriceStream

logger = logging.getLogger(__name__)

# Valid Binance direction choices
DIRECTION_CHOICES = [
    app_commands.Choice(name="Above target price", value="above"),
    app_commands.Choice(name="Below target price", value="below"),
    app_commands.Choice(name="Both directions", value="both"),
]


class AlertCommands(commands.Cog):
    def __init__(
        self,
        bot: commands.Bot,
        cache: AlertCache,
        price_stream: PriceStream,
    ) -> None:
        self.bot = bot
        self.cache = cache
        self.price_stream = price_stream

    # ------------------------------------------------------------------
    # /alert group
    # ------------------------------------------------------------------

    alert_group = app_commands.Group(
        name="alert",
        description="Manage your crypto price alerts.",
    )

    # ------------------------------------------------------------------
    # /alert add
    # ------------------------------------------------------------------

    @alert_group.command(name="add", description="Create a new price-crossover alert.")
    @app_commands.describe(
        symbol="Binance pair, e.g. BTCUSDT, ETHUSDT",
        direction="Fire when price crosses above, below, or both",
        price="Target price to trigger the alert",
        repeat="Re-fire every few minutes instead of deleting after first trigger",
    )
    @app_commands.choices(direction=DIRECTION_CHOICES)
    async def alert_add(
        self,
        interaction: discord.Interaction,
        symbol: str,
        direction: app_commands.Choice[str],
        price: str,
        repeat: Optional[bool] = False,
    ) -> None:
        await interaction.response.defer(ephemeral=True)

        symbol = symbol.upper().strip()

        # --- Validate price input ---
        try:
            target_price = Decimal(price)
            if target_price <= 0:
                raise ValueError("Price must be positive.")
        except (InvalidOperation, ValueError):
            await interaction.followup.send(
                f"❌ Invalid price `{price}`. Please enter a positive number, e.g. `42000.50`.",
                ephemeral=True,
            )
            return

        # --- Check per-user alert cap ---
        user_alerts = self.cache.get_all_for_user(interaction.user.id)
        if len(user_alerts) >= settings.max_alerts_per_user:
            await interaction.followup.send(
                f"❌ You've reached the maximum of **{settings.max_alerts_per_user}** alerts. "
                f"Remove some with `/alert remove` or `/alert clear` first.",
                ephemeral=True,
            )
            return

        # --- Validate symbol exists on Binance ---
        try:
            prices = await self.price_stream.fetch_rest_prices({symbol})
        except Exception as exc:
            logger.error("Binance REST fetch failed during /alert add: %s", exc)
            await interaction.followup.send(
                "❌ Could not verify the symbol with Binance right now. Try again in a moment.",
                ephemeral=True,
            )
            return

        if symbol not in prices:
            await interaction.followup.send(
                f"❌ `{symbol}` was not found on Binance. "
                f"Check the symbol format (e.g. `BTCUSDT`, `ETHUSDT`, `SOLUSDT`).",
                ephemeral=True,
            )
            return

        current_price = prices[symbol]

        # --- Build and store the alert ---
        alert = {
            # id is assigned by cache.add()
            "user_id": interaction.user.id,
            "channel_id": interaction.channel_id,
            "symbol": symbol,
            "direction": direction.value,
            "target_price": str(target_price),
            "repeat": bool(repeat),
            "paused": False,
            "last_price": float(current_price),  # baseline for crossover detection
            "last_triggered_at": None,
        }

        alert = await self.cache.add(alert)

        embed = discord.Embed(
            title="✅ Alert Created",
            color=discord.Color.green(),
        )
        embed.add_field(name="Alert ID", value=f"`#{alert['id']}`", inline=True)
        embed.add_field(name="Symbol", value=f"`{symbol}`", inline=True)
        embed.add_field(name="Direction", value=direction.name, inline=True)
        embed.add_field(name="Target Price", value=f"`${float(target_price):,.8f}`", inline=True)
        embed.add_field(name="Current Price", value=f"`${float(current_price):,.8f}`", inline=True)
        embed.add_field(
            name="Repeat",
            value=f"Yes ({settings.repeat_cooldown_secs // 60} min cooldown)" if repeat else "No",
            inline=True,
        )
        embed.set_footer(text="Alert is now active. You'll be pinged when it fires.")

        await interaction.followup.send(embed=embed, ephemeral=True)
        logger.info(
            "Alert #%d created: %s %s @ %s (user %d, repeat=%s)",
            alert["id"], symbol, direction.value, target_price,
            interaction.user.id, repeat,
        )

    # ------------------------------------------------------------------
    # /alert list
    # ------------------------------------------------------------------

    @alert_group.command(name="list", description="See all your active alerts.")
    async def alert_list(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer(ephemeral=True)

        user_alerts = self.cache.get_all_for_user(interaction.user.id)

        if not user_alerts:
            await interaction.followup.send(
                "📭 You have no active alerts. Use `/alert add` to create one.",
                ephemeral=True,
            )
            return

        embed = discord.Embed(
            title=f"📋 Your Alerts ({len(user_alerts)}/{settings.max_alerts_per_user})",
            color=discord.Color.blue(),
        )

        for alert in sorted(user_alerts, key=lambda a: a["id"]):
            status = "⏸ Paused" if alert.get("paused") else "✅ Active"
            repeat_str = f"🔁 {settings.repeat_cooldown_secs // 60}m cooldown" if alert["repeat"] else "One-shot"
            embed.add_field(
                name=f"#{alert['id']} — {alert['symbol']}",
                value=(
                    f"**Direction:** {alert['direction'].upper()}\n"
                    f"**Target:** `${float(alert['target_price']):,.8f}`\n"
                    f"**Repeat:** {repeat_str}\n"
                    f"**Status:** {status}"
                ),
                inline=True,
            )

        await interaction.followup.send(embed=embed, ephemeral=True)

    # ------------------------------------------------------------------
    # /alert remove
    # ------------------------------------------------------------------

    @alert_group.command(name="remove", description="Delete one of your alerts.")
    @app_commands.describe(id="The alert ID shown in /alert list")
    async def alert_remove(
        self, interaction: discord.Interaction, id: int
    ) -> None:
        await interaction.response.defer(ephemeral=True)

        alert = self.cache.find_alert(id, interaction.user.id)
        if not alert:
            await interaction.followup.send(
                f"❌ No alert with ID `#{id}` found. Use `/alert list` to see your alerts.",
                ephemeral=True,
            )
            return

        symbol = self.cache.find_symbol_by_alert_id(id)
        await self.cache.remove(id, symbol)

        await interaction.followup.send(
            f"🗑️ Alert `#{id}` ({alert['symbol']} {alert['direction'].upper()} @ "
            f"`${float(alert['target_price']):,.8f}`) has been removed.",
            ephemeral=True,
        )

    # ------------------------------------------------------------------
    # /alert clear
    # ------------------------------------------------------------------

    @alert_group.command(name="clear", description="Delete ALL your alerts.")
    async def alert_clear(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer(ephemeral=True)

        removed = await self.cache.remove_all_for_user(interaction.user.id)

        if removed == 0:
            await interaction.followup.send(
                "📭 You had no alerts to clear.", ephemeral=True
            )
        else:
            await interaction.followup.send(
                f"🗑️ Cleared **{removed}** alert(s).", ephemeral=True
            )

    # ------------------------------------------------------------------
    # /alert pause
    # ------------------------------------------------------------------

    @alert_group.command(name="pause", description="Suspend an alert without deleting it.")
    @app_commands.describe(id="The alert ID shown in /alert list")
    async def alert_pause(
        self, interaction: discord.Interaction, id: int
    ) -> None:
        await interaction.response.defer(ephemeral=True)

        alert = self.cache.find_alert(id, interaction.user.id)
        if not alert:
            await interaction.followup.send(
                f"❌ No alert with ID `#{id}` found.", ephemeral=True
            )
            return

        if alert.get("paused"):
            await interaction.followup.send(
                f"⏸ Alert `#{id}` is already paused. Use `/alert resume` to re-activate it.",
                ephemeral=True,
            )
            return

        symbol = self.cache.find_symbol_by_alert_id(id)
        await self.cache.set_paused(id, symbol, paused=True)

        await interaction.followup.send(
            f"⏸ Alert `#{id}` ({alert['symbol']}) is now **paused**.",
            ephemeral=True,
        )

    # ------------------------------------------------------------------
    # /alert resume
    # ------------------------------------------------------------------

    @alert_group.command(name="resume", description="Re-activate a paused alert.")
    @app_commands.describe(id="The alert ID shown in /alert list")
    async def alert_resume(
        self, interaction: discord.Interaction, id: int
    ) -> None:
        await interaction.response.defer(ephemeral=True)

        alert = self.cache.find_alert(id, interaction.user.id)
        if not alert:
            await interaction.followup.send(
                f"❌ No alert with ID `#{id}` found.", ephemeral=True
            )
            return

        if not alert.get("paused"):
            await interaction.followup.send(
                f"✅ Alert `#{id}` is already active.", ephemeral=True
            )
            return

        symbol = self.cache.find_symbol_by_alert_id(id)

        # Re-fetch current price to reset the baseline so the alert doesn't
        # immediately misfire based on a stale last_price from before the pause
        try:
            prices = await self.price_stream.fetch_rest_prices({alert["symbol"]})
            if alert["symbol"] in prices:
                self.cache.update_last_price(
                    id, alert["symbol"], float(prices[alert["symbol"]])
                )
        except Exception as exc:
            logger.warning("Could not refresh price on resume for alert #%d: %s", id, exc)

        await self.cache.set_paused(id, symbol, paused=False)

        await interaction.followup.send(
            f"▶️ Alert `#{id}` ({alert['symbol']}) is now **active** again.",
            ephemeral=True,
        )
