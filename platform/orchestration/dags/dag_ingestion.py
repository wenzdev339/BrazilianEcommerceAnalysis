"""
Airflow DAG — Layer 1: CSV Ingestion

Triggers the PySpark ingestion pipeline that reads all 9 source CSV files,
runs data quality validation, and writes to the Raw landing zone as Parquet.

Schedule: @daily with catchup=False (static dataset, no backfill needed)
"""

from datetime import datetime, timedelta

from airflow import DAG
from airflow.operators.bash import BashOperator
from airflow.operators.python import PythonOperator

PROJECT_DIR = "/opt/airflow/project"
DATASETS_PATH = "/opt/datasets"
DATA_PATH = "/opt/airflow/data"

default_args = {
    "owner": "data-platform",
    "retries": 1,
    "retry_delay": timedelta(minutes=5),
    "email_on_failure": False,
}

with DAG(
    dag_id="01_ingestion",
    description="Extract CSV sources → validate → write Raw Parquet",
    default_args=default_args,
    start_date=datetime(2024, 1, 1),
    schedule_interval="@daily",
    catchup=False,
    tags=["layer-1", "ingestion", "pyspark"],
) as dag:

    check_datasets = BashOperator(
        task_id="check_source_files",
        bash_command=f"""
            echo "Checking source CSV files..."
            for f in olist_customers_dataset.csv olist_orders_dataset.csv \
                      olist_order_items_dataset.csv olist_order_payments_dataset.csv \
                      olist_order_reviews_dataset.csv olist_products_dataset.csv \
                      olist_sellers_dataset.csv olist_geolocation_dataset.csv \
                      product_category_name_translation.csv; do
                if [ ! -f {DATASETS_PATH}/$f ]; then
                    echo "MISSING: $f" && exit 1
                fi
                echo "OK: $f"
            done
            echo "All source files found."
        """,
    )

    run_ingestion = BashOperator(
        task_id="run_pyspark_ingestion",
        bash_command=f"""
            cd {PROJECT_DIR} && \
            spark-submit \
                --master local[*] \
                --py-files {PROJECT_DIR}/ingestion/ \
                {PROJECT_DIR}/ingestion/ingest_raw.py \
                --datasets {DATASETS_PATH} \
                --output {DATA_PATH}/raw
        """,
        # Alternatively use SparkSubmitOperator with a Spark connection configured
    )

    validate_output = BashOperator(
        task_id="validate_raw_output",
        bash_command=f"""
            echo "Checking Raw Parquet output..."
            for table in customers orders order_items payments reviews \
                         products sellers geolocation category_translation; do
                if [ ! -d {DATA_PATH}/raw/$table ]; then
                    echo "MISSING Raw partition: $table" && exit 1
                fi
                echo "Raw OK: $table"
            done
            echo "Raw layer validation passed."
        """,
    )

    check_datasets >> run_ingestion >> validate_output
