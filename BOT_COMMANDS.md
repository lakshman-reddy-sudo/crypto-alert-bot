# 📖 Bot Commands — Complete User Guide

Everything you need to know about using the Crypto Price Alert Bot
in your Discord server. No technical knowledge required.

---

## Table of Contents

1. [Getting Started](#getting-started)
2. [How Alerts Work](#how-alerts-work)
3. [Command Reference](#command-reference)
   - [/alert add](#alert-add)
   - [/alert list](#alert-list)
   - [/alert remove](#alert-remove)
   - [/alert clear](#alert-clear)
   - [/alert pause](#alert-pause)
   - [/alert resume](#alert-resume)
4. [Alert Notifications](#alert-notifications)
5. [Tips & Best Practices](#tips--best-practices)
6. [Common Mistakes](#common-mistakes)
7. [FAQ](#faq)

---

## Getting Started

Once the bot is in your server and online (shown with a green dot), type
`/alert` in any channel where the bot has permission to read and send messages.

Discord will show you a dropdown of all available commands as you type.

> **Important:** All bot responses are **ephemeral** — only YOU can see them.
> Nobody else in the channel sees your alerts, prices, or settings.

---

## How Alerts Work

The bot connects to Binance's live price feed and watches your target prices
in real time. Alerts work on a **crossover** model:

```
ABOVE alert:
  last known price ──────────── crosses UP ──────→ target price
  Example: BTC was $69,000 → now hits $70,000 → FIRES ✅

BELOW alert:
  last known price ──────────── crosses DOWN ──→ target price
  Example: BTC was $71,000 → now hits $70,000 → FIRES ✅

BOTH alert:
  Fires on EITHER a cross above OR a cross below the same target.
```

**The alert only fires ONCE per crossover.** If you set a $70,000 alert and BTC
goes from $69k → $71k → $73k, it fires exactly once when it crosses $70k.
It does NOT fire again unless the price dips back below $70k and crosses
up again (for a `repeat` alert — see below).

---

## Command Reference

---

### `/alert add`

**Creates a new price alert.**

```
/alert add symbol:<pair> direction:<direction> price:<number> repeat:<true/false>
```

#### Parameters

| Parameter | Required | Description |
|---|---|---|
| `symbol` | ✅ Yes | The Binance trading pair. Must be exact. See examples below. |
| `direction` | ✅ Yes | Choose from the dropdown: Above, Below, or Both |
| `price` | ✅ Yes | The target price that triggers the alert |
| `repeat` | ❌ Optional | `True` = re-fires every 5 minutes while condition holds. Default: `False` |

#### Symbol Format

The symbol is the **Binance trading pair name**, always written as
`BASE + QUOTE` with no slash, space, or dash:

| What you want to track | Symbol to use |
|---|---|
| Bitcoin priced in USDT | `BTCUSDT` |
| Ethereum priced in USDT | `ETHUSDT` |
| Solana priced in USDT | `SOLUSDT` |
| BNB priced in USDT | `BNBUSDT` |
| Dogecoin priced in USDT | `DOGEUSDT` |
| Shiba Inu priced in USDT | `SHIBUSDT` |
| Bitcoin priced in BNB | `BTCBNB` |
| ETH priced in BTC | `ETHBTC` |

> **Rule of thumb:** if you can find it on Binance's markets page, the
> symbol is just the pair name with no separator, all uppercase.

#### Direction Options

When you click the `direction` field, Discord shows you a dropdown:

```
▸ Above target price   → fires when price rises THROUGH your target
▸ Below target price   → fires when price falls THROUGH your target
▸ Both directions      → fires on EITHER a rise or fall through your target
```

#### Price Format

Enter a plain number. You can use decimals. Do NOT use commas, currency
symbols, or letters:

```
✅ Correct:    70000        65000.50      0.00002500
❌ Wrong:      $70,000      70.000,50     70k
```

#### The `repeat` Flag

| Setting | Behaviour |
|---|---|
| `False` (default) | Alert fires once, then is automatically deleted |
| `True` | Alert fires, waits 5 minutes, then can fire again if still crossed |

Use `repeat: True` for things like "notify me every 5 minutes while BTC is
below $60k", or for ongoing monitoring of a volatile coin.

#### Examples

**Alert when BTC crosses above $70,000 (fires once):**
```
/alert add  symbol:BTCUSDT  direction:Above target price  price:70000
```

**Alert when ETH drops below $3,000 (fires once):**
```
/alert add  symbol:ETHUSDT  direction:Below target price  price:3000
```

**Alert when SOL crosses $200 in either direction (fires once):**
```
/alert add  symbol:SOLUSDT  direction:Both directions  price:200
```

**Repeating alert — notify every 5 min while BTC is above $100k:**
```
/alert add  symbol:BTCUSDT  direction:Above target price  price:100000  repeat:True
```

**Alert on a very small-cap coin:**
```
/alert add  symbol:SHIBUSDT  direction:Above target price  price:0.000030
```

#### What you'll see after creating an alert

The bot replies with a confirmation card showing:

```
✅ Alert #7 Created
────────────────────────────────
Symbol        BTCUSDT
Direction     🔼 ABOVE
Target Price  $70,000.00000000
Current Price $69,342.15000000
Repeat        No — fires once
────────────────────────────────
You'll be @mentioned in this channel when the alert fires.
```

The alert ID (e.g. `#7`) is what you use to remove or pause it later.

---

### `/alert list`

**Shows all your currently active alerts.**

```
/alert list
```

No parameters needed. The bot replies with a card showing up to 24 of your
active alerts. Each entry shows:

```
#7 — BTCUSDT  🔼
Target:    $70,000.00000000
Last seen: $69,342.15000000
```

#### Status icons

| Icon | Meaning |
|---|---|
| 🔼 | Alert fires when price goes ABOVE target |
| 🔽 | Alert fires when price goes BELOW target |
| ↕️ | Alert fires in BOTH directions |
| 🔁 | Repeat mode is ON |
| ⏸️ | Alert is currently PAUSED |

#### What "Last seen" means

This is the most recent price the bot recorded for that symbol. It updates
every time the Binance feed sends a new price for that symbol (roughly every
1–2 seconds). It's useful for checking how far a coin is from your target.

---

### `/alert remove`

**Permanently deletes a specific alert.**

```
/alert remove  id:<number>
```

| Parameter | Description |
|---|---|
| `id` | The alert ID number from `/alert list` or a notification |

#### Example

```
/alert remove  id:7
```

Bot replies:
```
✅ Alert #7 removed.
```

If you try to remove an alert that doesn't exist or belongs to someone
else, the bot tells you:
```
❌ Alert #7 not found or doesn't belong to you.
```

---

### `/alert clear`

**Deletes ALL of your active alerts at once.**

```
/alert clear
```

No parameters. Use this to start fresh. The bot confirms with a count:

```
✅ Cleared 5 active alert(s).
```

> ⚠️ This cannot be undone. All your alerts are permanently deleted.

---

### `/alert pause`

**Temporarily suspends an alert without deleting it.**

```
/alert pause  id:<number>
```

A paused alert:
- Will NOT fire, even if the price crosses your target
- Stays saved so you can resume it later
- Shows up in `/alert list` with a ⏸️ icon

#### When to use pause

- You're going to sleep and don't want late-night notifications
- You want to "snooze" an alert during a known volatile event
- You need to temporarily stop a repeating alert without losing the config

#### Example

```
/alert pause  id:7
```

Bot replies:
```
⏸️ Alert #7 paused. It won't fire until you /alert resume it.
```

---

### `/alert resume`

**Re-activates a paused alert.**

```
/alert resume  id:<number>
```

When you resume an alert:
- It goes back into the active price-watching pool immediately
- The bot checks the current Binance price right away, so if the price
  already crossed your target while it was paused, it will fire immediately

#### Example

```
/alert resume  id:7
```

Bot replies:
```
▶️ Alert #7 resumed and is now active.
```

---

## Alert Notifications

When an alert fires, the bot sends a message in the **same channel where you
ran `/alert add`** and **@mentions you** so you get a ping:

```
@YourName

🚀 Price Alert Triggered
────────────────────────────────────────
Symbol        BTCUSDT
Direction     ABOVE
Target        $70,000.00000000
Triggered At  $70,142.33000000
Repeat Alert  No (alert removed)
                              Alert ID #7
```

For a **downward** crossover:
```
@YourName

📉 Price Alert Triggered
────────────────────────────────────────
Symbol        ETHUSDT
Direction     BELOW
Target        $3,000.00000000
Triggered At  $2,998.11000000
Repeat Alert  No (alert removed)
                              Alert ID #4
```

For a **repeat** alert that fired:
```
@YourName

🔁 🚀 Price Alert Triggered
────────────────────────────────────────
Symbol        BTCUSDT
Direction     ABOVE
Target        $70,000.00000000
Triggered At  $70,250.00000000
Repeat Alert  Yes — 5-min cooldown
                              Alert ID #7
```

---

## Tips & Best Practices

### Setting good targets

```
❌ Don't:  set a target at exactly the current price
           → it may fire immediately or not fire at all
           depending on which way price moves first

✅ Do:     set your target at a meaningful level — a resistance,
           support, round number, or your buy/sell price
```

### Using "Both" direction wisely

`Both` is great for:
- Breakout alerts: "tell me when BTC leaves the $68k–$72k range"
  → set one `below` at $68k and one `above` at $72k
  → or set one `both` at either boundary

### Repeat alerts and spam

With `repeat: True`, the bot waits **5 minutes** between firings.
During a flash crash, a `below` repeat alert could fire every 5 minutes
for hours. That's intentional — it's telling you the price is still below
your level. Use `/alert pause` to silence it temporarily.

### The 50-alert limit

Each user can hold up to 50 active alerts. If you hit the cap:
```
❌ You've reached the maximum of 50 active alerts.
   Remove some with /alert remove or /alert clear.
```
Use `/alert list` to review and remove ones you no longer need.

### Running alerts across multiple servers

Your alerts are tied to **your Discord user ID**, not a server.
But each alert fires in the **channel where you created it**.
If you create an alert in Server A and an alert in Server B, they
both show in `/alert list` and fire in their respective channels.

---

## Common Mistakes

### "Symbol not found on Binance"

```
❌ Symbol `BTC/USDT` was not found on Binance.
```

**Fix:** Remove the slash. Use `BTCUSDT` not `BTC/USDT`.

```
❌ Symbol `btcusdt` ...
```

**Fix:** The bot auto-uppercases it, so this actually works — but to be safe,
always type the symbol in UPPERCASE.

```
❌ Symbol `BITCOIN` was not found.
```

**Fix:** Use the Binance pair name, not the coin's full name. `BTCUSDT`.

### "Invalid price"

```
❌ Invalid price: `70,000`. Enter a positive decimal number.
```

**Fix:** Remove the comma. Use `70000` not `70,000`.

### Alert not firing

Most common reasons:
1. **Price never actually crossed** — it touched your target but didn't
   cross it. The bot uses strict crossover: `last < target ≤ current`.
2. **Alert is paused** — check `/alert list` for the ⏸️ icon.
3. **It already fired and was one-shot** — check if it disappeared from
   `/alert list`. One-shot alerts auto-delete after firing.
4. **Bot was offline** — if the bot restarts, it resyncs prices and
   catches any crossovers that happened while it was down.

### Getting notified in the wrong channel

The alert fires in **whichever channel you typed `/alert add` in**.
If you want notifications in `#price-alerts`, run `/alert add` from
that channel. There's no way to change the channel of an existing
alert — remove it and re-create it in the right channel.

---

## FAQ

**Q: Can other people see my alerts?**
A: No. All bot responses are ephemeral (visible only to you). Other
   users cannot see your alert prices or settings.

**Q: Does the bot work in DMs?**
A: Slash commands require a server. The bot cannot be used in DMs.

**Q: What exchanges are supported?**
A: Only Binance currently. The bot uses Binance's global WebSocket
   feed, which covers all Binance spot trading pairs.

**Q: How fast is the alert?**
A: Binance pushes price updates roughly every 1–2 seconds. From the
   moment the price crosses your target to the moment you receive the
   Discord notification is typically 1–3 seconds.

**Q: What happens if the bot goes offline?**
A: When the bot comes back online, it fetches the current price from
   Binance's REST API and compares it to your stored last price. If
   the price crossed your target while the bot was offline, the alert
   fires as soon as the bot reconnects. You won't miss crossovers.

**Q: Can I set an alert for a price I've already passed?**
A: Yes, but think about direction. If BTC is at $72,000 and you set
   an `above` alert at $70,000, it will never fire (price is already
   above it and the bot is looking for an upward cross from below).
   Set a `below` alert at $70,000 instead for that scenario.

**Q: How many alerts can I have?**
A: Up to 50 active alerts per user.

**Q: Can I edit an existing alert's price?**
A: Not directly. Remove the old one with `/alert remove` and create
   a new one with `/alert add`. It takes about 5 seconds.

**Q: What does "Last seen" mean in /alert list?**
A: The most recent price the bot received from Binance for that symbol.
   It updates in real time as prices change.

**Q: Will the bot @mention me even if I have notifications off?**
A: The bot sends an @mention in the channel, but whether it pings
   you depends on your Discord notification settings for that channel.
   Make sure the channel has notifications enabled if you want pings.
