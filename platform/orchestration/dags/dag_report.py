"""
Airflow DAG — Layer 4b: Automated Weekly Report

Generates an HTML report from the Gold tables and saves it to the reports/ directory.
Optionally emails the report via SMTP if credentials are configured.
"""

from datetime import datetime, timedelta

from airflow import DAG
from airflow.operators.bash import BashOperator
from airflow.operators.python import PythonOperator

PROJECT_DIR = "/opt/airflow/project"

default_args = {
    "owner": "data-platform",
    "retries": 0,
    "email_on_failure": False,
}

with DAG(
    dag_id="04_weekly_report",
    description="Generate weekly HTML performance report from Gold tables",
    default_args=default_args,
    start_date=datetime(2024, 1, 1),
    schedule_interval=None,
    catchup=False,
    tags=["reporting", "layer-4"],
) as dag:

    generate_report = BashOperator(
        task_id="generate_html_report",
        bash_command=f"cd {PROJECT_DIR} && python reporting/generate_report.py",
    )

    log_completion = BashOperator(
        task_id="log_completion",
        bash_command='echo "Weekly report generated at $(date -u)"',
    )

    generate_report >> log_completion
