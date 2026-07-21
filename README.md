# YNAB Data Pipeline

This project fetches transactions from YNAB API, stores them in PostgreSQL, and provides analytics via dbt and Superset. The pipeline can be run manually (see below) or automated with Airflow — **production runs via Airflow**, using the shared stack in the `data-platform` repo. See **[dags/README.md](dags/README.md)** for the Airflow setup (mounting this repo, connections, schedule).

The manual setup below (local Postgres, `secrets.py`, `just refresh`) is useful for local development/testing, but isn't how the pipeline actually runs day to day.

## Prerequisites

- Python 3.7+
- PostgreSQL — either running locally, or point at the shared `data-platform` Postgres (see `data-platform/.env` for host/port) by setting `pg_host`/`pg_port` in `secrets.py` (the standalone scripts read Postgres config from `secrets.py` only, not env vars)
- Docker and Docker Compose (for Superset)
- dbt-core and dbt-postgres (for data transformations, if running dbt outside of Airflow)
- `just` command runner (optional, for simplified commands)

## Setup

### 1. PostgreSQL Setup

First, set up the PostgreSQL database and user.

```bash
# Create the database and user (if needed)
# You may need to run this as the postgres superuser
psql -U postgres -c "CREATE DATABASE <name>>;"
psql -U postgres -c "CREATE USER *** WITH PASSWORD '***';"
psql -U postgres -c "GRANT ALL PRIVILEGES ON DATABASE <name> TO <user>;"
```

Update your credentials in `secrets.py` if needed.

### 2. Install Python Dependencies

```bash
pip install requests psycopg2-binary apache-superset dbt-core dbt-postgres
```

### 3. Install Just (Optional)

For simplified command execution:

```bash
# macOS
brew install just

# Or install from https://github.com/casey/just
```

## Usage

### Quick Start (Using Just)

The easiest way to run the full pipeline:

```bash
just
# or
just refresh
```

This will:
- Fetch transactions from YNAB API
- Write CSV files for the last 14 days (overwrites existing files)
- Upsert transactions into PostgreSQL (preserves historical data)
- Run dbt build to transform and test the data

### Manual Execution

#### Fetching Transactions

Run the main script to fetch transactions from YNAB and load them into PostgreSQL:

```bash
python get_transactions.py
```

This will:
- Fetch all transactions from YNAB API
- Write CSV files for the last 14 days (overwrites existing files)
- **Upsert** transactions into PostgreSQL using `ON CONFLICT` (preserves historical data not in API response)

**Note:** The number of days for CSV writing can be configured via the `DAYS_BACK` constant in `get_transactions.py` (default: 14 days).

### Starting Superset

To start Apache Superset for data visualization:

```bash
# Start Superset in the background
docker compose up -d

# View logs (optional)
docker compose logs -f superset
```

**Access Superset:**
- URL: http://localhost:8088

**Useful Superset Commands:**

```bash
# Stop Superset
docker compose down

# Restart Superset
docker compose restart

# View Superset logs
docker compose logs -f superset

# Check Superset status
docker compose ps
```

**If you see "Unexpected error / SupersetApiError: Fatal error" or "Invalid decryption key":**  
Database connection strings are encrypted with `SECRET_KEY`. If the key changed (e.g. after a config or env change), Superset can’t decrypt them. Re-encrypt with the current key by setting `SUPERSET_DB_URI` to your Postgres connection string (user/password/port match `data-platform/.env`) and running (from repo root, with Superset running):

```bash
cd ynab-api && SUPERSET_DB_URI="postgresql+psycopg2://<user>:<password>@host.docker.internal:<port>/<database>" docker exec -e SUPERSET_DB_URI superset python -c "
import os, sys
sys.path.insert(0, '/app')
os.environ.setdefault('SUPERSET_CONFIG_PATH', '/app/superset_config.py')
from superset.app import create_app
from sqlalchemy import update
app = create_app()
with app.app_context():
    from superset.extensions import db
    from superset.models.core import Database
    uri = os.environ['SUPERSET_DB_URI']
    r = db.session.execute(update(Database).values(sqlalchemy_uri=uri))
    db.session.commit()
    print('Re-encrypted', r.rowcount, 'database connection(s).')
"
```

### Running dbt

To transform your data using dbt:

```bash
cd dbt

# Build all models and run tests
dbt build

# Run all models
dbt run

# Run specific model
dbt run --select stg_ynab_transactions

# Run tests
dbt test
```

## Project Structure

```
.
├── data/                          # Partitioned CSV files (year/month/day)
├── dbt/                           # dbt models and transformations
│   ├── models/
│   │   ├── staging/              # Staging models
│   │   ├── analytical/          # Analytical models (transactions, spend, card_usage, etc.)
│   │   └── reporting/           # Reporting models (rpt_spend, rpt_weekly_spend, etc.)
│   └── macros/                   # Reusable SQL macros
├── get_transactions.py           # Main script to fetch and load data
├── Justfile                      # Just command runner recipes
├── secrets.py                    # Configuration (credentials, etc.) - NOT in git
├── docker-compose.yml            # Superset Docker configuration
├── Dockerfile.superset           # Custom Superset Dockerfile
└── README.md                     # This file
```

## Configuration

All sensitive configuration is stored in `secrets.py`:

- YNAB API token and budget ID
- PostgreSQL connection details (host, port, user, password, database name)

`dbt/profiles.yml` is committed (env-var only, no secrets). Any personal payee-name corrections (e.g. restaurant names, or merchant strings that include your own name) go in the gitignored `dbt/macros/correct_payee_name.sql` instead — see [dags/README.md](dags/README.md#4-dbt-profiles--personal-payee-corrections) for the pattern.

## Data Pipeline Details

### PostgreSQL Loading Strategy

The pipeline uses **UPSERT** (not TRUNCATE) to preserve historical data:
- Transactions are inserted or updated based on transaction `id`
- Historical transactions not returned by the YNAB API are preserved
- Uses PostgreSQL `ON CONFLICT (id) DO UPDATE SET` clause

### CSV File Management

- CSV files are written in partitioned format: `data/year=YYYY/month=MM/day=DD/YYYY_MM_DD.csv`
- Only files for the last N days (default: 14) are overwritten on each run
- Older files are preserved for historical analysis
- Configure the number of days via `DAYS_BACK` constant in `get_transactions.py`

### dbt Models

The dbt project includes:
- **Staging**: Raw data transformations (`stg_ynab_transactions`)
- **Analytical**: Business logic models (`transactions`, `spend`, `income`, `card_usage`, etc.)
- **Reporting**: Aggregated reports (`rpt_spend`, `rpt_weekly_spend`, `rpt_income`, `rpt_savings`)

## Slack Bot (optional)

There's an on-demand `/ynab` Slack slash command that lets you ask Claude questions about your spending in plain English — it queries your Postgres transaction data via Claude tool-calling and answers directly in Slack:

```
/ynab How much did I spend on restaurants last month?
/ynab Spending by category this year
/ynab When was my last transaction at Costco?
```

You'll see an immediate "Thinking…" reply, then the real answer once Claude and the DB respond. You can also DM the bot or @mention it in a channel for multi-turn follow-up questions (e.g. ask a question, then "what about last year?") — it keeps the last 20 messages of context per conversation.

Full setup (Slack app, Slash Command, Anthropic API key, ngrok wiring, optional DM/@mention support) is in [`slack_bot/README.md`](slack_bot/README.md).

## Notes

- CSV files are overwritten for the last 14 days + today on each run (configurable via `DAYS_BACK`)
- PostgreSQL table uses UPSERT to preserve historical data
- Superset runs in Docker and persists data between restarts
- The pipeline is idempotent - safe to run multiple times