"""
price_stream.py — Binance !miniTicker@arr WebSocket, reconnect/resync logic,
                  and rate-limited Discord notification queue.

Architecture:
  Binance WS  →  _handle_ticker_update()  →  AlertCache  (hot path, no I/O)
                         │
                (crossover detected)
                         ↓
           asyncio.Queue  →  _process_notification_queue()
                         ↓
                Discord channel.send()  (rate-limited to config.discord_max_msg_per_sec)

The WS handler never awaits a DB or Discord call directly.
All slow work is either fire-and-forget tasks or queued.
"""

import asyncio
import json
import logging
from decimal import Decimal
from typing import TYPE_CHECKING, Optional

import aiohttp
import discord

from alerts import AlertCache, check_crossover
from config import settings
import data

if TYPE_CHECKING:
    from healthcheck import HealthServer

logger = logging.getLogger(__name__)


class PriceStream:
    """
    Manages the Binance WebSocket connection, automatic reconnects,
    startup/reconnect price resync, and the outgoing Discord alert queue.
    """

    def __init__(
        self,
        cache: AlertCache,
        bot: discord.Client,
        health: "HealthServer",
    ) -> None:
        self.cache = cache
        self.bot = bot
        self.health = health

        self._queue: asyncio.Queue[dict] = asyncio.Queue()
        self._running = False
        self._ws_task: Optional[asyncio.Task] = None
        self._queue_task: Optional[asyncio.Task] = None

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def start(self) -> None:
        self._running = True
        self._queue_task = asyncio.create_task(
            self._run_notification_queue(), name="discord-notify-queue"
        )
        self._ws_task = asyncio.create_task(
            self._ws_supervisor(), name="binance-ws-supervisor"
        )
        logger.info("PriceStream started.")

    async def stop(self) -> None:
        self._running = False
        for task in (self._ws_task, self._queue_task):
            if task and not task.done():
                task.cancel()
        logger.info("PriceStream stopped.")

    # ------------------------------------------------------------------
    # WebSocket supervisor — exponential back-off reconnects
    # ------------------------------------------------------------------

    async def _ws_supervisor(self) -> None:
        delay = settings.ws_reconnect_base_delay
        while self._running:
            try:
                await self._run_websocket()
                delay = settings.ws_reconnect_base_delay  # clean disconnect, reset
            except asyncio.CancelledError:
                return
            except Exception as exc:
                logger.error(
                    "WebSocket error: %s — reconnecting in %.0fs.", exc, delay
                )
            if not self._running:
                return
            self.health.set_ws_ready(False)
            await asyncio.sleep(delay)
            delay = min(delay * 2, settings.ws_reconnect_max_delay)
            await self._resync_on_reconnect()

    async def _run_websocket(self) -> None:
        timeout = aiohttp.ClientTimeout(
            total=None, sock_read=settings.ws_read_timeout_secs
        )
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.ws_connect(
                settings.binance_ws_url,
                heartbeat=settings.ws_heartbeat_secs,
            ) as ws:
                logger.info("Connected to Binance !miniTicker@arr stream.")
                self.health.set_ws_ready(True)
                async for msg in ws:
                    if msg.type == aiohttp.WSMsgType.TEXT:
                        await self._handle_ticker_update(msg.data)
                    elif msg.type == aiohttp.WSMsgType.ERROR:
                        raise ConnectionError(f"WS error frame: {ws.exception()}")
                    elif msg.type in (
                        aiohttp.WSMsgType.CLOSED,
                        aiohttp.WSMsgType.CLOSING,
                    ):
                        logger.warning("Binance WS closed — reconnecting.")
                        return

    # ------------------------------------------------------------------
    # Hot path: called on EVERY tick — must be fast, absolutely no I/O
    # ------------------------------------------------------------------

    async def _handle_ticker_update(self, raw: str) -> None:
        try:
            tickers: list[dict] = json.loads(raw)
        except json.JSONDecodeError:
            return

        active_symbols = self.cache.all_symbols
        for ticker in tickers:
            symbol: str = ticker.get("s", "").upper()
            if symbol not in active_symbols:
                continue

            current_price = Decimal(ticker["c"])
            for alert in self.cache.get_alerts_for_symbol(symbol):
                crossed = check_crossover(alert, current_price)
                if crossed:
                    await self._fire_alert(alert, crossed, current_price)
                else:
                    # Update last_price in cache only — no DB write
                    await self.cache.update_last_price(
                        alert["id"], symbol, float(current_price)
                    )

    # ------------------------------------------------------------------
    # Alert firing
    # ------------------------------------------------------------------

    async def _fire_alert(
        self, alert: dict, direction: str, current_price: Decimal
    ) -> None:
        alert_id: int = alert["id"]
        symbol: str = alert["symbol"]
        repeat: bool = bool(alert.get("repeat", False))
        new_last = float(current_price)

        # 1. Update cache (synchronous — no await needed for float write)
        if repeat:
            await self.cache.set_triggered(alert_id, symbol, new_last)
        else:
            await self.cache.deactivate(alert_id, symbol)

        # 2. Persist to DB — fire-and-forget, never blocks the WS loop
        asyncio.create_task(
            data.mark_alert_triggered(alert_id, new_last, repeat),
            name=f"db-trigger-{alert_id}",
        )

        # 3. Enqueue Discord notification (rate-limited consumer below)
        await self._queue.put(
            {
                "alert":     dict(alert),  # snapshot before potential mutation
                "direction": direction,
                "price":     current_price,
            }
        )

    # ------------------------------------------------------------------
    # Discord notification queue — rate-limited consumer
    # ------------------------------------------------------------------

    async def _run_notification_queue(self) -> None:
        """
        Drain the notification queue at a safe rate.
        Sleep interval enforces the discord_max_msg_per_sec config value,
        keeping us well under Discord's 50 msg/s global hard limit.
        """
        interval = 1.0 / settings.discord_max_msg_per_sec
        while True:
            item = await self._queue.get()
            try:
                await self._send_discord_notification(
                    item["alert"], item["direction"], item["price"]
                )
            except discord.HTTPException as exc:
                if exc.status == 429:
                    retry_after = exc.retry_after or settings.discord_429_backoff_secs
                    logger.warning("Discord 429 — backing off %.1fs.", retry_after)
                    await asyncio.sleep(retry_after)
                else:
                    logger.error("Discord HTTP error sending alert: %s", exc)
            except Exception as exc:
                logger.error("Unexpected error sending notification: %s", exc)
            finally:
                self._queue.task_done()
                await asyncio.sleep(interval)

    async def _send_discord_notification(
        self, alert: dict, direction: str, price: Decimal
    ) -> None:
        channel = self.bot.get_channel(alert["channel_id"])
        if channel is None:
            try:
                channel = await self.bot.fetch_channel(alert["channel_id"])
            except discord.NotFound:
                logger.warning(
                    "Channel %s not found for alert %s — skipping.",
                    alert["channel_id"], alert["id"],
                )
                return

        is_above = direction == "above"
        embed = discord.Embed(
            title=(
                f"{'🚀' if is_above else '📉'}  "
                f"{'🔁 ' if alert['repeat'] else ''}"
                "Price Alert Triggered"
            ),
            color=discord.Color.green() if is_above else discord.Color.red(),
        )
        embed.add_field(name="Symbol",       value=f"`{alert['symbol']}`",                    inline=True)
        embed.add_field(name="Direction",    value=direction.upper(),                          inline=True)
        embed.add_field(name="Target",       value=f"`${float(alert['target_price']):,.8f}`",  inline=True)
        embed.add_field(name="Triggered At", value=f"`${float(price):,.8f}`",                  inline=True)
        embed.add_field(
            name="Repeat Alert",
            value=f"Yes — {settings.repeat_cooldown_secs // 60}-min cooldown" if alert["repeat"] else "No (alert removed)",
            inline=True,
        )
        embed.set_footer(text=f"Alert ID #{alert['id']}")

        await channel.send(content=f"<@{alert['user_id']}>", embed=embed)

    # ------------------------------------------------------------------
    # REST price fetch — used on startup + resync
    # ------------------------------------------------------------------

    async def fetch_rest_prices(self, symbols: set[str]) -> dict[str, Decimal]:
        """
        Fetch current prices via Binance REST for the given symbol set.
        Returns {SYMBOL: Decimal(price)}.
        """
        if not symbols:
            return {}
        timeout = aiohttp.ClientTimeout(total=10)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.get(settings.binance_rest_url) as resp:
                resp.raise_for_status()
                data_list: list[dict] = await resp.json()

        return {
            item["symbol"]: Decimal(item["price"])
            for item in data_list
            if item["symbol"] in symbols
        }

    # ------------------------------------------------------------------
    # Resync — called on startup and after every WS reconnect
    # ------------------------------------------------------------------

    async def resync_prices(self) -> None:
        """
        1. Fetch current REST prices for all tracked symbols.
        2. Check each alert for missed crossovers (happened while offline).
        3. Batch-update last_price in DB for non-triggered alerts.
        """
        symbols = self.cache.all_symbols
        if not symbols:
            return

        logger.info("Resyncing REST prices for %d symbol(s)...", len(symbols))
        try:
            prices = await self.fetch_rest_prices(symbols)
        except Exception as exc:
            logger.error("REST price fetch failed during resync: %s", exc)
            return

        batch_updates: list[tuple[int, float]] = []

        for symbol, current_price in prices.items():
            for alert in self.cache.get_alerts_for_symbol(symbol):
                crossed = check_crossover(alert, current_price)
                if crossed:
                    logger.info(
                        "Missed crossover detected on resync: alert %d (%s %s).",
                        alert["id"], symbol, crossed,
                    )
                    await self._fire_alert(alert, crossed, current_price)
                else:
                    new_lp = float(current_price)
                    await self.cache.update_last_price(alert["id"], symbol, new_lp)
                    batch_updates.append((alert["id"], new_lp))

        # Single bulk write instead of N individual DB calls
        if batch_updates:
            asyncio.create_task(
                data.batch_update_last_prices(batch_updates),
                name="db-batch-last-price",
            )
            logger.info(
                "Queued batch last_price update for %d alert(s).",
                len(batch_updates),
            )

    async def _resync_on_reconnect(self) -> None:
        logger.info("Running post-reconnect price resync...")
        await self.resync_prices()
