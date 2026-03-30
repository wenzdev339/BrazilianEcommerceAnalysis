"""
Silver Layer — Sellers

Transforms:
  - Normalise city/state casing
  - Pad zip_code_prefix to 5 digits
  - Enrich with geolocation lat/lng (join on zip+state after geolocation Silver runs)
"""

from __future__ import annotations

import logging
import os
import sys
from pathlib import Path

from pyspark.sql import DataFrame, SparkSession
from pyspark.sql import functions as F

sys.path.insert(0, str(Path(__file__).parent.parent.parent))
from ingestion.spark_session import get_spark_session

logger = logging.getLogger(__name__)


def transform_sellers(df: DataFrame, geo_df: DataFrame | None = None) -> DataFrame:
    meta_cols = [c for c in df.columns if c.startswith("_")]
    df = df.drop(*meta_cols)

    df = (
        df
        .withColumn("seller_city",  F.initcap(F.lower(F.trim(F.col("seller_city")))))
        .withColumn("seller_state", F.upper(F.trim(F.col("seller_state"))))
        .withColumn(
            "seller_zip_code_prefix",
            F.lpad(F.col("seller_zip_code_prefix"), 5, "0"),
        )
    )

    # Optional geolocation enrichment
    if geo_df is not None:
        geo_clean = geo_df.select(
            F.col("geolocation_zip_code_prefix").alias("zip"),
            F.col("geolocation_state").alias("geo_state"),
            F.col("geolocation_lat").alias("seller_lat"),
            F.col("geolocation_lng").alias("seller_lng"),
        )
        df = df.join(
            geo_clean,
            (df["seller_zip_code_prefix"] == geo_clean["zip"])
            & (df["seller_state"] == geo_clean["geo_state"]),
            "left",
        ).drop("zip", "geo_state")

    return df


def run_silver_sellers(
    bronze_path: Path,
    silver_path: Path,
    spark: SparkSession | None = None,
) -> None:
    own_spark = spark is None
    if own_spark:
        spark = get_spark_session("SilverSellers")

    logger.info("Silver ← sellers (Bronze)")
    df = spark.read.parquet(str(bronze_path / "sellers"))

    # Enrich with Silver geolocation if available
    geo_path = silver_path / "geolocation"
    geo_df = None
    if geo_path.exists():
        geo_df = spark.read.parquet(str(geo_path))
        logger.info("Geolocation Silver found — enriching sellers")

    silver_df = transform_sellers(df, geo_df)

    target = silver_path / "sellers"
    target.mkdir(parents=True, exist_ok=True)
    silver_df.write.format("parquet").mode("overwrite").save(str(target))
    logger.info("Silver sellers written → %s", target)

    if own_spark:
        spark.stop()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    run_silver_sellers(
        bronze_path=Path(os.getenv("BRONZE_PATH", "./data/bronze")),
        silver_path=Path(os.getenv("SILVER_PATH", "./data/silver")),
    )
