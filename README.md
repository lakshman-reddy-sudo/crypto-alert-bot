# 🤖 Crypto Price Alert Discord Bot

A production-ready, fully async Discord bot for real-time crypto price
alerts — powered by **Binance WebSocket**, **discord.py v2 slash commands**,
**asyncpg + Supabase (PostgreSQL)**, auto-deployed to **Railway** via
**GitHub Actions**. Zero installs on your PC. Push to GitHub → bot updates itself.

---

## 📁 Complete File Structure

```
crypto-alert-bot/
│
├── 🤖 Core Bot
│   ├── bot.py                        Entry point, lifecycle, signal handling
│   ├── alerts.py                     In-memory AlertCache + crossover logic
│   ├── data.py                       asyncpg pool, schema, all DB queries
│   ├── price_stream.py               Binance WebSocket, reconnect, alert queue
│   ├── config.py                     All env vars validated at startup
│   └── healthcheck.py                /health  /ready  /metrics  HTTP server
│
├── 📂 cogs/
│   ├── __init__.py
│   └── alert_commands.py             All 6 slash commands as a discord.py Cog
│
├── 📂 migrations/
│   ├── migrate.py                    Versioned SQL migration runner
│   ├── 0001_initial_schema.sql       Creates alerts table + indexes
│   └── 0002_add_paused_column.sql    Adds pause/resume support
│
├── 📂 tests/
│   ├── __init__.py
│   ├── conftest.py                   Shared fixtures, env stubs
│   ├── test_crossover.py             40+ crossover logic unit tests
│   └── test_cache.py                 AlertCache async unit tests
│
├── 📂 .github/
│   ├── PULL_REQUEST_TEMPLATE.md
│   └── workflows/
│       ├── ci.yml                    Lint + test on every push
│       └── deploy.yml                Auto-deploy to Railway on push to main
│
├── 📄 Documentation
│   ├── README.md                     ← you are here
│   ├── DEPLOY.md                     Full deployment guide (GitHub + Railway)
│   ├── BOT_COMMANDS.md               How to use all bot commands
│   └── SUPABASE_CONNECTION_GUIDE.md  Step-by-step Supabase setup
│
├── 🐳 Docker / Infra
│   ├── Dockerfile                    Multi-stage production image
│   ├── docker-compose.yml            Bot + optional Prometheus + Grafana
│   ├── prometheus.yml                Prometheus scrape config
│   └── railway.toml                  Railway deployment config
│
└── ⚙️ Config
    ├── requirements.txt
    ├── pytest.ini
    ├── Makefile
    ├── .env.example                  All supported environment variables
    ├── .gitignore
    └── .dockerignore
```

---

## ⚡ How It Works

```
Binance !miniTicker@arr WebSocket  ←  single global stream, all symbols
        │
        ▼  (every ~1 second, per symbol)
  price_stream.py
  └── _handle_ticker_update()        NO I/O — pure in-memory check
          └── check_crossover()      Decimal math, zero side effects
                  │
          (price crossed target)
                  ▼
          asyncio.Queue  →  Discord channel.send()
                             rate-limited to 10 msg/sec

  alerts.py  AlertCache              symbol → alert_id → alert dict
             Lock on writes          Lock-free on hot-path reads

  data.py    asyncpg pool            DB writes ONLY on:
             ssl=require               create / delete / trigger / pause

  config.py  Settings                All env vars, validated at import
  healthcheck.py                     /health  /ready  /metrics
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

**Symbol format:** Binance pair name, no separators — `BTCUSDT`, `ETHUSDT`, `SOLUSDT`

**Direction choices:**
- `Above target price` — fires when price rises through your target
- `Below target price` — fires when price falls through your target
- `Both directions` — fires on either cross

**Repeat flag:** if `True`, re-fires every 5 minutes instead of deleting after first trigger.

> Full command guide with examples → **`BOT_COMMANDS.md`**

---

## 🚀 Deployment (Zero Local Install)

Every push to `main` automatically:
1. Runs lint + all unit tests
2. Builds Docker image → pushes to GitHub Container Registry
3. Deploys to Railway
4. Health-checks `/ready` before marking deploy live

You only need a browser. Nothing installs on your PC.

> Full step-by-step guide → **`DEPLOY.md`**
> Supabase connection string guide → **`SUPABASE_CONNECTION_GUIDE.md`**

---

## 🔑 Required GitHub Secrets

Go to: **GitHub repo → Settings → Secrets and variables → Actions**

| Secret | Where to get it |
|---|---|
| `DISCORD_TOKEN` | Discord Developer Portal → Your App → Bot → Reset Token |
| `SUPABASE_DB_URL` | Supabase → Project Settings → Database → URI tab → Session mode (port 5432) |
| `RAILWAY_TOKEN` | Railway → Account Settings → Tokens → New Token |

Optional secrets (all have sensible defaults):

| Secret | Default | Description |
|---|---|---|
| `DEV_GUILD_ID` | (empty) | Your server ID for instant command sync during dev |
| `REPEAT_COOLDOWN_SECS` | `300` | Seconds between repeat alert fires |
| `MAX_ALERTS_PER_USER` | `50` | Per-user alert cap |
| `LOG_FORMAT` | `json` | `json` for Railway, `text` for local dev |
| `LOG_LEVEL` | `INFO` | `DEBUG` for verbose logs |

---

## 📋 One-Time Setup Checklist

- [ ] **1. Fork / push repo to GitHub**
- [ ] **2. Create Discord bot** — Developer Portal → New Application → Bot → copy token
- [ ] **3. Invite bot to server** — OAuth2 → URL Generator → scopes: `bot` + `applications.commands` → permissions: Send Messages, Embed Links, Read Message History
- [ ] **4. Create Supabase project** — free tier, copy Session mode URI (port 5432)
- [ ] **5. Create Railway project** — connect GitHub repo, copy Railway token
- [ ] **6. Add 3 GitHub Secrets** — `DISCORD_TOKEN`, `SUPABASE_DB_URL`, `RAILWAY_TOKEN`
- [ ] **7. Push to main** — triggers first auto-deploy (~5 min)
- [ ] **8. Run migrations** — Railway shell → `python migrations/migrate.py`
- [ ] **9. Verify** — bot appears online in Discord, try `/alert add`

---

## 🩺 Health Endpoints

Once deployed, Railway exposes these at your service URL:

| Endpoint | Returns 200 when... | Use for |
|---|---|---|
| `/health` | Process is alive | Docker liveness probe |
| `/ready` | Discord + DB + WS + cache all up | Docker readiness probe |
| `/metrics` | Always | Prometheus scraping |

```bash
# Check if bot is fully ready
curl https://your-service.railway.app/ready

# Response when everything is healthy:
# {"ready": true, "components": {"discord": true, "database": true, "websocket": true, "cache": true}, "uptime_seconds": 3600.0}
```

---

## 🧪 Running Tests Locally

Tests are fully in-memory — no real Discord, DB, or Binance connection needed.

```bash
# Install deps
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# Run all tests
pytest tests/ -v

# With coverage
pytest tests/ -v --cov=. --cov-report=term-missing
```

---

## 🗃️ Database Migrations

```bash
# See what's been applied
python migrations/migrate.py --status

# Apply pending migrations
python migrations/migrate.py

# Preview without applying
python migrations/migrate.py --dry-run
```

To add a new migration, create a file in `migrations/`:
```
migrations/0003_your_description.sql
```
It will be picked up and applied automatically on next run.

---

## 💰 Running Costs

| Service | Cost |
|---|---|
| GitHub Actions | Free (2,000 min/month on free plan) |
| Railway Hobby | ~$5/month (bot uses ~100MB RAM, near-zero CPU) |
| Supabase Free | $0 (500MB storage, handles tens of thousands of alerts) |
| **Total** | **~$5/month** |

---

## 📚 Read Next

| File | What's in it |
|---|---|
| `DEPLOY.md` | Full 9-part deployment walkthrough, troubleshooting, rollback guide |
| `BOT_COMMANDS.md` | Every command explained with examples, FAQ, common mistakes |
| `SUPABASE_CONNECTION_GUIDE.md` | Exactly how to get your DB connection string, step by step |
