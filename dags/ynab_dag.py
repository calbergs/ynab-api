"""
Airflow DAG for YNAB data pipeline
Runs at 9am CT and 9pm CT daily to fetch transactions and run dbt build.
Schedule uses America/Chicago so DST is handled automatically.
"""

import sys
from datetime import datetime, timedelta

try:
    import pendulum
except ImportError:
    pendulum = None

from airflow import DAG
from airflow.models import Variable
from airflow.operators.bash import BashOperator
from airflow.operators.python import ShortCircuitOperator
from airflow.providers.postgres.operators.postgres import PostgresOperator

# Handle Airflow 1.x vs 2.x compatibility
try:
    # Airflow 2.x
    from airflow.operators.empty import EmptyOperator as DummyOperator
    from airflow.hooks.base import BaseHook
    try:
        from airflow.providers.slack.hooks.slack_webhook import SlackWebhookHook
        SLACK_AVAILABLE = True
    except ImportError:
        SLACK_AVAILABLE = False
except ImportError:
    # Airflow 1.x
    from airflow.operators.dummy_operator import DummyOperator
    from airflow.hooks.base_hook import BaseHook
    try:
        from airflow.providers.slack.hooks.slack_webhook import SlackWebhookHook
        SLACK_AVAILABLE = True
    except ImportError:
        SLACK_AVAILABLE = False

# from airflow_dbt.operators.dbt_operator import DbtRunOperator  # Uncomment if using airflow-dbt


def task_fail_slack_alert(context):
    """Send Slack alert when a task fails.
    Requires Airflow connection id 'slack': Conn Type = slackwebhook, Password = full webhook URL
    (e.g. https://hooks.slack.com/services/T.../B.../xxx) or path (T.../B.../xxx). See Admin -> Connections.
    """
    if not SLACK_AVAILABLE:
        print("Slack provider not installed. Skipping Slack alert.")
        return None
    ti = context.get("task_instance")
    slack_msg = (
        ":x: Task Failed\n"
        "*Task*: {task}\n"
        "*Dag*: {dag}\n"
        "*Execution Time*: {exec_date}\n"
        "*Log URL*: {log_url}"
    ).format(
        task=ti.task_id,
        dag=ti.dag_id,
        exec_date=context.get("execution_date"),
        log_url=ti.log_url,
    )
    try:
        hook = SlackWebhookHook(slack_webhook_conn_id="slack")
        hook.send(text=slack_msg)
    except Exception as e:
        # Log so it appears in task logs; don't raise or the failure callback itself fails
        print(f"Slack alert failed: {e}")
        return None
    return None


# Default arguments for the DAG
args = {
    "owner": "airflow",
    "depends_on_past": False,
    "start_date": datetime(2025, 12, 1),
    "retries": 1,
    "retry_delay": timedelta(minutes=5),
    "on_success_callback": None,
    "on_failure_callback": task_fail_slack_alert,
}


def should_send_weekly_summary(**context):
    """
    Only send the weekly summary on the Monday 9am CT run.

    DAG runs at 9am and 9pm CT. We convert the Airflow data interval end
    (run time) to America/Chicago and return True only when it's Monday
    and 9am (the morning run). Manual/backfill runs are treated the same
    way—no extra gating.
    """
    dt = context.get("data_interval_end") or context.get("logical_date") or context.get("execution_date")
    if not dt:
        return False
    if pendulum:
        # data_interval_end is the run time in UTC; convert to Chicago to detect "Monday 9am CT" run
        central = pendulum.timezone("America/Chicago")
        if hasattr(dt, "in_timezone"):
            ct = dt.in_timezone(central)
        else:
            ct = pendulum.instance(dt).in_timezone(central)
        return ct.weekday() == 0 and ct.hour == 9
    # Fallback if pendulum missing: approximate using naive datetime
    return dt.weekday() == 0 and getattr(dt, "hour", 15) == 15

# Schedule: 9am and 9pm America/Chicago daily (DST handled by timezone)
try:
    from airflow.timetables.interval import CronDataIntervalTimetable
    _central_tz = pendulum.timezone("America/Chicago") if pendulum else None
    _schedule = (
        CronDataIntervalTimetable("0 9,21 * * *", timezone=_central_tz)
        if _central_tz
        else "0 3,15 * * *"
    )
except (ImportError, AttributeError):
    _schedule = "0 3,15 * * *"  # fallback: 3am and 3pm UTC (approx 9pm and 9am CT)

with DAG(
    dag_id="ynab_dag",
    schedule=_schedule,
    max_active_runs=1,
    catchup=False,
    default_args=args,
    description="YNAB data pipeline: fetch transactions and run dbt build",
) as dag:

    start_task = DummyOperator(task_id="start")

    # Base path for YNAB project (mounted in the container)
    # The full YNAB repo is mounted at /opt/ynab
    YNAB_BASE_PATH = "/opt/ynab"
    # Use same Postgres port as data-platform (set Airflow Variable POSTGRES_HOST_PORT if not 5433)
    postgres_port = Variable.get("POSTGRES_HOST_PORT", default_var="5433")

    # Ensure YNAB_FULL_REFRESH exists so Jinja var.value.YNAB_FULL_REFRESH does not raise KeyError
    try:
        Variable.get("YNAB_FULL_REFRESH")
    except KeyError:
        Variable.set("YNAB_FULL_REFRESH", "false")

    # full_refresh: set via (1) Trigger DAG w/ config {"full_refresh": true}, or (2) Airflow Variable
    # YNAB_FULL_REFRESH = true (Admin → Variables). Then we upsert ALL and run payee correction.
    # Use Variable if your UI has no "Trigger w/ config". Set back to false after the run for incremental.
    full_refresh_tmpl = (
        "{{ 'true' if (dag_run.conf.get('full_refresh') or "
        "(var.value.YNAB_FULL_REFRESH | default('false')).lower() in ('true', '1', 'yes')) else 'false' }}"
    )

    # Task 1: Fetch transactions from YNAB API and load into PostgreSQL
    fetch_transactions = BashOperator(
        task_id="fetch_transactions",
        bash_command=f"cd {YNAB_BASE_PATH} && python get_transactions.py",
        env={
            "PYTHONPATH": YNAB_BASE_PATH,
            "YNAB_PG_HOST": "host.docker.internal",
            "YNAB_PG_PORT": postgres_port,
            "POSTGRES_HOST_PORT": postgres_port,
            "FULL_REFRESH": full_refresh_tmpl,
        },
    )

    # Ensure ynab_transactions table exists before dbt (no-op if fetch_transactions created it)
    ensure_ynab_table = PostgresOperator(
        task_id="ensure_ynab_transactions_table",
        postgres_conn_id="postgres_localhost",
        sql="""
        CREATE TABLE IF NOT EXISTS ynab_transactions (
            id TEXT PRIMARY KEY,
            date DATE,
            amount BIGINT,
            approved BOOLEAN,
            cleared TEXT,
            debt_transaction_type TEXT,
            deleted BOOLEAN,
            flag_color TEXT,
            flag_name TEXT,
            import_id TEXT,
            import_payee_name TEXT,
            import_payee_name_original TEXT,
            matched_transaction_id TEXT,
            memo TEXT,
            payee_id TEXT,
            payee_name TEXT,
            category_id TEXT,
            category_name TEXT,
            account_id TEXT,
            account_name TEXT,
            subtransactions JSONB,
            transfer_account_id TEXT,
            transfer_transaction_id TEXT,
            load_timestamp TIMESTAMPTZ
        );
        """,
    )

    # Always run payee corrections after fetch so the raw table stays corrected (not overwritten by next run).
    correct_payee_names = BashOperator(
        task_id="correct_payee_names",
        bash_command=f"cd {YNAB_BASE_PATH} && PYTHONPATH={YNAB_BASE_PATH} python scripts/run_correct_payee_if_full_refresh.py",
        env={
            "PYTHONPATH": YNAB_BASE_PATH,
            "YNAB_PG_HOST": "host.docker.internal",
            "YNAB_PG_PORT": postgres_port,
            "POSTGRES_HOST_PORT": postgres_port,
        },
    )

    # Task 2: Run dbt build using the project-local profiles.yml
    # Ensure dbt CLI is on PATH (pip installs it to ~/.local/bin in the Airflow image)
    dbt_build = BashOperator(
        task_id="dbt_build",
        bash_command=f"cd {YNAB_BASE_PATH}/dbt && dbt build --profiles-dir .",
        env={
            "PATH": "/home/airflow/.local/bin:/usr/local/bin:/usr/bin:/bin",
            "YNAB_PG_HOST": "host.docker.internal",
            "POSTGRES_HOST_PORT": postgres_port,
        },
    )

    # Indexes for faster Superset/dashboard queries (idempotent). Only public.ynab_transactions
    # here; staging table schema/name can vary by dbt config (run scripts/add_ynab_indexes.sql manually if needed).
    ensure_ynab_indexes = PostgresOperator(
        task_id="ensure_ynab_indexes",
        postgres_conn_id="postgres_localhost",
        sql=[
            "CREATE INDEX IF NOT EXISTS ix_ynab_transactions_date ON public.ynab_transactions (date)",
            "CREATE INDEX IF NOT EXISTS ix_ynab_transactions_date_category ON public.ynab_transactions (date, category_name)",
            "CREATE INDEX IF NOT EXISTS ix_ynab_transactions_date_payee ON public.ynab_transactions (date, payee_name)",
        ],
    )

    # Gate: only run weekly summary on Monday morning run
    check_weekly_summary = ShortCircuitOperator(
        task_id="check_weekly_summary_window",
        python_callable=should_send_weekly_summary,
    )

    # Task 3: Send weekly summary to Slack (script itself only sends on Monday mornings)
    weekly_summary = BashOperator(
        task_id="weekly_summary_to_slack",
        bash_command=(
            f"cd {YNAB_BASE_PATH} && "
            f"PYTHONPATH={YNAB_BASE_PATH} python -m slack_bot.weekly_summary"
        ),
    )

    end_task = DummyOperator(task_id="end")

    # Define task dependencies
    start_task >> fetch_transactions >> ensure_ynab_table >> correct_payee_names >> dbt_build >> ensure_ynab_indexes >> check_weekly_summary >> weekly_summary >> end_task
