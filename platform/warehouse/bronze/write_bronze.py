"""
Layer 2a — Bronze Zone Writer

Reads Raw Parquet files (from the ingestion layer) and writes them 1:1 to
the Bronze zone, adding pipeline metadata columns.

Bronze = "exactly what arrived from source" + audit metadata.
No transformations are applied; this zone is the forensic record.
"""

from __future__ import annotations

import logging
import os
import sys
from pathlib import Path

from dotenv import load_dotenv
from pyspark.sql import DataFrame, SparkSession
from pyspark.sql import functions as F

sys.path.insert(0, str(Path(__file__).parent.parent.parent))
from ingestion.schemas import SOURCE_REGISTRY
from ingestion.spark_session import get_spark_session

load_dotenv()
logger = logging.getLogger(__name__)

PIPELINE_VERSION = "1.0.0"


def read_raw(spark: SparkSession, raw_path: Path, table_name: str) -> DataFrame:
    """Read the latest raw Parquet partition for a given table."""
    table_path = raw_path / table_name
    if not table_path.exists():
        raise FileNotFoundError(
            f"Raw zone table not found: {table_path}. "
            "Run ingestion/ingest_raw.py first."
        )
    return spark.read.parquet(str(table_path))


def write_bronze(
    df: DataFrame,
    table_name: str,
    bronze_path: Path,
) -> None:
    """
    Write a DataFrame to the Bronze zone with pipeline metadata.

    Columns added:
        _bronze_loaded_at   — timestamp when this Bronze write ran
        _pipeline_version   — version string for lineage tracking
    """
    enriched = (
        df
        .withColumn("_bronze_loaded_at", F.current_timestamp())
        .withColumn("_pipeline_version", F.lit(PIPELINE_VERSION))
        # Preserve the _ingestion_date partition from Raw for alignment
    )

    target = bronze_path / table_name
    target.mkdir(parents=True, exist_ok=True)

    (
        enriched.write
        .format("parquet")
        .mode("overwrite")
        .partitionBy("_ingestion_date")
        .save(str(target))
    )
    logger.info("Bronze written → %s", target)


def run_bronze(
    raw_path: Path,
    bronze_path: Path,
    spark_master: str = "local[*]",
) -> None:
    """Copy all Raw tables to Bronze with metadata enrichment."""
    spark = get_spark_session(app_name="EcommerceBronze", master=spark_master)

    for table_name in SOURCE_REGISTRY:
        logger.info("Bronze ← %s", table_name)
        try:
            df = read_raw(spark, raw_path, table_name)
            write_bronze(df, table_name, bronze_path)
        except FileNotFoundError as e:
            logger.warning("%s — skipping.", e)

    spark.stop()
    logger.info("Bronze layer complete.")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    run_bronze(
        raw_path=Path(os.getenv("RAW_PATH", "./data/raw")),
        bronze_path=Path(os.getenv("BRONZE_PATH", "./data/bronze")),
        spark_master=os.getenv("SPARK_MASTER", "local[*]"),
    )
