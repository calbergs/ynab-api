"""
Load config from environment or secrets.py (for Postgres).
Set SLACK_SIGNING_SECRET and ANTHROPIC_API_KEY in env or secrets.
"""
import os

# Prefer env; fall back to secrets if available (secrets.py is gitignored)
def _get(name: str, default: str = "") -> str:
    v = os.environ.get(name)
    if v:
        return v
    try:
        from secrets import __dict__ as s
        return s.get(name, default)
    except ImportError:
        return default


SLACK_SIGNING_SECRET = _get("SLACK_SIGNING_SECRET")
SLACK_BOT_TOKEN = _get("SLACK_BOT_TOKEN")  # Bot User OAuth Token (xoxb-...) for posting replies
ANTHROPIC_API_KEY = _get("ANTHROPIC_API_KEY")
# Override if your account has different models (e.g. ANTHROPIC_MODEL=claude-3-5-sonnet)
ANTHROPIC_MODEL = _get("ANTHROPIC_MODEL", "claude-sonnet-4-6")

# Postgres: from env or secrets
def get_pg_config():
    try:
        from secrets import pg_host, pg_port, pg_user, pg_password, dbname
        return {
            "host": pg_host,
            "port": pg_port,
            "user": pg_user,
            "password": pg_password,
            "dbname": dbname,
        }
    except ImportError:
        return {
            "host": os.environ.get("PG_HOST", "localhost"),
            "port": int(os.environ.get("PG_PORT", "5432")),
            "user": os.environ.get("PG_USER", ""),
            "password": os.environ.get("PG_PASSWORD", ""),
            "dbname": os.environ.get("PG_DATABASE", "ynab"),
        }

TABLE_NAME = "ynab_transactions"
