# YNAB Airflow DAG

This DAG runs the YNAB data pipeline twice daily (9am CT and 9pm CT).

## DAG Overview

**DAG ID:** `ynab_dag`

**Schedule:** Runs at 9am CT and 9pm CT daily

**Tasks:**
1. `fetch_transactions` - Fetches transactions from YNAB API and loads into PostgreSQL
2. `dbt_build` - Runs dbt build to transform and test the data

## Setup Instructions

### 1. Mount this repo into the shared Airflow stack

This DAG runs inside the `data-platform` repo's Airflow stack (not a standalone Airflow install). `ynab_dag.py` already assumes fixed in-container paths via `YNAB_BASE_PATH = "/opt/ynab"` — no line-editing needed. Just set these in `data-platform/.env`:

```
YNAB_DAGS_PATH=/absolute/path/to/ynab-api/dags
YNAB_REPO_PATH=/absolute/path/to/ynab-api
```

`data-platform/docker-compose.yaml` mounts them as `${YNAB_DAGS_PATH}:/opt/airflow/dags/ynab` and `${YNAB_REPO_PATH}:/opt/ynab` — the second one is what `YNAB_BASE_PATH` in the DAG points at, so `get_transactions.py`, `dbt/`, and `slack_bot/` are all reachable at `/opt/ynab/...` automatically. Restart `airflow-worker`/`airflow-scheduler` after changing these.

### 2. Configure Connections

Make sure you have these Airflow connections configured in **Admin → Connections**:

- **PostgreSQL**: Connection ID `postgres_localhost`
  - Host: `host.docker.internal` (or your host when running Airflow in Docker)
  - Port, schema, login, password: match whatever's set in `data-platform/.env` (`POSTGRES_HOST_PORT` and the Postgres service's credentials)
- **Slack (failure alerts)**: Connection ID `slack`
  - Conn Type: **Slack Webhook** (or **HTTP** if that’s the only option)
  - For Slack Webhook: put your incoming webhook URL in **Password** (or in Host, depending on provider)
  - Webhook URL looks like: `https://hooks.slack.com/services/T.../B.../xxx`
  - Without this connection, task failures will not send Slack alerts

### 3. Install Dependencies

Ensure these are installed in your Airflow environment:
- `requests`
- `psycopg2-binary`
- `dbt-core` (and your dbt adapter, e.g., `dbt-postgres`)

### 4. dbt Profiles & Personal Payee Corrections

`dbt/profiles.yml` is already committed and env-var only (no secrets) — nothing to configure there.

If you want personal payee-name corrections (e.g. normalizing a specific card's merchant strings, which may contain your name or other identifying text), add them to `dbt/macros/correct_payee_name.sql` — this file is gitignored (like the rest of `dbt/macros/`) so personal data never gets committed. `stg_ynab_transactions.sql` calls `{{ correct_payee_name('payee_name_ascii') }}`; without the macro file present, `dbt build` will fail with a missing-macro error on a fresh clone. Minimum viable version (no-op passthrough):

```sql
{% macro correct_payee_name(payee_name_col) %}
    {{ payee_name_col }}
{% endmacro %}
```

Add `when ... then ...` cases inside a `case` expression as needed — see the (gitignored) working copy for the pattern.

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
