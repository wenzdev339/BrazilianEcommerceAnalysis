"""
Silver Layer — Reviews

Transforms:
  - Parse review timestamps
  - Normalise review_score to integer 1-5 (drop invalid values)
  - Set null for empty comment titles/messages (they arrive as empty strings)
  - Compute has_written_review boolean flag
  - Compute response_time_hours (review_creation to review_answer)
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

TS_FORMAT = "M/d/yyyy H:mm"


def transform_reviews(df: DataFrame) -> DataFrame:
    meta_cols = [c for c in df.columns if c.startswith("_")]
    df = df.drop(*meta_cols)

    # Parse timestamps
    for col_name in ["review_creation_date", "review_answer_timestamp"]:
        df = df.withColumn(col_name, F.to_timestamp(F.col(col_name), TS_FORMAT))

    # Validate score range
    df = df.filter(
        F.col("review_score").isNull()
        | F.col("review_score").between(1, 5)
    )

    # Null-ify empty comment strings
    df = (
        df
        .withColumn(
            "review_comment_title",
            F.when(
                F.trim(F.col("review_comment_title")) == "",
                F.lit(None),
            ).otherwise(F.col("review_comment_title")),
        )
        .withColumn(
            "review_comment_message",
            F.when(
                F.trim(F.col("review_comment_message")) == "",
                F.lit(None),
            ).otherwise(F.col("review_comment_message")),
        )
    )

    # Derived flags
    df = (
        df
        .withColumn(
            "has_written_review",
            F.col("review_comment_message").isNotNull(),
        )
        .withColumn(
            "response_time_hours",
            F.when(
                F.col("review_answer_timestamp").isNotNull()
                & F.col("review_creation_date").isNotNull(),
                (
                    F.unix_timestamp("review_answer_timestamp")
                    - F.unix_timestamp("review_creation_date")
                ) / 3600,
            ),
        )
    )

    return df


def run_silver_reviews(
    bronze_path: Path,
    silver_path: Path,
    spark: SparkSession | None = None,
) -> None:
    own_spark = spark is None
    if own_spark:
        spark = get_spark_session("SilverReviews")

    logger.info("Silver ← reviews (Bronze)")
    df = spark.read.parquet(str(bronze_path / "reviews"))
    silver_df = transform_reviews(df)

    target = silver_path / "reviews"
    target.mkdir(parents=True, exist_ok=True)
    silver_df.write.format("parquet").mode("overwrite").save(str(target))
    logger.info("Silver reviews written → %s", target)

    if own_spark:
        spark.stop()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    run_silver_reviews(
        bronze_path=Path(os.getenv("BRONZE_PATH", "./data/bronze")),
        silver_path=Path(os.getenv("SILVER_PATH", "./data/silver")),
    )
