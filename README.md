# 🤖 Crypto Price Alert Discord Bot

A production-ready, fully async Discord bot for real-time crypto price alerts —
powered by **Binance WebSocket**, **discord.py v2 slash commands**, and deployed
on **Render**. Zero database. Zero polling. Pure event-driven.

---

## 💡 Why I Built This

I was paper trading crypto and forex on a brokerage platform that capped me at
**20 price alerts**. That's not enough when you're watching multiple pairs across
different timeframes.

So I built my own — unlimited alerts, instant crossover detection, and a clean
Discord interface I can use from anywhere.

---

## ⚡ How It Works

```
Binance !miniTicker@arr WebSocket   ←   single stream, ALL symbols (~2000+)
        │
        ▼  (every ~1 second, per symbol)
  price_stream.py
  └── _handle_ticker_update()       pure in-memory check, zero I/O
          └── check_crossover()     Decimal math, no side effects
                  │
          (price crossed target)
                  ↓
          asyncio.Queue  →  Discord channel.send()
                             rate-limited to 5 msg/sec

  AlertCache                        symbol → alert_id → alert dict
  asyncio.Lock on writes            lock-free on hot-path reads
```

**Crossover logic** — alerts only fire when price *crosses* the target, not just touches it:

```
last_price < target  AND  current >= target  →  fires ABOVE
last_price > target  AND  current <= target  →  fires BELOW
```

---

## 🎮 Slash Commands

| Command | What it does |
|---|---|
| `/alert add symbol direction price [repeat]` | Create a price-crossover alert |
| `/alert list` | See all your active alerts |
| `/alert remove id` | Delete one alert |
| `/alert clear` | Delete all your alerts |
| `/alert pause id` | Suspend an alert without deleting it |
| `/alert resume id` | Re-activate a paused alert |

**Symbol format:** Any Binance pair — `BTCUSDT`, `ETHUSDT`, `SOLUSDT`, `XAUUSDT`

**Direction choices:**
- `Above target price` — fires when price rises through your target
- `Below target price` — fires when price falls through your target
- `Both directions` — fires on either cross

**Repeat flag:** if `True`, re-fires every 5 minutes instead of deleting after first trigger.

---

## 📡 What Binance Provides

| Feature | Detail |
|---|---|
| WebSocket stream | `!miniTicker@arr` — all symbols, ~1s updates |
| Symbols available | ~2000+ trading pairs |
| REST endpoint | `/api/v3/ticker/price` — used for startup price sync |
| Connection limit | 300 WebSocket connections per IP (this bot uses 1) |
| REST weight | 4 per full ticker fetch — well within 1200/min limit |
| Cost | Completely free — no API key needed for market data |

---

## 🏗️ Architecture

```
crypto-alert-bot/
├── bot.py                 Entry point, lifecycle, signal handling
├── alerts.py              In-memory AlertCache + crossover logic
├── price_stream.py        Binance WebSocket, reconnect, alert queue
├── config.py              All env vars validated at startup
├── healthcheck.py         /health  /ready  /metrics  HTTP server
├── cogs/
│   └── alert_commands.py  All 6 slash commands
├── Dockerfile
├── render.yaml
└── requirements.txt
```

---

## 🚀 Deploy to Render (5 minutes)

1. Fork this repo
2. Go to [render.com](https://render.com) → New → **Web Service**
3. Connect your GitHub repo
4. Set `DISCORD_TOKEN` in the Environment tab
5. Deploy — bot is online in ~2 minutes

**Required environment variable:**

| Variable | Where to get it |
|---|---|
| `DISCORD_TOKEN` | Discord Developer Portal → Your App → Bot → Reset Token |

**Optional:**

| Variable | Default | Description |
|---|---|---|
| `DEV_GUILD_ID` | (empty) | Your server ID for instant slash command sync |
| `MAX_ALERTS_PER_USER` | `50` | Per-user alert cap |
| `REPEAT_COOLDOWN_SECS` | `300` | Seconds between repeat alert fires |
| `BINANCE_WS_URL` | Binance vision URL | Override if geo-blocked |
| `LOG_LEVEL` | `INFO` | Set to `DEBUG` for verbose logs |

---

## 🔑 Discord Bot Setup

1. Go to [discord.com/developers/applications](https://discord.com/developers/applications)
2. New Application → Bot → copy token
3. OAuth2 → URL Generator → scopes: `bot` + `applications.commands`
4. Permissions: `Send Messages`, `Embed Links`, `Read Message History`
5. Invite bot to your server with the generated URL

---

## 🩺 Health Endpoints

| Endpoint | Returns 200 when... |
|---|---|
| `/health` | Process is alive |
| `/ready` | Discord connected + Binance WS active |
| `/metrics` | Always (Prometheus format) |

---

## 💰 Running Cost

| Service | Cost |
|---|---|
| Render Web Service | Free tier / ~$7/month paid |
| Binance market data | Free (no API key needed) |
| Discord bot | Free |
| **Total** | **$0 on free tier** |

---

## 🛠️ Tech Stack

- **Python 3.12**
- **discord.py v2** — slash commands, embeds
- **aiohttp** — async WebSocket + REST
- **uvloop** — 2x faster event loop on Linux
- **Render** — deployment platform
