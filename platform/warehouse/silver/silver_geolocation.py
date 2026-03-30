"""
Silver Layer — Geolocation

The source table has 1,000,163 rows but only ~19,000 distinct zip code prefixes.
Multiple lat/lng coordinates exist per prefix (different data providers).

Strategy: group by (zip_prefix, state), compute AVG(lat) and AVG(lng).
Result: one canonical coordinate per zip+state — used to enrich customers and sellers.
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


def transform_geolocation(df: DataFrame) -> DataFrame:
    # 1. Drop Bronze metadata
    meta_cols = [c for c in df.columns if c.startswith("_")]
    df = df.drop(*meta_cols)

    # 2. Normalise city casing and pad zip prefix
    df = (
        df
        .withColumn("geolocation_city",  F.initcap(F.lower(F.trim(F.col("geolocation_city")))))
        .withColumn("geolocation_state", F.upper(F.trim(F.col("geolocation_state"))))
        .withColumn(
            "geolocation_zip_code_prefix",
            F.lpad(F.col("geolocation_zip_code_prefix"), 5, "0"),
        )
    )

    # 3. Remove extreme coordinate outliers (Brazil bounding box)
    df = df.filter(
        (F.col("geolocation_lat").between(-34.0, 5.3))
        & (F.col("geolocation_lng").between(-73.99, -34.79))
    )

    # 4. Deduplicate: one row per zip prefix + state using avg coordinates
    df = (
        df
        .groupBy("geolocation_zip_code_prefix", "geolocation_state")
        .agg(
            F.avg("geolocation_lat").alias("geolocation_lat"),
            F.avg("geolocation_lng").alias("geolocation_lng"),
            F.first("geolocation_city").alias("geolocation_city"),
        )
    )

    logger.info(
        "Geolocation deduplicated: %d canonical zip+state combinations",
        df.count(),
    )
    return df


def run_silver_geolocation(
    bronze_path: Path,
    silver_path: Path,
    spark: SparkSession | None = None,
) -> None:
    own_spark = spark is None
    if own_spark:
        spark = get_spark_session("SilverGeolocation")

    logger.info("Silver ← geolocation (Bronze) — dedup 1M rows to ~19k")
    df = spark.read.parquet(str(bronze_path / "geolocation"))
    silver_df = transform_geolocation(df)

    target = silver_path / "geolocation"
    target.mkdir(parents=True, exist_ok=True)
    silver_df.write.format("parquet").mode("overwrite").save(str(target))
    logger.info("Silver geolocation written → %s", target)

    if own_spark:
        spark.stop()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    run_silver_geolocation(
        bronze_path=Path(os.getenv("BRONZE_PATH", "./data/bronze")),
        silver_path=Path(os.getenv("SILVER_PATH", "./data/silver")),
    )
