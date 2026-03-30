"""
Silver Layer — Orders

Transforms:
  - Parse mixed-format timestamps ("M/D/YYYY H:MM") → TimestampType
  - Derive delivery_days (integer), is_late_delivery (boolean)
  - Filter to meaningful order statuses for downstream modelling
  - Standardise order_status values to lowercase
"""

from __future__ import annotations

import logging
import os
import sys
from pathlib import Path

from pyspark.sql import DataFrame, SparkSession
from pyspark.sql import functions as F
from pyspark.sql.types import IntegerType

sys.path.insert(0, str(Path(__file__).parent.parent.parent))
from ingestion.spark_session import get_spark_session

logger = logging.getLogger(__name__)

# Timestamp format used in source CSVs  e.g. "10/2/2017 10:56"
TS_FORMAT = "M/d/yyyy H:mm"

# Statuses included downstream (exclude "unavailable" noise)
VALID_STATUSES = {
    "delivered", "shipped", "processing", "invoiced",
    "approved", "canceled", "created",
}


def transform_orders(df: DataFrame) -> DataFrame:
    """Apply all Silver transformations to the orders Bronze DataFrame."""

    ts_cols = [
        "order_purchase_timestamp",
        "order_approved_at",
        "order_delivered_carrier_date",
        "order_delivered_customer_date",
        "order_estimated_delivery_date",
    ]

    # 1. Parse timestamps from string to TimestampType
    for col_name in ts_cols:
        df = df.withColumn(col_name, F.to_timestamp(F.col(col_name), TS_FORMAT))

    # 2. Standardise order_status
    df = df.withColumn("order_status", F.lower(F.trim(F.col("order_status"))))

    # 3. Derive delivery metrics (only meaningful for delivered orders)
    df = df.withColumn(
        "delivery_days",
        F.when(
            F.col("order_delivered_customer_date").isNotNull()
            & F.col("order_purchase_timestamp").isNotNull(),
            F.datediff(
                F.col("order_delivered_customer_date"),
                F.col("order_purchase_timestamp"),
            ),
        ).cast(IntegerType()),
    )

    df = df.withColumn(
        "is_late_delivery",
        F.when(
            F.col("order_delivered_customer_date").isNotNull()
            & F.col("order_estimated_delivery_date").isNotNull(),
            F.col("order_delivered_customer_date") > F.col("order_estimated_delivery_date"),
        ).otherwise(F.lit(None).cast("boolean")),
    )

    # 4. Drop internal Bronze metadata columns
    meta_cols = [c for c in df.columns if c.startswith("_")]
    df = df.drop(*meta_cols)

    return df


def run_silver_orders(
    bronze_path: Path,
    silver_path: Path,
    spark: SparkSession | None = None,
) -> None:
    own_spark = spark is None
    if own_spark:
        spark = get_spark_session("SilverOrders")

    logger.info("Silver ← orders (Bronze)")
    df = spark.read.parquet(str(bronze_path / "orders"))
    silver_df = transform_orders(df)

    target = silver_path / "orders"
    target.mkdir(parents=True, exist_ok=True)
    silver_df.write.format("parquet").mode("overwrite").save(str(target))
    logger.info("Silver orders written → %s (%d rows)", target, silver_df.count())

    if own_spark:
        spark.stop()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    run_silver_orders(
        bronze_path=Path(os.getenv("BRONZE_PATH", "./data/bronze")),
        silver_path=Path(os.getenv("SILVER_PATH", "./data/silver")),
    )
