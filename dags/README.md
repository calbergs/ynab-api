# YNAB Airflow DAG

This DAG runs the YNAB data pipeline twice daily (9am CT and 9pm CT).

## DAG Overview

**DAG ID:** `ynab_dag`

**Schedule:** Runs at 9am CT and 9pm CT daily

**Tasks:**
1. `fetch_transactions` - Fetches transactions from YNAB API and loads into PostgreSQL
2. `dbt_build` - Runs dbt build to transform and test the data

## Setup Instructions

### 1. Copy DAG to Airflow

If your Airflow is running in Docker (like your Spotify setup), you'll need to mount this directory:

```yaml
# In your docker-compose.yml or Airflow config
volumes:
  - /Users/albertcheng/Documents/GitHub/ynab/dags:/opt/airflow/dags/ynab
```

Or copy the DAG file to your Airflow DAGs directory:
```bash
cp dags/ynab_dag.py /path/to/airflow/dags/
```

### 2. Update Paths

Update the paths in `ynab_dag.py` to match your Airflow setup:

- **Line 74**: Update the path to `get_transactions.py`
- **Line 80**: Update the path to your `dbt` directory

Current paths assume:
- `/opt/airflow/dags/ynab/get_transactions.py`
- `/opt/airflow/dags/ynab/dbt/`

### 3. Configure Connections

Make sure you have these Airflow connections configured:

- **PostgreSQL**: Connection ID `postgres_localhost` (if your dbt profiles use it)
- **Slack** (optional): Connection ID `slack` for failure alerts

### 4. Install Dependencies

Ensure these are installed in your Airflow environment:
- `requests`
- `psycopg2-binary`
- `dbt-core` (and your dbt adapter, e.g., `dbt-postgres`)

### 5. Configure dbt Profiles

Make sure your `dbt/profiles.yml` is configured correctly for Airflow to use.

## Schedule Timezone Notes

The DAG is scheduled for **9am CT and 9pm CT**, but Airflow schedules in UTC:

- **9am CT** = 3pm UTC (15:00) in winter / 2pm UTC (14:00) in summer
- **9pm CT** = 3am UTC (03:00) in winter / 2am UTC (02:00) in summer

Current schedule: `"0 3,15 * * *"` (3am and 3pm UTC)

**To adjust for Daylight Saving Time:**
- During DST (March-November): Change to `"0 2,14 * * *"`
- During Standard Time (November-March): Use `"0 3,15 * * *"`

Or use Airflow 2.x timezone-aware scheduling if available.

## Task Flow

```
start → fetch_transactions → dbt_build → end
```

## Slack Alerts

The DAG includes Slack alerts on task failure. To disable:
- Remove or comment out the `on_failure_callback` in the `args` dictionary
- Or remove the `task_fail_slack_alert` function if not using Slack

## Testing

Test the DAG manually:
```bash
# Test fetch_transactions task
airflow tasks test ynab_dag fetch_transactions 2024-01-01

# Test dbt_build task
airflow tasks test ynab_dag dbt_build 2024-01-01
```
