"""
Airflow DAG for YNAB data pipeline
Runs at 9am CT and 9pm CT daily to fetch transactions and run dbt build
"""

import sys
from datetime import datetime, timedelta

from airflow import DAG
from airflow.operators.bash import BashOperator
from airflow.operators.python import ShortCircuitOperator

# Handle Airflow 1.x vs 2.x compatibility
try:
    # Airflow 2.x
    from airflow.operators.empty import EmptyOperator as DummyOperator
    from airflow.hooks.base import BaseHook
    try:
        from airflow.providers.slack.operators.slack_webhook import SlackWebhookOperator
        SLACK_AVAILABLE = True
    except ImportError:
        SLACK_AVAILABLE = False
except ImportError:
    # Airflow 1.x
    from airflow.operators.dummy_operator import DummyOperator
    from airflow.hooks.base_hook import BaseHook
    try:
        from airflow.contrib.operators.slack_webhook_operator import SlackWebhookOperator
        SLACK_AVAILABLE = True
    except ImportError:
        SLACK_AVAILABLE = False

# from airflow_dbt.operators.dbt_operator import DbtRunOperator  # Uncomment if using airflow-dbt


def task_fail_slack_alert(context):
    """Send Slack alert when a task fails (optional - only if Slack connection is configured)."""
    if not SLACK_AVAILABLE:
        print("Slack provider not installed. Skipping Slack alert.")
        return None
    
    try:
        slack_webhook_token = BaseHook.get_connection("slack").password
        slack_msg = """
            :x: Task Failed
            *Task*: {task}
            *Dag*: {dag}
            *Execution Time*: {exec_date}
            *Log URL*: {log_url}
            """.format(
            task=context.get("task_instance").task_id,
            dag=context.get("task_instance").dag_id,
            ti=context.get("task_instance"),
            exec_date=context.get("execution_date"),
            log_url=context.get("task_instance").log_url,
        )
        failed_alert = SlackWebhookOperator(
            task_id="slack_alert",
            http_conn_id="slack",
            webhook_token=slack_webhook_token,
            message=slack_msg,
            username="airflow",
            dag=dag,
        )
        return failed_alert.execute(context=context)
    except Exception as e:
        # If Slack is not configured, just log the error and continue
        print(f"Slack alert failed (Slack may not be configured): {str(e)}")
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
    Only send the weekly summary on the Monday morning run.

    This DAG is scheduled at 03:00 and 15:00 UTC every day.
    - 15:00 UTC on Monday ≈ 09:00 Monday CT (the "Monday morning" run).
    We check the execution_date in UTC and only return True for that run.
    """
    execution_date = context.get("execution_date")
    if not execution_date:
        return False
    # Monday is 0; hour 15 is the 15:00 UTC run
    return execution_date.weekday() == 0 and execution_date.hour == 15

# Schedule: 9am CT and 9pm CT daily
# Note: Airflow schedules in UTC
# 9am CT = 15:00 UTC (CST) / 14:00 UTC (CDT)
# 9pm CT = 03:00 UTC (CST) / 02:00 UTC (CDT)
# Using 15:00 and 03:00 UTC - adjust for DST if needed
# Alternative: Use timezone-aware scheduling if on Airflow 2.x+
with DAG(
    dag_id="ynab_dag",
    schedule_interval="0 3,15 * * *",  # 3am and 3pm UTC (9pm and 9am CT, adjust for DST)
    max_active_runs=1,
    catchup=False,
    default_args=args,
    description="YNAB data pipeline: fetch transactions and run dbt build",
) as dag:

    start_task = DummyOperator(task_id="start")

    # Base path for YNAB project (mounted in the container)
    # The full YNAB repo is mounted at /opt/ynab
    YNAB_BASE_PATH = "/opt/ynab"

    # Task 1: Fetch transactions from YNAB API and load into PostgreSQL
    fetch_transactions = BashOperator(
        task_id="fetch_transactions",
        bash_command=f"cd {YNAB_BASE_PATH} && python get_transactions.py",
        # Ensure Python can find the secrets module
        env={"PYTHONPATH": YNAB_BASE_PATH},
    )

    # Task 2: Run dbt build using the project-local profiles.yml
    dbt_build = BashOperator(
        task_id="dbt_build",
        bash_command=f"cd {YNAB_BASE_PATH}/dbt && dbt build --profiles-dir .",
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
    start_task >> fetch_transactions >> dbt_build >> check_weekly_summary >> weekly_summary >> end_task
