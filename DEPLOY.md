# 🚀 Full Deployment Guide — GitHub + Railway

**Goal:** Your bot runs 24/7 in the cloud. You never install Python,
Docker, or anything on your PC. Every time you push a change to GitHub,
the bot automatically updates itself.

---

## What You Will Set Up

```
┌─────────────────────────────────────────────────────────────────┐
│                        THE FULL PICTURE                         │
│                                                                 │
│   You (browser only)                                            │
│        │                                                        │
│        │  git push  (or edit file on GitHub.com)               │
│        ▼                                                        │
│   ┌─────────────┐                                              │
│   │   GitHub    │  stores your code + encrypted secrets        │
│   │   Repo      │                                              │
│   └──────┬──────┘                                              │
│          │  triggers automatically                              │
│          ▼                                                      │
│   ┌─────────────┐                                              │
│   │   GitHub    │  Step 1: runs your tests (lint + pytest)     │
│   │   Actions   │  Step 2: builds Docker image                 │
│   │   (CI/CD)   │  Step 3: deploys to Railway                  │
│   └──────┬──────┘                                              │
│          │  deploys automatically if tests pass                 │
│          ▼                                                      │
│   ┌─────────────┐         ┌─────────────┐                     │
│   │   Railway   │────────▶│  Supabase   │                     │
│   │  (bot runs  │         │ (database)  │                     │
│   │   24/7)     │         └─────────────┘                     │
│   └──────┬──────┘                                              │
│          │  sends messages                                      │
│          ▼                                                      │
│   ┌─────────────┐                                              │
│   │   Discord   │  your server, your users                     │
│   └─────────────┘                                              │
└─────────────────────────────────────────────────────────────────┘
```

**Services used (all free tiers work):**
- **GitHub** — stores the code, runs CI/CD pipelines
- **Railway** — runs the bot 24/7 (Hobby plan ~$5/month, free trial available)
- **Supabase** — PostgreSQL database (free tier: 500MB, more than enough)
- **Discord Developer Portal** — bot token (always free)

---

## PART 1 — One-Time Account Setup

### 1.1 — Create a GitHub Account

If you don't have one: https://github.com/signup

Use a real email — GitHub will send you a verification link.

---

### 1.2 — Create a Discord Bot

**Go to:** https://discord.com/developers/applications

1. Click **"New Application"** (top right)
2. Give it a name like `CryptoAlertBot` → click **Create**
3. In the left sidebar click **"Bot"**
4. Click **"Add Bot"** → confirm with **"Yes, do it!"**
5. Under **"Token"** → click **"Reset Token"** → confirm → click **"Copy"**

   > ⚠️ **This is your `DISCORD_TOKEN`. Save it somewhere safe right now.**
   > You can only see it once. If you lose it, you have to reset it again.

6. Scroll down to **"Privileged Gateway Intents"**
   - Leave all three toggles **OFF** (the bot doesn't need them)

7. In the left sidebar click **"OAuth2"** → **"URL Generator"**
8. Under **"Scopes"** tick: `bot` and `applications.commands`
9. Under **"Bot Permissions"** tick:
   - `Send Messages`
   - `Embed Links`
   - `Read Message History`
10. Scroll to the bottom, copy the generated URL
11. Open that URL in a new tab → select your server → click **Authorize**

Your bot now appears in your server's member list (shown as offline — that's
normal, it's not running yet).

---

### 1.3 — Create a Supabase Database

**Go to:** https://supabase.com

1. Click **"Start your project"** → sign in with GitHub (recommended)
2. Click **"New project"**
3. Fill in:
   - **Name:** `crypto-alert-bot` (or anything you like)
   - **Database Password:** click "Generate a password" → **copy and save it**
   - **Region:** pick the one closest to you geographically
4. Click **"Create new project"** → wait 1–2 minutes for it to provision

**Getting the connection string:**

1. Left sidebar → **"Project Settings"** (gear icon at the bottom)
2. Click **"Database"**
3. Scroll down to **"Connection string"**
4. Click the **"URI"** tab
5. Under **"Connection pooler"** make sure **"Session mode"** is selected

   > ⚠️ This is critical. The port must be **5432**.
   > If you see port 6543, you're on Transaction mode — switch to Session mode.

6. You'll see something like:
   ```
   postgresql://postgres.abcdefgh:[YOUR-PASSWORD]@aws-0-ap-south-1.pooler.supabase.com:5432/postgres
   ```
7. Replace `[YOUR-PASSWORD]` with the password you saved in step 3
8. Copy the full URI

   > ⚠️ **This is your `SUPABASE_DB_URL`. Save it.**

---

### 1.4 — Create a Railway Account

**Go to:** https://railway.app

1. Click **"Login"** → **"Login with GitHub"**
   - Using GitHub login is important — it's how Railway gets permission
     to deploy from your repo
2. Authorize Railway to access your GitHub account
3. You'll land on the Railway dashboard

**Create a project:**

1. Click **"New Project"**
2. Click **"Empty Project"**
3. Click **"Add a Service"** → **"GitHub Repo"**
4. If prompted, click **"Configure GitHub App"** → give Railway access to
   your specific repo (or all repos)
5. Select your `crypto-alert-bot` repo

   > ⚠️ **Do NOT click Deploy yet.** Stop here. You'll come back after
   > adding secrets in Step 2.

**Get your Railway token:**

1. Click your profile picture (top right)
2. Click **"Account Settings"**
3. Left sidebar → **"Tokens"**
4. Click **"New Token"**
5. Name it `github-actions`
6. Copy the token

   > ⚠️ **This is your `RAILWAY_TOKEN`. Save it.**

---

## PART 2 — Push Your Code to GitHub

### 2.1 — Create the GitHub repository

1. Go to https://github.com/new
2. Fill in:
   - **Repository name:** `crypto-alert-bot`
   - **Visibility:** Private (recommended — keeps your configs private)
   - Leave everything else default
3. Click **"Create repository"**

---

### 2.2 — Upload your code

**Option A: Using Git (if you have it):**

```bash
cd crypto_alert_bot       # navigate to the project folder
git init
git add .
git commit -m "initial commit"
git branch -M main
git remote add origin https://github.com/YOUR_USERNAME/crypto-alert-bot.git
git push -u origin main
```

**Option B: Drag and drop on GitHub (no terminal needed):**

1. On the empty repo page, click **"uploading an existing file"**
2. Drag all the project files into the browser window
3. Make sure you include the hidden folders:
   - `.github/` (the whole folder with `workflows/` inside)
   - `.gitignore`
   - `.env.example`
   - `.dockerignore`
4. Scroll down → click **"Commit changes"**

> ⚠️ **NEVER upload your `.env` file.** Only upload `.env.example`.
> Your real secrets go into GitHub Secrets (next step), not the repo.

---

## PART 3 — Add Secrets to GitHub

This is the most important step. Your bot token and database URL are
stored as encrypted GitHub Secrets — they never appear in your code or
logs, and Railway receives them automatically on every deploy.

**Go to:** Your GitHub repo → **Settings** tab → **Secrets and variables**
→ **Actions** → **New repository secret**

Add each secret one at a time:

### Required Secrets (you must add these)

---

**Secret 1:**
```
Name:   DISCORD_TOKEN
Value:  (paste your Discord bot token from Step 1.2)
```

---

**Secret 2:**
```
Name:   SUPABASE_DB_URL
Value:  (paste your full postgresql:// URI from Step 1.3)
```

Example of what it should look like:
```
postgresql://postgres.abcdefgh:YourPassword123@aws-0-ap-south-1.pooler.supabase.com:5432/postgres
```

---

**Secret 3:**
```
Name:   RAILWAY_TOKEN
Value:  (paste your Railway token from Step 1.4)
```

---

### Optional Secrets (add these to customise behaviour)

**DEV_GUILD_ID** — Your Discord server's ID. Causes slash commands to
appear instantly in your server instead of waiting up to 1 hour for
global propagation. Highly recommended during setup.

How to get your server ID:
1. In Discord, go to Settings → Advanced → turn on **Developer Mode**
2. Right-click your server icon → **"Copy Server ID"**

```
Name:   DEV_GUILD_ID
Value:  (your server's ID, e.g. 1234567890123456789)
```

---

Other optional secrets:

| Secret Name | What it does | Example value |
|---|---|---|
| `REPEAT_COOLDOWN_SECS` | Minutes between repeat alert fires | `300` |
| `MAX_ALERTS_PER_USER` | Max alerts per Discord user | `50` |
| `LOG_LEVEL` | How detailed the logs are | `INFO` or `DEBUG` |

---

## PART 4 — Trigger Your First Deploy

### 4.1 — Make a small commit to trigger the pipeline

The deploy workflow runs automatically when you push to `main`. Since you
already pushed the code in Part 2, you just need to trigger it again by
making any small change.

**On GitHub.com (no terminal needed):**
1. Open your repo
2. Click on `README.md`
3. Click the pencil icon (Edit)
4. Add a space anywhere
5. Click **"Commit changes"** → **"Commit directly to main"** → **Commit**

This triggers the GitHub Actions pipeline.

---

### 4.2 — Watch the pipeline run

1. Go to your GitHub repo → **"Actions"** tab
2. You'll see a workflow run called **"CI"** starting
3. Click on it to watch in real time

The pipeline runs in this order:

```
CI Workflow
├── lint        (~30 seconds)
│   └── checks code quality with ruff
└── test        (~60 seconds)
    └── runs all unit tests (no real secrets needed)

Deploy Workflow (starts automatically if CI passes)
├── ci-gate     (re-runs CI as a safety check)
├── build       (~2-4 minutes)
│   ├── builds Docker image
│   └── pushes to GitHub Container Registry
└── deploy      (~1-2 minutes)
    ├── runs railway up
    └── syncs your secrets to Railway
```

Total time for first deploy: **4–8 minutes**
After first deploy (Docker cache is warm): **60–90 seconds**

---

### 4.3 — Run database migrations

After the first deploy, the bot is running but the database tables
don't exist yet. You need to run migrations once.

**Using Railway's web shell:**
1. Go to https://railway.app → your project → your service
2. Click the **"Shell"** button (looks like `>_`)
3. Type these commands:

```bash
python migrations/migrate.py --status
```

You should see:
```
VERSION     STATUS        FILENAME
------------------------------------------------------------
1           ✗ pending     0001_initial_schema.sql
2           ✗ pending     0002_add_paused_column.sql
```

Then run:
```bash
python migrations/migrate.py
```

You should see:
```
✓ Applied 0001_initial_schema.sql
✓ Applied 0002_add_paused_column.sql
Migration complete. 2 new migration(s) applied.
```

> After this one-time step, future migrations apply automatically
> if you add them to the deploy flow (see Part 6).

---

### 4.4 — Verify the bot is alive

**In Railway logs:**
1. Railway → your project → your service → **"Logs"** tab
2. You should see:

```
Using uvloop event loop.
Health server listening on 0.0.0.0:8080
asyncpg pool initialized (min=2, max=10).
Loaded 0 active alert(s) into cache.
Resyncing REST prices for 0 symbol(s)...
Connected to Binance !miniTicker@arr stream.
Synced 6 slash command(s) globally.
Bot fully initialized and ready.
```

**In Discord:**
- Your bot should now show as **online** (green dot) in your server
- Go to any channel where the bot has access
- Type `/alert` — you should see the command dropdown appear

---

## PART 5 — Understanding the Full Workflow

### What happens on every push to `main`

```
You push a commit
       │
       ▼
GitHub Actions starts "CI" workflow
       │
       ├── Lint check (ruff)
       │       │ FAIL → workflow stops, no deploy happens, you get an email
       │       │ PASS ↓
       │
       └── Test suite (pytest)
               │ FAIL → workflow stops, no deploy happens
               │ PASS ↓
               ▼
       GitHub Actions starts "Deploy" workflow
               │
               ├── Build Docker image
               │       Uses layer cache → fast after first time
               │
               ├── Push image to ghcr.io (GitHub's container registry)
               │
               └── Deploy to Railway
                       │
                       ├── Railway pulls the new image
                       ├── Starts new container
                       ├── Health check: waits for /ready to return 200
                       │       (this means Discord + DB + WS all connected)
                       └── Old container stops → new one takes over
                               Zero downtime for active alerts
```

### What happens on a push to any OTHER branch

```
You push to feature/my-change
       │
       ▼
GitHub Actions starts "CI" workflow only
       │
       ├── Lint check
       └── Test suite
               │ PASS → green checkmark, nothing deployed
               │ FAIL → red X, you see what broke
```

This means you can safely experiment on branches without ever
breaking the live bot.

### What happens if a test fails

The deploy **does not happen**. Railway never sees the bad code.
You get an email from GitHub and a red X on the commit. Fix the
issue, push again, and the pipeline retries automatically.

### What happens if Railway goes down

Railway has ~99.9% uptime. If it ever restarts your container, the
bot reconnects automatically:
1. Connects to Binance WebSocket
2. Fetches current prices via REST
3. Compares against stored `last_price` in Supabase
4. Fires any alerts that crossed while offline
5. Resumes normal operation

No alerts are missed.

---

## PART 6 — Automating Migrations on Every Deploy

Right now you ran migrations manually from the Railway shell. To make
future migrations automatic (run before every deploy), change one line
in `railway.toml`:

```toml
[deploy]
# Change this line:
startCommand = "python -u bot.py"

# To this:
startCommand = "python migrations/migrate.py && python -u bot.py"
```

Commit and push. Now every deploy automatically applies any new migration
files before starting the bot. It's safe to do this because `migrate.py`
skips migrations that have already been applied.

---

## PART 7 — Day-to-Day Management

### Viewing logs

Railway → your project → your service → **Logs** tab

You can filter logs by keyword. Useful searches:
- `ERROR` — see only errors
- `crossover` — see when alerts fire
- `reconnect` — see WebSocket reconnects

### Restarting the bot manually

Railway → your project → your service → three dots menu → **Restart**

### Rolling back a bad deploy

**Option A (GitHub — easiest):**
1. Go to your repo → **Commits** tab
2. Find the last good commit
3. Click the three dots → **Revert**
4. Merge the revert PR → pipeline auto-deploys the old version

**Option B (Railway):**
1. Railway → your service → **Deployments** tab
2. Find the last successful deployment
3. Click the three dots → **Redeploy**

### Checking bot health

Railway exposes your service on a public URL. Open it and add `/ready`:

```
https://your-service-name.railway.app/ready
```

You'll see:
```json
{
  "ready": true,
  "components": {
    "discord": true,
    "database": true,
    "websocket": true,
    "cache": true
  },
  "uptime_seconds": 14523.4
}
```

If any component shows `false`, check the Railway logs for errors.

### Adding a new environment variable

1. GitHub repo → Settings → Secrets and variables → Actions
2. Add the new secret
3. Push any commit to `main` — the deploy workflow syncs secrets to Railway automatically

Or add it directly in Railway:
Railway → your service → **Variables** tab → **New Variable**

### Monitoring with Prometheus + Grafana (advanced, optional)

If you want a dashboard showing alert counts, uptime, and WebSocket
status, you can run the monitoring stack locally:

```bash
docker compose --profile monitoring up -d
```

Then open http://localhost:3000 (Grafana) and add Prometheus as a
data source pointing to http://localhost:9090.

The `/metrics` endpoint on the bot (port 8080) exposes:
- `crypto_alert_bot_uptime_seconds`
- `crypto_alert_bot_active_alerts`
- `crypto_alert_bot_ws_ready`
- `crypto_alert_bot_discord_ready`

---

## PART 8 — Cost & Scaling

### Railway pricing

| Plan | Cost | What you get |
|---|---|---|
| Free trial | $5 credit | Enough for ~1 month of testing |
| Hobby | ~$5/month | 8GB RAM, 8 vCPU, always on |
| Pro | ~$20/month | More resources, team features |

The bot uses roughly:
- **RAM:** 80–150MB (mostly the asyncpg pool + alert cache)
- **CPU:** Near 0% at rest, small spikes when alerts fire
- **Bandwidth:** ~50–100MB/day (Binance WebSocket stream)

The Hobby plan is more than sufficient for thousands of active alerts.

### Supabase free tier limits

| Resource | Free limit | Bot usage |
|---|---|---|
| Database size | 500MB | ~1MB per 10,000 alerts |
| Connections | 60 | Bot uses 2–10 (asyncpg pool) |
| Bandwidth | 5GB/month | Very low (DB only written on state changes) |

You will not hit these limits unless you have tens of thousands of
active alerts. Even then, upgrading Supabase is cheap (~$25/month).

---

## PART 9 — Troubleshooting

### Bot is offline in Discord after deploy

Check Railway logs for:
```
[FATAL] Missing required environment variable: DISCORD_TOKEN
```
→ Your secret wasn't synced. Go to Railway → your service → Variables
  and add `DISCORD_TOKEN` manually.

---

### Slash commands not appearing in Discord

Two possible causes:

**A) Commands haven't propagated yet (global sync)**
Global slash command sync takes up to 1 hour. Set `DEV_GUILD_ID`
in GitHub Secrets to get instant sync for your server.

**B) Bot doesn't have the `applications.commands` scope**
Re-invite the bot using a new OAuth2 URL with both `bot` and
`applications.commands` scopes checked.

---

### "SSL connection required" error in Railway logs

```
asyncpg.exceptions.InvalidAuthorizationSpecificationError: ...
```

→ Your `SUPABASE_DB_URL` might be using the wrong format.
  Make sure it starts with `postgresql://` (not `postgres://`)
  and the port is `5432`.

---

### Railway deploy fails with "service not found"

The Railway CLI command references `--service crypto-alert-bot`.
If you named your Railway service something different:

1. Go to Railway → your project → your service → Settings
2. Copy the exact service name
3. Update `deploy.yml` line:
   ```yaml
   railway up --service YOUR-ACTUAL-SERVICE-NAME --detach
   ```

---

### Tests pass locally but fail in GitHub Actions

The most common cause is a missing env var in the CI workflow.
Check `ci.yml` — it stubs `DISCORD_TOKEN` and `SUPABASE_DB_URL`.
If you added a new `_require()` call in `config.py`, add the
corresponding stub to the `env:` section of the test step in `ci.yml`.

---

### Price alerts not firing

1. Check Railway logs for `Missed crossover detected on resync` — this
   means the bot caught it on reconnect (working correctly).
2. Check `/alert list` — alert might be paused (⏸️ icon).
3. Check the `last_price` shown in `/alert list`. If it's on the
   wrong side of your target, the price never actually crossed.

---

## Quick Reference Card

| Task | Where to do it |
|---|---|
| Change bot token | GitHub Secrets → `DISCORD_TOKEN` + push to main |
| Change DB password | Supabase → reset password → update `SUPABASE_DB_URL` secret + push |
| See live logs | Railway → service → Logs tab |
| Restart bot | Railway → service → ⋯ → Restart |
| Roll back deploy | Railway → service → Deployments → Redeploy old version |
| Add new feature | Push to a branch → test → merge PR to main → auto-deploys |
| Apply new migration | Add SQL file to `migrations/` → push to main |
| Check health | `https://your-service.railway.app/ready` |
| See active alerts count | `https://your-service.railway.app/metrics` |
