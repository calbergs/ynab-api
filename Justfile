# Justfile for YNAB project

# Default recipe: refresh all data
default: refresh

# Refresh YNAB data: fetch transactions, run dbt
refresh:
	python get_transactions.py
	cd dbt && dbt build

# Run Slack bot (requires SLACK_SIGNING_SECRET, ANTHROPIC_API_KEY; see slack_bot/README.md)
slackbot:
	python -m slack_bot.app
