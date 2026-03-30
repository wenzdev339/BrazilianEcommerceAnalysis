"""
Gold Layer — dim_product

Columns:
  product_key                  INTEGER  Surrogate key
  product_id                   STRING   Business key
  product_category_name        STRING   Portuguese category
  product_category_name_english STRING  English category
  product_name_length          INTEGER
  product_description_length   INTEGER
  product_photos_qty           INTEGER
  product_weight_g             INTEGER
  product_length_cm            INTEGER
  product_height_cm            INTEGER
  product_width_cm             INTEGER
  product_volume_cm3           INTEGER  Derived
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


def build_dim_product(silver_products: DataFrame) -> DataFrame:
    dim = silver_products.withColumn("product_key", F.monotonically_increasing_id())

    return dim.select(
        "product_key",
        "product_id",
        "product_category_name",
        "product_category_name_english",
        "product_name_length",
        "product_description_length",
        "product_photos_qty",
        "product_weight_g",
        "product_length_cm",
        "product_height_cm",
        "product_width_cm",
        "product_volume_cm3",
    )


def run_dim_product(
    silver_path: Path,
    gold_path: Path,
    spark: SparkSession | None = None,
) -> None:
    own_spark = spark is None
    if own_spark:
        spark = get_spark_session("GoldDimProduct")

    logger.info("Building dim_product from Silver layer")
    products = spark.read.parquet(str(silver_path / "products"))
    dim = build_dim_product(products)

    target = gold_path / "dim_product"
    target.mkdir(parents=True, exist_ok=True)
    dim.write.format("parquet").mode("overwrite").save(str(target))
    logger.info("dim_product written → %s (%d rows)", target, dim.count())

    if own_spark:
        spark.stop()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    run_dim_product(
        silver_path=Path(os.getenv("SILVER_PATH", "./data/silver")),
        gold_path=Path(os.getenv("GOLD_PATH", "./data/gold")),
    )
