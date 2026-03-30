"""
Silver Layer — Products

Transforms:
  - Join with category_translation to add product_category_name_english
  - Rename typo columns: product_name_lenght → product_name_length (sic fixed)
  - Compute product_volume_cm3 = length × height × width
  - Fill missing category with 'uncategorized'
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


def transform_products(df: DataFrame, category_translation_df: DataFrame) -> DataFrame:
    # 1. Drop Bronze metadata
    meta_cols = [c for c in df.columns if c.startswith("_")]
    df = df.drop(*meta_cols)

    # 2. Fix typo column names
    df = (
        df
        .withColumnRenamed("product_name_lenght", "product_name_length")
        .withColumnRenamed("product_description_lenght", "product_description_length")
    )

    # 3. Join English category names
    cat_df = category_translation_df.drop(*[c for c in category_translation_df.columns if c.startswith("_")])
    df = df.join(cat_df, on="product_category_name", how="left")

    # 4. Fill missing categories
    df = (
        df
        .withColumn(
            "product_category_name",
            F.coalesce(F.col("product_category_name"), F.lit("uncategorized")),
        )
        .withColumn(
            "product_category_name_english",
            F.coalesce(F.col("product_category_name_english"), F.lit("uncategorized")),
        )
    )

    # 5. Compute volume
    df = df.withColumn(
        "product_volume_cm3",
        F.col("product_length_cm") * F.col("product_height_cm") * F.col("product_width_cm"),
    )

    return df


def run_silver_products(
    bronze_path: Path,
    silver_path: Path,
    spark: SparkSession | None = None,
) -> None:
    own_spark = spark is None
    if own_spark:
        spark = get_spark_session("SilverProducts")

    logger.info("Silver ← products (Bronze)")
    df = spark.read.parquet(str(bronze_path / "products"))
    cat_df = spark.read.parquet(str(bronze_path / "category_translation"))
    silver_df = transform_products(df, cat_df)

    target = silver_path / "products"
    target.mkdir(parents=True, exist_ok=True)
    silver_df.write.format("parquet").mode("overwrite").save(str(target))
    logger.info("Silver products written → %s", target)

    if own_spark:
        spark.stop()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    run_silver_products(
        bronze_path=Path(os.getenv("BRONZE_PATH", "./data/bronze")),
        silver_path=Path(os.getenv("SILVER_PATH", "./data/silver")),
    )
