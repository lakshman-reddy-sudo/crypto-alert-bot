# 🗄️ Supabase Connection String — Complete Step-by-Step Guide

This guide covers everything from creating your Supabase account to
getting the exact connection string the bot needs. Every single click
is documented.

---

## What you need by the end of this guide

A string that looks exactly like this:

```
postgresql://postgres.abcdefghijkl:YourPassword123@aws-0-ap-south-1.pooler.supabase.com:5432/postgres
```

That string is your `SUPABASE_DB_URL`. It goes into GitHub Secrets.

---

## STEP 1 — Create a Supabase Account

1. Open your browser and go to:
   ```
   https://supabase.com
   ```

2. Click the green **"Start your project"** button in the middle of the page

3. You'll see a sign-in screen. You have two options:
   - **"Continue with GitHub"** ← recommended (one click, no password needed)
   - **"Sign up with email"** ← if you prefer email/password

4. If you chose GitHub:
   - Click **"Authorize supabase"**
   - It takes you straight to the Supabase dashboard

5. If you chose email:
   - Enter your email and a password
   - Check your inbox for a confirmation email
   - Click the link in the email
   - You're taken to the dashboard

---

## STEP 2 — Create a New Project

Once you're on the Supabase dashboard:

1. You'll see a screen that says **"New project"** or shows your
   organization name. Click **"New project"**

2. Fill in the form:

   **Name:**
   ```
   crypto-alert-bot
   ```
   (or any name you want — this is just for your reference)

   **Database Password:**
   - Click **"Generate a password"** button
   - A strong random password appears in the box
   - ⚠️ **COPY THIS PASSWORD AND SAVE IT SOMEWHERE RIGHT NOW**
   - You will need it in Step 4
   - If you lose it you'll have to reset it

   **Region:**
   - Click the dropdown
   - Pick the region **closest to you geographically**
   - Examples:
     - India → `Southeast Asia (Singapore)` or `South Asia (Mumbai)` if available
     - US East → `East US (North Virginia)`
     - Europe → `West EU (Ireland)`
   - Closer region = faster database queries

   **Pricing Plan:**
   - Select **"Free"** (it's already selected by default)
   - The free plan gives you 500MB database storage — more than enough

3. Click the green **"Create new project"** button

4. ⏳ Wait. You'll see a loading screen that says:
   ```
   Setting up your project...
   ```
   This takes **1 to 3 minutes**. Don't close the tab.

5. When it's done, you'll see your project dashboard with green
   status indicators. It looks like a database overview page.

---

## STEP 3 — Navigate to the Connection String

This is where most people get confused. Follow these exact clicks:

1. Look at the **left sidebar** (the vertical menu on the left side)

2. Scroll all the way to the **bottom** of the left sidebar

3. Click the **gear icon ⚙️** that says **"Project Settings"**
   - It's at the very bottom of the sidebar
   - Not "Settings" at the top — scroll down to the bottom

4. A new menu appears under Project Settings. Click **"Database"**
   - It's in the sub-menu under Project Settings
   - The full path is: Settings (gear) → Database

5. You're now on the Database Settings page. **Scroll down** on this
   page. You're looking for a section called **"Connection string"**
   - It's roughly in the middle of the page
   - Keep scrolling until you see a box with tabs at the top

---

## STEP 4 — Get the Correct Connection String

You're now looking at the Connection string section. This is the
most important part. Follow carefully:

### 4a — Select the right tab

At the top of the connection string box, you'll see tabs:

```
[ URI ]  [ PSQL ]  [ SQLAlchemy ]  [ Supavisor ]
```

Click **"URI"** — it should already be selected, but make sure.

### 4b — Check the connection mode

⚠️ **This is the step most people get wrong.**

Just above the connection string box, or below the tabs, look for
a section that says something like:

```
Connection pooler
```

Or you might see a dropdown or radio buttons that say:

```
○ Transaction   (port 6543)
● Session       (port 5432)
```

**You MUST select "Session" mode.**

Here's why this matters:
- **Transaction mode (port 6543):** works for most web apps but
  NOT for asyncpg (the library this bot uses). If you use this,
  the bot will crash with a connection error.
- **Session mode (port 5432):** works correctly with asyncpg. ✅

**How to switch to Session mode:**

The Supabase UI changes occasionally. You might see:

**Option A — Dropdown:**
Click the dropdown that shows "Transaction" and change it to "Session"

**Option B — Radio buttons:**
Click the radio button next to "Session mode"

**Option C — Separate URL sections:**
Supabase sometimes shows two separate connection strings labeled
"Transaction" and "Session". Use the one labeled **"Session"**.

**How to confirm you have the right one:**
Look at the URL in the box. It should contain **:5432** near the end:
```
...pooler.supabase.com:5432/postgres
                       ^^^^
                  This must be 5432
```

If you see **:6543**, you're on Transaction mode. Switch to Session.

### 4c — Copy the connection string

1. In the connection string box, you'll see a URL like:
   ```
   postgresql://postgres.abcdefghijkl:[YOUR-PASSWORD]@aws-0-region.pooler.supabase.com:5432/postgres
   ```

2. The URL contains the placeholder `[YOUR-PASSWORD]`
   - Replace this with the database password you saved in Step 2
   - Or click the **"Show password"** toggle/checkbox if available
     (some Supabase versions show the password directly in the URL)

3. The final URL should have your actual password in it, like:
   ```
   postgresql://postgres.abcdefghijkl:MyActualPassword123@aws-0-ap-south-1.pooler.supabase.com:5432/postgres
   ```

4. Click the **copy icon** (two overlapping squares 📋) next to the
   URL box to copy the whole thing

---

## STEP 5 — Verify Your Connection String

Before adding it to GitHub Secrets, double-check these 5 things:

```
postgresql://postgres.abcdefghijkl:YourPassword@aws-0-region.pooler.supabase.com:5432/postgres
     ↑                    ↑              ↑                  ↑                      ↑      ↑
  Starts with        Your project    Your actual        Your region             MUST   Database
 "postgresql://"     reference ID     password                                 be     name is
 NOT "postgres://"   (random chars)  (NOT the         (matches what           5432   "postgres"
                                     placeholder)     you selected)
```

### ✅ Checklist

- [ ] Starts with `postgresql://` (with the **ql** at the end — NOT just `postgres://`)
- [ ] Contains `postgres.` followed by random characters (your project ref)
- [ ] Has your actual password (not the text `[YOUR-PASSWORD]`)
- [ ] Contains `.pooler.supabase.com`
- [ ] Port is `:5432` (not `:6543`)
- [ ] Ends with `/postgres`

### Common mistakes

**Wrong — missing "ql":**
```
❌  postgres://postgres.abc123:pass@host:5432/postgres
✅  postgresql://postgres.abc123:pass@host:5432/postgres
```

**Wrong — still has placeholder:**
```
❌  postgresql://postgres.abc123:[YOUR-PASSWORD]@host:5432/postgres
✅  postgresql://postgres.abc123:MyActualPass@host:5432/postgres
```

**Wrong — Transaction mode port:**
```
❌  postgresql://postgres.abc123:pass@host:6543/postgres
✅  postgresql://postgres.abc123:pass@host:5432/postgres
```

---

## STEP 6 — Add It to GitHub Secrets

Now that you have the correct connection string:

1. Go to your GitHub repository
2. Click the **"Settings"** tab (at the top of the repo page)
3. In the left sidebar, click **"Secrets and variables"**
4. Click **"Actions"**
5. Click the green **"New repository secret"** button
6. Fill in:
   ```
   Name:   SUPABASE_DB_URL
   Secret: postgresql://postgres.abc123:YourPass@host:5432/postgres
   ```
   (paste your actual connection string in the Secret field)
7. Click **"Add secret"**

Done. ✅

---

## STEP 7 — What Happens With This String

When the bot starts up, it uses your connection string to:

1. Open a pool of 2–10 direct PostgreSQL connections to Supabase
2. Create the `alerts` table if it doesn't exist
3. Load all active alerts into memory
4. Write new alerts, updates, and deletions as users interact with the bot

The bot connects directly to PostgreSQL — it does NOT use Supabase's
REST API or JavaScript client. This is why Session mode (port 5432)
is required.

---

## If You Lose Your Database Password

1. Go to Supabase dashboard → your project
2. Left sidebar → gear icon → **"Database"**
3. Scroll up to find **"Database password"** section
4. Click **"Reset database password"**
5. Generate a new one, copy it
6. Update your GitHub Secret `SUPABASE_DB_URL` with the new password
7. Push any commit to `main` to re-deploy the bot with the new password

---

## If the Connection Still Fails

If you see errors like these in Railway logs after deploying:

**Error 1:**
```
asyncpg.exceptions.InvalidAuthorizationSpecificationError
```
→ Wrong password in the connection string. Reset and try again.

**Error 2:**
```
SSL connection required
```
→ The bot requires SSL. Your connection string format is correct
  (asyncpg adds SSL automatically). Check if your Supabase project
  is paused (free tier projects pause after 1 week of inactivity).

**Error 3:**
```
could not connect to server: Connection refused
```
→ Your project might be paused. Go to Supabase dashboard and click
  **"Restore project"** if you see a paused banner.

**Error 4:**
```
connection timeout
```
→ Wrong region or the project is still provisioning. Wait 2–3 minutes
  and try again.

**To unpause a free tier project:**
Supabase pauses free projects after 1 week of no activity.
Go to your Supabase dashboard → you'll see a yellow banner saying
the project is paused → click **"Restore"** → wait 1–2 minutes.

To prevent pausing: upgrade to the Pro plan ($25/month) or keep
the bot running (which makes DB queries regularly, keeping it active).

---

## Quick Visual Reference

```
Supabase Dashboard
│
├── Left Sidebar
│   ├── Table Editor
│   ├── SQL Editor
│   ├── ...other menus...
│   │
│   └── ⚙️ Project Settings    ← CLICK THIS (bottom of sidebar)
│           │
│           └── Database        ← CLICK THIS
│                   │
│                   └── (scroll down on the page)
│                           │
│                           └── Connection string section
│                                   │
│                                   ├── Tabs: [URI] [PSQL] [SQLAlchemy]
│                                   │         ↑
│                                   │    Click URI
│                                   │
│                                   ├── Mode: ● Session (port 5432) ← SELECT THIS
│                                   │         ○ Transaction (port 6543)
│                                   │
│                                   └── postgresql://postgres.xxx:pass@host:5432/postgres
│                                                                                 ↑
│                                                                           Copy this URL
```

---

## Summary

| What to do | Where |
|---|---|
| Create account | https://supabase.com → Start your project |
| Create project | Dashboard → New project → fill in name + password + region |
| Find connection string | Left sidebar → ⚙️ Project Settings → Database → scroll down |
| Select correct tab | Click **URI** tab |
| Select correct mode | Switch to **Session** mode (port **5432**) |
| Copy the URL | Replace `[YOUR-PASSWORD]` with your actual password |
| Add to GitHub | Repo → Settings → Secrets → `SUPABASE_DB_URL` |
