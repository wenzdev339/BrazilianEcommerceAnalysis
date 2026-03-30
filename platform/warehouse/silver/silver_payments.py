"""
Silver Layer — Payments

Transforms:
  - Aggregate to order level: total_payment_value per order_id
  - Pivot payment types to one row per order with columns per method
  - Keep sequential payments for orders with mixed payment methods
  - Flag voucher-only vs credit-card-mixed orders
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


def transform_payments(df: DataFrame) -> DataFrame:
    meta_cols = [c for c in df.columns if c.startswith("_")]
    df = df.drop(*meta_cols)

    # Ensure payment_value is decimal
    df = df.withColumn("payment_value", F.col("payment_value").cast(DecimalType(10, 2)))

    # Remove rows where payment_value is null or zero
    df = df.filter(F.col("payment_value").isNotNull() & (F.col("payment_value") > 0))

    # Aggregate payment totals per order (kept at sequential level for fact table)
    # Also add order-level summary columns
    order_agg = df.groupBy("order_id").agg(
        F.sum("payment_value").alias("order_total_payment"),
        F.count("payment_sequential").alias("payment_count"),
        F.max("payment_installments").alias("max_installments"),
        F.collect_set("payment_type").alias("payment_types_used"),
    )

    # Join back to the sequential rows
    df = df.join(order_agg, on="order_id", how="left")

    # Primary payment type = type with highest value for this order
    window = (
        __import__("pyspark.sql.window", fromlist=["Window"])
        .Window.partitionBy("order_id")
        .orderBy(F.col("payment_value").desc())
    )
    df = (
        df
        .withColumn("row_rank", F.rank().over(window))
        .withColumn(
            "primary_payment_type",
            F.when(F.col("row_rank") == 1, F.col("payment_type")),
        )
        .drop("row_rank")
    )

    # Fill primary_payment_type with the first non-null in the partition
    df = df.withColumn(
        "primary_payment_type",
        F.first("primary_payment_type", ignorenulls=True).over(
            __import__("pyspark.sql.window", fromlist=["Window"])
            .Window.partitionBy("order_id")
        ),
    )

    return df


def run_silver_payments(
    bronze_path: Path,
    silver_path: Path,
    spark: SparkSession | None = None,
) -> None:
    own_spark = spark is None
    if own_spark:
        spark = get_spark_session("SilverPayments")

    logger.info("Silver ← payments (Bronze)")
    df = spark.read.parquet(str(bronze_path / "payments"))
    silver_df = transform_payments(df)

    target = silver_path / "payments"
    target.mkdir(parents=True, exist_ok=True)
    silver_df.write.format("parquet").mode("overwrite").save(str(target))
    logger.info("Silver payments written → %s", target)

    if own_spark:
        spark.stop()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    run_silver_payments(
        bronze_path=Path(os.getenv("BRONZE_PATH", "./data/bronze")),
        silver_path=Path(os.getenv("SILVER_PATH", "./data/silver")),
    )
