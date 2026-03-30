"""
Airflow DAG — Layer 3: Gold (PySpark dims/facts) + dbt build & test

Build order:
  1. dim_date, dim_customer, dim_product  (independent — parallel)
  2. fact_orders                          (depends on all dims)
  3. dbt build --select marts            (depends on Gold Parquet → Postgres load)
  4. dbt test                            (depends on dbt build)
"""

from datetime import datetime, timedelta

from airflow import DAG
from airflow.operators.bash import BashOperator

PROJECT_DIR = "/opt/airflow/project"
DATA_PATH = "/opt/airflow/data"
SPARK_CMD = "spark-submit --master local[*]"
DBT_DIR = f"{PROJECT_DIR}/dbt"

default_args = {
    "owner": "data-platform",
    "retries": 1,
    "retry_delay": timedelta(minutes=5),
    "email_on_failure": False,
}


with DAG(
    dag_id="03_gold_and_dbt",
    description="Build Gold star schema (PySpark) then run dbt models and tests",
    default_args=default_args,
    start_date=datetime(2024, 1, 1),
    schedule_interval=None,
    catchup=False,
    tags=["layer-3", "gold", "dbt", "star-schema"],
) as dag:

    # ── Dimension tables (parallel) ────────────────────────────────────────────
    gold_dim_date = BashOperator(
        task_id="gold_dim_date",
        bash_command=f"cd {PROJECT_DIR} && {SPARK_CMD} warehouse/gold/dim_date.py",
    )

    gold_dim_customer = BashOperator(
        task_id="gold_dim_customer",
        bash_command=f"cd {PROJECT_DIR} && {SPARK_CMD} warehouse/gold/dim_customer.py",
    )

    gold_dim_product = BashOperator(
        task_id="gold_dim_product",
        bash_command=f"cd {PROJECT_DIR} && {SPARK_CMD} warehouse/gold/dim_product.py",
    )

    # ── Fact table (waits for all dims) ───────────────────────────────────────
    gold_fact_orders = BashOperator(
        task_id="gold_fact_orders",
        bash_command=f"cd {PROJECT_DIR} && {SPARK_CMD} warehouse/gold/fact_orders.py",
    )

    # ── dbt: seed → staging → intermediate → marts ────────────────────────────
    dbt_seed = BashOperator(
        task_id="dbt_seed",
        bash_command=f"cd {DBT_DIR} && dbt seed --profiles-dir .",
    )

    dbt_build = BashOperator(
        task_id="dbt_build",
        bash_command=(
            f"cd {DBT_DIR} && "
            "dbt build --select staging intermediate marts --profiles-dir ."
        ),
    )

    dbt_test = BashOperator(
        task_id="dbt_test",
        bash_command=f"cd {DBT_DIR} && dbt test --select marts --profiles-dir .",
    )

    # ── Dependency graph ───────────────────────────────────────────────────────
    [gold_dim_date, gold_dim_customer, gold_dim_product] >> gold_fact_orders
    gold_fact_orders >> dbt_seed >> dbt_build >> dbt_test
