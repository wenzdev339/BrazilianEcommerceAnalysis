"""
Airflow DAG — Layer 2: Bronze → Silver

Runs bronze writer then silver transformations in dependency order.
Geolocation must complete before customers/sellers (enrichment join).
"""

from datetime import datetime, timedelta

from airflow import DAG
from airflow.operators.bash import BashOperator

PROJECT_DIR = "/opt/airflow/project"
DATA_PATH = "/opt/airflow/data"
SPARK_CMD = f"spark-submit --master local[*]"

default_args = {
    "owner": "data-platform",
    "retries": 1,
    "retry_delay": timedelta(minutes=5),
    "email_on_failure": False,
}


def spark_task(task_id: str, script_path: str, **kwargs) -> BashOperator:
    return BashOperator(
        task_id=task_id,
        bash_command=(
            f"cd {PROJECT_DIR} && "
            f"{SPARK_CMD} {script_path} "
            f"--bronze {DATA_PATH}/bronze --silver {DATA_PATH}/silver"
        ),
        **kwargs,
    )


with DAG(
    dag_id="02_bronze_silver",
    description="Write Bronze (1:1) then transform all Silver tables",
    default_args=default_args,
    start_date=datetime(2024, 1, 1),
    schedule_interval=None,   # triggered by dag_full_pipeline
    catchup=False,
    tags=["layer-2", "bronze", "silver", "pyspark"],
) as dag:

    # ── Bronze (all tables, parallelisable) ───────────────────────────────────
    write_bronze = BashOperator(
        task_id="write_bronze",
        bash_command=f"""
            cd {PROJECT_DIR} && \
            {SPARK_CMD} warehouse/bronze/write_bronze.py \
                --raw {DATA_PATH}/raw --bronze {DATA_PATH}/bronze
        """,
    )

    # ── Silver: geolocation first (needed for customer/seller enrichment) ─────
    silver_geolocation = BashOperator(
        task_id="silver_geolocation",
        bash_command=f"""
            cd {PROJECT_DIR} && \
            {SPARK_CMD} warehouse/silver/silver_geolocation.py
        """,
    )

    # ── Silver: independent tables (can run in parallel) ──────────────────────
    silver_orders = BashOperator(
        task_id="silver_orders",
        bash_command=f"cd {PROJECT_DIR} && {SPARK_CMD} warehouse/silver/silver_orders.py",
    )

    silver_order_items = BashOperator(
        task_id="silver_order_items",
        bash_command=f"cd {PROJECT_DIR} && {SPARK_CMD} warehouse/silver/silver_order_items.py",
    )

    silver_payments = BashOperator(
        task_id="silver_payments",
        bash_command=f"cd {PROJECT_DIR} && {SPARK_CMD} warehouse/silver/silver_payments.py",
    )

    silver_reviews = BashOperator(
        task_id="silver_reviews",
        bash_command=f"cd {PROJECT_DIR} && {SPARK_CMD} warehouse/silver/silver_reviews.py",
    )

    silver_products = BashOperator(
        task_id="silver_products",
        bash_command=f"cd {PROJECT_DIR} && {SPARK_CMD} warehouse/silver/silver_products.py",
    )

    # ── Silver: depends on geolocation ────────────────────────────────────────
    silver_customers = BashOperator(
        task_id="silver_customers",
        bash_command=f"cd {PROJECT_DIR} && {SPARK_CMD} warehouse/silver/silver_customers.py",
    )

    silver_sellers = BashOperator(
        task_id="silver_sellers",
        bash_command=f"cd {PROJECT_DIR} && {SPARK_CMD} warehouse/silver/silver_sellers.py",
    )

    # ── Dependency graph ──────────────────────────────────────────────────────
    # Bronze must complete before any Silver runs
    write_bronze >> silver_geolocation

    # Geolocation must complete before customer/seller enrichment
    silver_geolocation >> [silver_customers, silver_sellers]

    # Other Silver tables can run in parallel after Bronze
    write_bronze >> [
        silver_orders,
        silver_order_items,
        silver_payments,
        silver_reviews,
        silver_products,
    ]
