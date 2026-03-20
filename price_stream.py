"""
price_stream.py — Binance !miniTicker@arr WebSocket, reconnect/resync logic,
and rate-limited Discord notification queue.

Architecture:
  Binance WS → _handle_ticker_update()  →  AlertCache (hot path, no I/O)
                        │
               (crossover detected)
                        ↓
              asyncio.Queue  →  _process_notification_queue()
                                          ↓
                               Discord channel.send()
                               (rate-limited to config.discord_max_msg_per_sec)

The WS handler never awaits a Discord call directly.
All slow work is either fire-and-forget tasks or queued.

Binance rate limit notes:
  - !miniTicker@arr is a single combined stream — one WS connection for ALL
    symbols. Binance allows 300 connections per IP, and this bot uses exactly 1.
  - The REST /api/v3/ticker/price endpoint has a weight of 4 (all symbols).
    We only call it on startup and reconnect, never on a timer, so we're
    nowhere near the 1200 weight/minute limit.
  - No polling loop anywhere — purely event-driven.
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

if TYPE_CHECKING:
    from healthcheck import HealthServer

logger = logging.getLogger(__name__)

# How long to wait for queued notifications to drain on graceful shutdown
_QUEUE_DRAIN_TIMEOUT = 5.0


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

        # Cancel the WS supervisor first
        if self._ws_task and not self._ws_task.done():
            self._ws_task.cancel()
            try:
                await self._ws_task
            except asyncio.CancelledError:
                pass

        # Drain remaining notifications before stopping the queue consumer
        if not self._queue.empty():
            logger.info(
                "Draining %d pending notifications before shutdown...",
                self._queue.qsize(),
            )
            try:
                await asyncio.wait_for(self._queue.join(), timeout=_QUEUE_DRAIN_TIMEOUT)
            except asyncio.TimeoutError:
                logger.warning("Notification queue drain timed out — some alerts may not have been sent.")

        if self._queue_task and not self._queue_task.done():
            self._queue_task.cancel()
            try:
                await self._queue_task
            except asyncio.CancelledError:
                pass

        self.health.set_ws_ready(False)
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
            total=None,
            sock_read=settings.ws_read_timeout_secs,
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
        except (json.JSONDecodeError, TypeError):
            return

        active_symbols = self.cache.all_symbols
        if not active_symbols:
            return  # Fast exit — no alerts, don't iterate the full ticker list

        for ticker in tickers:
            symbol: str = ticker.get("s", "").upper()
            if symbol not in active_symbols:
                continue

            try:
                current_price = Decimal(ticker["c"])
            except Exception:
                continue

            for alert in self.cache.get_alerts_for_symbol(symbol):
                crossed = check_crossover(alert, current_price)
                if crossed:
                    await self._fire_alert(alert, crossed, current_price)
                else:
                    # Update last_price in cache only — pure in-memory
                    self.cache.update_last_price(
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

        # 1. Update/remove from cache BEFORE enqueuing the notification.
        #    This prevents the double-fire race: if a second WS tick arrives
        #    before the notification is sent, the alert is already gone/reset.
        if repeat:
            await self.cache.set_triggered(alert_id, symbol, new_last)
        else:
            # Deactivate synchronously before any await so subsequent ticks
            # in the same batch don't re-trigger this alert
            await self.cache.deactivate(alert_id, symbol)

        # 2. Enqueue Discord notification (rate-limited consumer below)
        await self._queue.put(
            {
                "alert": dict(alert),  # snapshot taken before mutation
                "direction": direction,
                "price": current_price,
            }
        )

    # ------------------------------------------------------------------
    # Discord notification queue — rate-limited consumer
    # ------------------------------------------------------------------

    async def _run_notification_queue(self) -> None:
        """
        Drain the notification queue at a safe rate.
        Interval enforces discord_max_msg_per_sec, keeping us well under
        Discord's 50 msg/s global hard limit.
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
                    retry_after = getattr(exc, "retry_after", None) or settings.discord_429_backoff_secs
                    logger.warning("Discord 429 — backing off %.1fs.", retry_after)
                    await asyncio.sleep(retry_after)
                else:
                    logger.error("Discord HTTP error sending alert: %s", exc)
            except Exception as exc:
                logger.error("Unexpected error sending notification: %s", exc, exc_info=True)
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
                    alert["channel_id"],
                    alert["id"],
                )
                return
            except discord.Forbidden:
                logger.warning(
                    "No permission to fetch channel %s — skipping.", alert["channel_id"]
                )
                return

        is_above = direction == "above"
        embed = discord.Embed(
            title=(
                f"{'🚀' if is_above else '📉'} "
                f"{'🔁 ' if alert['repeat'] else ''}"
                "Price Alert Triggered"
            ),
            color=discord.Color.green() if is_above else discord.Color.red(),
        )
        embed.add_field(name="Symbol", value=f"`{alert['symbol']}`", inline=True)
        embed.add_field(name="Direction", value=direction.upper(), inline=True)
        embed.add_field(
            name="Target",
            value=f"`${float(alert['target_price']):,.8f}`",
            inline=True,
        )
        embed.add_field(
            name="Triggered At",
            value=f"`${float(price):,.8f}`",
            inline=True,
        )
        embed.add_field(
            name="Repeat Alert",
            value=(
                f"Yes — {settings.repeat_cooldown_secs // 60}-min cooldown"
                if alert["repeat"]
                else "No (alert removed)"
            ),
            inline=True,
        )
        embed.set_footer(text=f"Alert ID #{alert['id']}")

        await channel.send(content=f"<@{alert['user_id']}>", embed=embed)

    # ------------------------------------------------------------------
    # REST price fetch — used on startup + resync after reconnect
    # Binance REST weight: 4 per call (all symbols). Very safe.
    # ------------------------------------------------------------------

    async def fetch_rest_prices(self, symbols: set[str]) -> dict[str, Decimal]:
        """
        Fetch current prices via Binance REST for the given symbol set.
        Returns {SYMBOL: Decimal(price)}.
        """
        if not symbols:
            return {}

        timeout = aiohttp.ClientTimeout(total=15)
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
        3. Update last_price in cache for non-triggered alerts.

        No DB writes — pure in-memory update.
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

        for symbol, current_price in prices.items():
            for alert in self.cache.get_alerts_for_symbol(symbol):
                crossed = check_crossover(alert, current_price)
                if crossed:
                    logger.info(
                        "Missed crossover detected on resync: alert %d (%s %s).",
                        alert["id"],
                        symbol,
                        crossed,
                    )
                    await self._fire_alert(alert, crossed, current_price)
                else:
                    self.cache.update_last_price(
                        alert["id"], symbol, float(current_price)
                    )

        logger.info("Price resync complete.")

    async def _resync_on_reconnect(self) -> None:
        logger.info("Running post-reconnect price resync...")
        await self.resync_prices()
