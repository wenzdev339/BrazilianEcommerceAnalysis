"""
Airflow DAG — Master Pipeline Orchestrator

Chains all three layer DAGs in sequence using TriggerDagRunOperator.
This allows individual layers to be re-triggered independently for
partial re-runs (e.g., dbt model change → re-run Gold + dbt only).

Schedule: @weekly (Sundays at 02:00 UTC)
"""

from datetime import datetime, timedelta

from airflow import DAG
from airflow.operators.bash import BashOperator
from airflow.operators.trigger_dagrun import TriggerDagRunOperator

default_args = {
    "owner": "data-platform",
    "retries": 0,
    "email_on_failure": True,
}

with DAG(
    dag_id="00_full_pipeline",
    description="Master orchestrator — chains ingestion → bronze/silver → gold/dbt → report",
    default_args=default_args,
    start_date=datetime(2024, 1, 1),
    schedule_interval="0 2 * * 0",   # Sundays 02:00 UTC
    catchup=False,
    tags=["master", "orchestration"],
) as dag:

    trigger_ingestion = TriggerDagRunOperator(
        task_id="trigger_ingestion",
        trigger_dag_id="01_ingestion",
        wait_for_completion=True,
        poke_interval=30,
    )

    trigger_bronze_silver = TriggerDagRunOperator(
        task_id="trigger_bronze_silver",
        trigger_dag_id="02_bronze_silver",
        wait_for_completion=True,
        poke_interval=30,
    )

    trigger_gold_dbt = TriggerDagRunOperator(
        task_id="trigger_gold_dbt",
        trigger_dag_id="03_gold_and_dbt",
        wait_for_completion=True,
        poke_interval=30,
    )

    trigger_report = TriggerDagRunOperator(
        task_id="trigger_report",
        trigger_dag_id="04_weekly_report",
        wait_for_completion=True,
        poke_interval=30,
    )

    pipeline_complete = BashOperator(
        task_id="pipeline_complete",
        bash_command='echo "Full pipeline completed at $(date -u)"',
    )

    (
        trigger_ingestion
        >> trigger_bronze_silver
        >> trigger_gold_dbt
        >> trigger_report
        >> pipeline_complete
    )
