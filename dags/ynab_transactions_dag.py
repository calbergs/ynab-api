from datetime import datetime, timedelta

from airflow import DAG
from airflow.operators.bash import BashOperator

# Slack failure alert (same pattern as spotify_dag / ynab_dag)
try:
    from airflow.hooks.base import BaseHook
    from airflow.providers.slack.operators.slack_webhook import SlackWebhookOperator
    SLACK_AVAILABLE = True
except ImportError:
    try:
        from airflow.hooks.base_hook import BaseHook
        from airflow.contrib.operators.slack_webhook_operator import SlackWebhookOperator
        SLACK_AVAILABLE = True
    except ImportError:
        SLACK_AVAILABLE = False


def task_fail_slack_alert(context):
    """Send Slack alert when a task fails (uses Airflow connection 'slack')."""
    if not SLACK_AVAILABLE:
        return None
    try:
        slack_webhook_token = BaseHook.get_connection("slack").password
        ti = context.get("task_instance")
        slack_msg = """
        :x: Task Failed
        *Task*: {task}
        *Dag*: {dag}
        *Execution Time*: {exec_date}
        *Log URL*: {log_url}
        """.format(
            task=ti.task_id,
            dag=ti.dag_id,
            ti=ti,
            exec_date=context.get("execution_date"),
            log_url=ti.log_url,
        )
        dag = ti.dag
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
    schedule_interval="0 3 * * *",  # daily at 03:00
    catchup=False,
    max_active_runs=1,
) as dag:
    run_ynab_pipeline = BashOperator(
        task_id="run_ynab_transactions_pipeline",
        bash_command="python /opt/ynab/get_transactions.py",
    )

