from datetime import datetime, timedelta

from airflow import DAG
from airflow.operators.bash import BashOperator

try:
    from airflow.providers.slack.hooks.slack_webhook import SlackWebhookHook

    SLACK_AVAILABLE = True
except ImportError:
    SLACK_AVAILABLE = False


def task_fail_slack_alert(context):
    """Send Slack alert when a task fails (requires Airflow connection id `slack`)."""
    if not SLACK_AVAILABLE:
        return None
    ti = context.get("task_instance")
    exec_date = context.get("logical_date") or context.get("execution_date")
    slack_msg = (
        ":x: Task Failed\n"
        "*Task*: {task}\n"
        "*Dag*: {dag}\n"
        "*Execution Time*: {exec_date}\n"
        "*Log URL*: {log_url}"
    ).format(
        task=ti.task_id,
        dag=ti.dag_id,
        exec_date=exec_date,
        log_url=ti.log_url,
    )
    try:
        hook = SlackWebhookHook(slack_webhook_conn_id="slack")
        hook.send(text=slack_msg)
    except Exception as e:
        print(f"Slack alert failed: {e}")
    return None

default_args = {
    "owner": "airflow",
    "depends_on_past": False,
    "start_date": datetime(2026, 1, 1),
    "retries": 1,
    "retry_delay": timedelta(minutes=5),
    "on_failure_callback": task_fail_slack_alert,
}


with DAG(
    dag_id="ynab_transactions_full_refresh",
    default_args=default_args,
    # Defining params makes the UI reliably show "Trigger DAG w/ config".
    params={
        "days_back": 14,
        "full_refresh": False,
    },
    catchup=False,
    max_active_runs=1,
) as dag:
    run_ynab_pipeline = BashOperator(
        task_id="run_ynab_transactions_pipeline",
        bash_command="python /opt/ynab/get_transactions.py",
        env={
            # Optional parameters passed when you trigger the DAG manually:
            #   {"days_back": 30, "full_refresh": true}
            "DAYS_BACK": "{{ (dag_run.conf or {}).get('days_back', 14) }}",
            "FULL_REFRESH": "{{ (dag_run.conf or {}).get('full_refresh', false) | lower }}",
            # Ensure the script uses the same Postgres port your Airflow/data-platform uses.
            # Your data-platform exposes Postgres on host port 5433, and the script runs inside the Airflow container.
            "YNAB_PG_HOST": "host.docker.internal",
            "YNAB_PG_PORT": "5433",
            "POSTGRES_HOST_PORT": "5433",
        },
    )

    # Build all dbt models and run tests (same pattern as ynab_dag).
    dbt_build = BashOperator(
        task_id="dbt_build",
        bash_command="cd /opt/ynab/dbt && dbt build --profiles-dir .",
        env={
            "PATH": "/home/airflow/.local/bin:/usr/local/bin:/usr/bin:/bin",
            "YNAB_PG_HOST": "host.docker.internal",
            "POSTGRES_HOST_PORT": "5433",
        },
    )

    run_ynab_pipeline >> dbt_build

