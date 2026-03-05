"""
Helper script to send a weekly YNAB summary to Slack.

Intended to be called from Airflow (or manually) as:

    cd /opt/projects/ynab && PYTHONPATH=/opt/projects/ynab python -m slack_bot.weekly_summary

It reuses the same Claude + Postgres logic as the Slack bot, and posts
the answer to a configured Slack channel.
"""
import os
import sys
from datetime import datetime

from .claude import answer_question
from .app import post_message_to_slack
from .config import SLACK_BOT_TOKEN


def should_send_now(dt: datetime) -> bool:
    """
    Gate sending to Monday morning by default.

    - Only send on Monday (weekday() == 0)
    - Only send before 12:00 local time, so if the DAG also runs in the evening
      it won't send a second summary.
    """
    return dt.weekday() == 0 and dt.hour < 12


def send_weekly_summary() -> None:
    """
    Ask Claude for the previous week's summary and post it to Slack.

    Slack channel is controlled via YNAB_SLACK_CHANNEL (e.g. "#general" or a channel ID).
    Defaults to "#general" if not set.
    """
    now = datetime.now()
    if not should_send_now(now):
        print("Skipping: not in weekly summary window (Monday morning).", file=sys.stderr)
        return

    channel = os.environ.get("YNAB_SLACK_CHANNEL", "#general")

    if not SLACK_BOT_TOKEN:
        print("ERROR: SLACK_BOT_TOKEN is not set. Set it in secrets.py or YNAB_SLACK_* env vars.", file=sys.stderr)
        sys.exit(1)

    print(f"Sending weekly summary to channel: {channel}", flush=True)
    question = (
        "Give me my summary for the previous week. "
        "Use clear headings and plain text tables (code blocks) with aligned columns."
    )

    answer = answer_question(question)
    ok = post_message_to_slack(channel, answer)
    if not ok:
        print("ERROR: Failed to post message to Slack. Check logs for chat.postMessage response.", file=sys.stderr)
        sys.exit(1)
    print("Weekly summary sent successfully.", flush=True)


if __name__ == "__main__":
    send_weekly_summary()

