# YNAB Slack bot

Ask questions about your spending in Slack. The bot queries your Postgres YNAB data and uses Claude to answer in plain language.

Example: `/ynab How much did I spend on restaurants last month?`

**Conversation history:** You can also DM the app or @mention it in a channel; the bot keeps the last 20 messages per conversation so you can ask follow-ups (e.g. “What about last year?”). See **Optional: Events API** below.

---

## 1. Prerequisites

- PostgreSQL with `ynab_transactions` populated (run `get_transactions.py` at least once).
- Python 3.9+ with dependencies below.

---

## 2. Install dependencies

From the repo root, with your virtualenv activated (e.g. `source venv39/bin/activate`):

```bash
pip install flask anthropic requests
```

(You likely already have `psycopg2-binary` from the main pipeline. If not, add it: `pip install psycopg2-binary`.)

Alternatively: `pip install -e ".[slackbot]"` (can fail if other project deps have version conflicts).

---

## 3. Slack app setup

1. Go to [Slack API – Your Apps](https://api.slack.com/apps) → **Create New App** → **From scratch**.
2. Name it (e.g. "YNAB") and pick your workspace.
3. **Slash Commands** (left sidebar) → **Create New Command**:
   - Command: `/ynab`
   - Request URL: your public URL (see step 5) + `/slack/ynab`, e.g. `https://your-domain.com/slack/ynab`
   - Short description: `Ask questions about your YNAB spending`
   - Usage hint: `How much did I spend on restaurants last month?`
4. **Basic Information** (left sidebar) → **App Credentials**:
   - Copy **Signing Secret** (starts with a long hex string).
5. **Install App** → Install to workspace. For **slash commands only** you don’t need a Bot token. For **conversation history** (DMs / @mentions), copy the **Bot User OAuth Token** (starts with `xoxb-`) after installing.

---

## 4. Environment / config

The bot needs:

- **SLACK_SIGNING_SECRET** – From Slack app → Basic Information → App Credentials → Signing Secret.
- **ANTHROPIC_API_KEY** – From [Anthropic Console](https://console.anthropic.com/).
- **SLACK_BOT_TOKEN** – (Optional, for conversation history.) After Install App, use the **Bot User OAuth Token** (`xoxb-...`) so the bot can post replies to DMs and @mentions.
- **Postgres** – Same as the rest of the project. Either:
  - Use your existing `secrets.py` (with `pg_host`, `pg_port`, `pg_user`, `pg_password`, `dbname`), or
  - Set env vars: `PG_HOST`, `PG_PORT`, `PG_USER`, `PG_PASSWORD`, `PG_DATABASE`.

Option A – add to `secrets.py` (gitignored):

```python
SLACK_SIGNING_SECRET = "your_signing_secret_here"
ANTHROPIC_API_KEY = "sk-ant-..."
SLACK_BOT_TOKEN = "xoxb-..."   # optional, for DMs / @mentions with history
# pg_* already there
```

Option B – export in the shell:

```bash
export SLACK_SIGNING_SECRET="..."
export ANTHROPIC_API_KEY="sk-ant-..."
```

---

## 5. Expose your server to the internet

Slack must be able to POST to your app. Options:

- **Local dev:** use [ngrok](https://ngrok.com/): `ngrok http 5001` → use the `https://...` URL as the Slash Command Request URL (e.g. `https://abc123.ngrok.io/slack/ynab`).
- **Production:** run the app on a server or PaaS (e.g. Fly.io, Railway, a VPS) with HTTPS and set the Slash Command Request URL to `https://your-domain.com/slack/ynab`.

---

## 6. Run the app

From the **repo root** (so `secrets` and `slack_bot` are importable):

```bash
python -m slack_bot.app
```

Server listens on `http://0.0.0.0:5001`. In Slack, run:

```
/ynab How much did I spend on restaurants last month?
```

You’ll get an immediate “Thinking…” then the real answer posted when Claude and the DB respond.

---

## Summary checklist

- [ ] Postgres has `ynab_transactions` (run `get_transactions.py`).
- [ ] Dependencies installed (`pip install -e ".[slackbot]"` or equivalent).
- [ ] Slack app created; Slash Command `/ynab` with Request URL = `https://<your-public-host>/slack/ynab`.
- [ ] Signing Secret and Anthropic API key set (in `secrets.py` or env).
- [ ] App running and reachable at the Request URL (ngrok or production).
- [ ] Test with `/ynab spending by category this month`.

---

## Optional: Events API (conversation history)

To have the bot remember context when you **DM it** or **@mention it** in a channel:

1. **OAuth & Permissions** → ensure the bot has scope **`chat:write`** (and **`app_mentions:read`** if you use @mentions). Reinstall the app if you add scopes, then copy the new **Bot User OAuth Token** into `secrets.py` as **SLACK_BOT_TOKEN**.

2. **Event Subscriptions** → turn **On** → set **Request URL** to `https://<your-public-host>/slack/events` (same base as slash command, path `/slack/events`). Save.

3. Under **Subscribe to bot events**, add:
   - **`message.im`** – direct messages to the bot  
   - **`app_mention`** – when someone @mentions the app in a channel  

4. Restart your app. Open a **DM with the app** or **@mention the app** in a channel and ask a question; reply in the same DM or thread to ask follow-ups. History is kept per conversation (last 20 messages).
