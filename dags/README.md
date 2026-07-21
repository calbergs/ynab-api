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
  - /Users/<user>/Documents/GitHub/ynab/dags:/opt/airflow/dags/ynab
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

Make sure you have these Airflow connections configured in **Admin → Connections**:

- **PostgreSQL**: Connection ID `postgres_localhost`
  - Host: `host.docker.internal` (or your host when running Airflow in Docker)
  - Port: **5433** (must match `POSTGRES_HOST_PORT` in data-platform `.env` if Postgres is on 5433)
  - Schema: `airflow`
  - Login: `airflow` / Password: `airflow`
- **Slack (failure alerts)**: Connection ID `slack`
  - Conn Type: **Slack Webhook** (or **HTTP** if that’s the only option)
  - For Slack Webhook: put your incoming webhook URL in **Password** (or in Host, depending on provider)
  - Webhook URL looks like: `https://hooks.slack.com/services/T.../B.../xxx`
  - Without this connection, task failures will not send Slack alerts

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
start → fetch_transactions → ensure_ynab_table → correct_payee_names → dbt_build → check_weekly_summary → weekly_summary → end
```

### Full refresh vs incremental

- **Normal / scheduled run:** Only the last `DAYS_BACK` days (default 14) are upserted into Postgres. Payee correction is skipped.
- **Full historical refresh:** Use either method below. Then all transactions are upserted (not just last 14 days).

  **Option A – Airflow Variable (works in all UIs)**  
  1. Go to **Admin → Variables**.  
  2. Add (or edit) variable **Key** `YNAB_FULL_REFRESH`, **Val** `true`.  
  3. Trigger the DAG with the normal **Play** button.  
  4. After the run, set `YNAB_FULL_REFRESH` back to `false` (or delete it) so the next run is incremental.

  **Option B – Trigger with config (if your Airflow UI has it)**  
  Some versions show **Trigger DAG w/ config** in the play-button dropdown. If so, trigger with Config (JSON): `{"full_refresh": true}`. No Variable needed.

**Payee name correction** runs after every fetch (full and incremental), so the raw table and dbt models always see corrected restaurant names and nothing overwrites them on the next run.

## Slack Alerts

The DAG sends a Slack message when any task **fails** (via `on_failure_callback`). For this to work:

1. **Create an Airflow connection** (Admin → Connections):
   - Connection Id: `slack`
   - Connection Type: `Slack Webhook` (or `HTTP` if your Airflow version only has that)
   - Password: your Slack incoming webhook URL (e.g. `https://hooks.slack.com/services/T.../B.../xxx`)

2. **Install the Slack provider** in your Airflow environment (usually already in the image):
   - `apache-airflow-providers-slack`

3. Tasks must actually **fail** (non-zero exit or exception). If a script fails but exits with code 0, Airflow marks the task as success and no alert is sent. The YNAB DAG is set up so that `fetch_transactions` exits with code 1 when Postgres load fails.

To disable alerts: remove or comment out `on_failure_callback: task_fail_slack_alert` in the `args` dictionary.

## Testing

Test the DAG manually:
```bash
# Test fetch_transactions task
airflow tasks test ynab_dag fetch_transactions 2024-01-01

# Test dbt_build task
airflow tasks test ynab_dag dbt_build 2024-01-01
```
