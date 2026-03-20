"""
bot.py — Discord bot entry point and orchestration layer.

Responsibilities:
  - Bootstrap logging and settings validation
  - Initialize DB pool, AlertCache, PriceStream, HealthServer
  - Load the AlertCommands Cog (where all /alert commands live)
  - Coordinate startup sequence and graceful shutdown

All slash commands live in cogs/alert_commands.py.
"""

import asyncio
import logging
import signal

import discord
from discord.ext import commands

import data
from alerts import AlertCache
from config import configure_logging, settings
from healthcheck import HealthServer
from price_stream import PriceStream

# Bootstrap logging immediately — before any other imports log anything
configure_logging()
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Bot & shared singletons
# ---------------------------------------------------------------------------

intents = discord.Intents.default()
bot = commands.Bot(command_prefix="!", intents=intents)
cache = AlertCache()
health = HealthServer()

_price_stream: PriceStream | None = None


# ---------------------------------------------------------------------------
# Lifecycle
# ---------------------------------------------------------------------------

@bot.event
async def on_ready() -> None:
    global _price_stream

    logger.info("Logged in as %s (ID: %s).", bot.user, bot.user.id)

    # 1. DB pool + schema
    await data.init_db()
    health.set_db_ready()

    # 2. Load active alerts into in-memory cache
    all_alerts = await data.load_all_active_alerts()
    await cache.load(all_alerts)
    health.set_cache_loaded(size_fn=lambda: cache.total_alerts)
    logger.info("Loaded %d active alert(s) into cache.", cache.total_alerts)

    # 3. Instantiate PriceStream
    _price_stream = PriceStream(cache, bot, health)

    # 4. Load the AlertCommands Cog
    from cogs.alert_commands import AlertCommands
    if not bot.cogs.get("AlertCommands"):
        await bot.add_cog(AlertCommands(bot, cache, _price_stream))

    # 5. Sync slash commands
    if settings.dev_guild_id:
        guild_obj = discord.Object(id=settings.dev_guild_id)
        bot.tree.copy_global_to(guild=guild_obj)
        synced = await bot.tree.sync(guild=guild_obj)
        logger.info(
            "Dev mode: synced %d command(s) to guild %d.",
            len(synced), settings.dev_guild_id,
        )
    else:
        synced = await bot.tree.sync()
        logger.info("Synced %d slash command(s) globally.", len(synced))

    # 6. Initial REST price resync — fire alerts missed while offline
    await _price_stream.resync_prices()

    # 7. Start WebSocket supervisor + notification queue
    await _price_stream.start()

    # 8. Mark Discord ready — /ready probe returns 200 from here on
    health.set_discord_ready()
    logger.info("Bot fully initialized and ready.")


@bot.event
async def on_close() -> None:
    logger.info("Bot shutting down...")
    if _price_stream:
        await _price_stream.stop()
    await data.close_db()
    await health.stop()


# ---------------------------------------------------------------------------
# Global app command error handler
# ---------------------------------------------------------------------------

@bot.tree.error
async def on_app_command_error(
    interaction: discord.Interaction,
    error: discord.app_commands.AppCommandError,
) -> None:
    logger.error("Unhandled app command error: %s", error, exc_info=True)
    msg = "An unexpected error occurred. Please try again later."
    try:
        if interaction.response.is_done():
            await interaction.followup.send(msg, ephemeral=True)
        else:
            await interaction.response.send_message(msg, ephemeral=True)
    except Exception:
        pass


# ---------------------------------------------------------------------------
# Graceful shutdown on SIGTERM / SIGINT
# ---------------------------------------------------------------------------

def _attach_signal_handlers(loop: asyncio.AbstractEventLoop) -> None:
    async def _shutdown() -> None:
        logger.info("Shutdown signal received.")
        await bot.close()

    for sig in (signal.SIGTERM, signal.SIGINT):
        try:
            loop.add_signal_handler(sig, lambda: asyncio.create_task(_shutdown()))
        except NotImplementedError:
            pass  # Windows does not support loop.add_signal_handler


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    try:
        import uvloop  # type: ignore
        asyncio.set_event_loop_policy(uvloop.EventLoopPolicy())
        logger.info("Using uvloop event loop.")
    except ImportError:
        pass

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    _attach_signal_handlers(loop)

    # Health server starts before Discord connects so the container is
    # immediately reachable for liveness probes during the handshake
    loop.run_until_complete(health.start())

    try:
        loop.run_until_complete(bot.start(settings.discord_token))
    except KeyboardInterrupt:
        pass
    finally:
        loop.run_until_complete(bot.close())
        loop.close()
