"""
Gold Layer — dim_customer  (SCD Type 1)

Grain: one row per customer_unique_id.

Key design decision: The source has customer_id (per-order) and customer_unique_id
(per person). A single person can have multiple customer_id values across orders.
We resolve to customer_unique_id and aggregate order history to derive segments.

Columns:
  customer_key        INTEGER  Surrogate key (monotonically increasing)
  customer_unique_id  STRING   Business key
  customer_city       STRING
  customer_state      STRING
  region              STRING   Brazil macro-region
  customer_since      DATE     Earliest order purchase date
  total_orders        INTEGER
  lifetime_value      DECIMAL  Sum of all delivered order payments
  customer_segment    STRING   High (≥ R$500) / Medium (≥ R$200) / Low (< R$200)
"""

from __future__ import annotations

import logging
import os
import sys
from pathlib import Path

from pyspark.sql import DataFrame, SparkSession
from pyspark.sql import functions as F
from pyspark.sql.types import DecimalType

sys.path.insert(0, str(Path(__file__).parent.parent.parent))
from ingestion.spark_session import get_spark_session

logger = logging.getLogger(__name__)


def build_dim_customer(
    silver_customers: DataFrame,
    silver_orders: DataFrame,
    silver_payments: DataFrame,
) -> DataFrame:
    # ── Aggregate order history per customer_unique_id ─────────────────────────

    # Map customer_id → customer_unique_id via orders + customers join
    id_map = silver_customers.select("customer_id", "customer_unique_id")

    orders_with_unique = silver_orders.join(id_map, on="customer_id", how="left")

    # Order-level payment totals (sum sequential payments per order)
    order_payment = (
        silver_payments
        .groupBy("order_id")
        .agg(F.sum("payment_value").alias("order_payment_total"))
    )

    # Delivered orders with payments
    delivered = (
        orders_with_unique
        .filter(F.col("order_status") == "delivered")
        .join(order_payment, on="order_id", how="left")
    )

    # Aggregate to customer_unique_id level
    customer_stats = (
        delivered
        .groupBy("customer_unique_id")
        .agg(
            F.min("order_purchase_timestamp").alias("customer_since"),
            F.count("order_id").alias("total_orders"),
            F.sum("order_payment_total").cast(DecimalType(12, 2)).alias("lifetime_value"),
        )
    )

    # ── Build dimension ────────────────────────────────────────────────────────

    # One canonical record per customer_unique_id (take first customer_id's city/state)
    canonical = (
        silver_customers
        .groupBy("customer_unique_id")
        .agg(
            F.first("customer_city").alias("customer_city"),
            F.first("customer_state").alias("customer_state"),
            F.first("region").alias("region"),
        )
    )

    dim = canonical.join(customer_stats, on="customer_unique_id", how="left")

    # Segment by lifetime value using existing business rules
    dim = dim.withColumn(
        "customer_segment",
        F.when(F.col("lifetime_value") >= 500, "High")
        .when(F.col("lifetime_value") >= 200, "Medium")
        .otherwise("Low"),
    )

    # Surrogate key
    dim = dim.withColumn("customer_key", F.monotonically_increasing_id())

    # Final column order
    return dim.select(
        "customer_key",
        "customer_unique_id",
        "customer_city",
        "customer_state",
        "region",
        "customer_since",
        "total_orders",
        "lifetime_value",
        "customer_segment",
    )


def run_dim_customer(
    silver_path: Path,
    gold_path: Path,
    spark: SparkSession | None = None,
) -> None:
    own_spark = spark is None
    if own_spark:
        spark = get_spark_session("GoldDimCustomer")

    logger.info("Building dim_customer from Silver layer")
    customers = spark.read.parquet(str(silver_path / "customers"))
    orders    = spark.read.parquet(str(silver_path / "orders"))
    payments  = spark.read.parquet(str(silver_path / "payments"))

    dim = build_dim_customer(customers, orders, payments)

    target = gold_path / "dim_customer"
    target.mkdir(parents=True, exist_ok=True)
    dim.write.format("parquet").mode("overwrite").save(str(target))
    logger.info("dim_customer written → %s (%d rows)", target, dim.count())

    if own_spark:
        spark.stop()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    run_dim_customer(
        silver_path=Path(os.getenv("SILVER_PATH", "./data/silver")),
        gold_path=Path(os.getenv("GOLD_PATH", "./data/gold")),
    )
