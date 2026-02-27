# YNAB Data Pipeline

This project fetches transactions from YNAB API, stores them in PostgreSQL, and provides analytics via dbt and Superset. The pipeline can be run manually, scheduled via cron/launchd, or automated with Airflow.

## Prerequisites

- Python 3.7+
- PostgreSQL (running locally)
- Docker and Docker Compose (for Superset)
- dbt-core and dbt-postgres (for data transformations)
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

## Notes

- CSV files are overwritten for the last 14 days + today on each run (configurable via `DAYS_BACK`)
- PostgreSQL table uses UPSERT to preserve historical data
- Superset runs in Docker and persists data between restarts
- The pipeline is idempotent - safe to run multiple times