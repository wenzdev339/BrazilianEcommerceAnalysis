"""
Silver Layer — Order Items

Transforms:
  - Cast price and freight_value to DecimalType (already done in schema, verify)
  - Compute item_total = price + freight_value
  - Parse shipping_limit_date timestamp
  - Remove rows with null product_id or seller_id (orphaned items)
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

TS_FORMAT = "M/d/yyyy H:mm"


def transform_order_items(df: DataFrame) -> DataFrame:
    meta_cols = [c for c in df.columns if c.startswith("_")]
    df = df.drop(*meta_cols)

    # Parse shipping_limit_date
    df = df.withColumn(
        "shipping_limit_date",
        F.to_timestamp(F.col("shipping_limit_date"), TS_FORMAT),
    )

    # Ensure price and freight are proper decimals
    df = (
        df
        .withColumn("price",         F.col("price").cast(DecimalType(10, 2)))
        .withColumn("freight_value", F.col("freight_value").cast(DecimalType(10, 2)))
    )

    # Derived: total per line item
    df = df.withColumn("item_total", F.col("price") + F.col("freight_value"))

    # Drop orphaned rows
    before = df.count()
    df = df.filter(F.col("product_id").isNotNull() & F.col("seller_id").isNotNull())
    dropped = before - df.count()
    if dropped:
        logger.warning("Dropped %d orphaned order_items rows", dropped)

    return df


def run_silver_order_items(
    bronze_path: Path,
    silver_path: Path,
    spark: SparkSession | None = None,
) -> None:
    own_spark = spark is None
    if own_spark:
        spark = get_spark_session("SilverOrderItems")

    logger.info("Silver ← order_items (Bronze)")
    df = spark.read.parquet(str(bronze_path / "order_items"))
    silver_df = transform_order_items(df)

    target = silver_path / "order_items"
    target.mkdir(parents=True, exist_ok=True)
    silver_df.write.format("parquet").mode("overwrite").save(str(target))
    logger.info("Silver order_items written → %s", target)

    if own_spark:
        spark.stop()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    run_silver_order_items(
        bronze_path=Path(os.getenv("BRONZE_PATH", "./data/bronze")),
        silver_path=Path(os.getenv("SILVER_PATH", "./data/silver")),
    )
