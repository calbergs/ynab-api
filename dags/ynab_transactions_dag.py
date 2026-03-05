from datetime import datetime, timedelta

from airflow import DAG
from airflow.operators.bash import BashOperator


default_args = {
    "owner": "airflow",
    "depends_on_past": False,
    "start_date": datetime(2026, 1, 1),
    "retries": 1,
    "retry_delay": timedelta(minutes=5),
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

