"""
Silver Layer — Customers

Transforms:
  - Normalise city and state to title case / uppercase
  - Pad zip_code_prefix to 5 digits (source can lose leading zeros)
  - Retain both customer_id and customer_unique_id (dedup to unique happens in Gold)
  - Add brazil_region lookup based on state code
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

# Brazilian state → macro-region mapping
STATE_REGION: dict[str, str] = {
    "SP": "Sudeste", "RJ": "Sudeste", "MG": "Sudeste", "ES": "Sudeste",
    "RS": "Sul",     "PR": "Sul",     "SC": "Sul",
    "BA": "Nordeste","PE": "Nordeste","CE": "Nordeste","MA": "Nordeste",
    "PB": "Nordeste","RN": "Nordeste","AL": "Nordeste","SE": "Nordeste","PI": "Nordeste",
    "AM": "Norte",   "PA": "Norte",   "RO": "Norte",  "AC": "Norte",
    "AP": "Norte",   "RR": "Norte",   "TO": "Norte",
    "GO": "Centro-Oeste","MT": "Centro-Oeste","MS": "Centro-Oeste","DF": "Centro-Oeste",
}


def build_region_map_df(spark: SparkSession) -> DataFrame:
    data = [{"state_code": k, "region": v} for k, v in STATE_REGION.items()]
    return spark.createDataFrame(data)


def transform_customers(df: DataFrame, spark: SparkSession) -> DataFrame:
    # 1. Drop Bronze metadata
    meta_cols = [c for c in df.columns if c.startswith("_")]
    df = df.drop(*meta_cols)

    # 2. Normalise city (title case) and state (upper)
    df = (
        df
        .withColumn("customer_city",  F.initcap(F.lower(F.trim(F.col("customer_city")))))
        .withColumn("customer_state", F.upper(F.trim(F.col("customer_state"))))
    )

    # 3. Pad zip prefix to 5 chars (leading zeros may be lost in CSV)
    df = df.withColumn(
        "customer_zip_code_prefix",
        F.lpad(F.col("customer_zip_code_prefix"), 5, "0"),
    )

    # 4. Join region
    region_df = build_region_map_df(spark)
    df = (
        df
        .join(region_df, df["customer_state"] == region_df["state_code"], "left")
        .drop("state_code")
    )

    return df


def run_silver_customers(
    bronze_path: Path,
    silver_path: Path,
    spark: SparkSession | None = None,
) -> None:
    own_spark = spark is None
    if own_spark:
        spark = get_spark_session("SilverCustomers")

    logger.info("Silver ← customers (Bronze)")
    df = spark.read.parquet(str(bronze_path / "customers"))
    silver_df = transform_customers(df, spark)

    target = silver_path / "customers"
    target.mkdir(parents=True, exist_ok=True)
    silver_df.write.format("parquet").mode("overwrite").save(str(target))
    logger.info("Silver customers written → %s", target)

    if own_spark:
        spark.stop()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    run_silver_customers(
        bronze_path=Path(os.getenv("BRONZE_PATH", "./data/bronze")),
        silver_path=Path(os.getenv("SILVER_PATH", "./data/silver")),
    )
