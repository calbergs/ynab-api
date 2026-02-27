# Justfile for YNAB project

# Default recipe: refresh all data
default: refresh

# Refresh YNAB data: fetch transactions, run dbt
refresh:
	python get_transactions.py
	cd dbt && dbt build
