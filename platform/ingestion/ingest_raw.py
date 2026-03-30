"""
Layer 1 — PySpark Ingestion Pipeline

Reads all 9 source CSV files from the Datasets/ directory, runs data quality
checks, then writes validated data to the Raw landing zone as Parquet files
partitioned by ingestion date.

Usage:
    python -m ingestion.ingest_raw                        # uses .env defaults
    python -m ingestion.ingest_raw --datasets /path/to/csvs --output ./data/raw
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
from datetime import date
from pathlib import Path

from dotenv import load_dotenv
from pyspark.sql import DataFrame, SparkSession
from pyspark.sql import functions as F

# Local imports
sys.path.insert(0, str(Path(__file__).parent.parent))
from ingestion.schemas import MIN_ROW_COUNTS, SOURCE_REGISTRY
from ingestion.spark_session import get_spark_session
from ingestion.validators import (
    ValidationResult,
    run_all_validations,
    validate_no_duplicates,
    validate_not_null,
    validate_positive_values,
    validate_row_count,
    validate_schema,
)

load_dotenv()
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(name)s — %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)

# ── Per-table validation rules ────────────────────────────────────────────────
VALIDATION_RULES: dict[str, dict] = {
    "customers": {
        "pk_columns":       ["customer_id"],
        "dedupe_key":       ["customer_id"],
        "positive_columns": [],
    },
    "orders": {
        "pk_columns":       ["order_id"],
        "dedupe_key":       ["order_id"],
        "positive_columns": [],
    },
    "order_items": {
        "pk_columns":       ["order_id", "order_item_id"],
        "dedupe_key":       ["order_id", "order_item_id"],
        "positive_columns": ["price", "freight_value"],
    },
    "payments": {
        "pk_columns":       ["order_id"],
        "dedupe_key":       ["order_id", "payment_sequential"],
        "positive_columns": ["payment_value"],
    },
    "reviews": {
        "pk_columns":       ["order_id"],
        "dedupe_key":       ["review_id"],
        "positive_columns": [],
    },
    "products": {
        "pk_columns":       ["product_id"],
        "dedupe_key":       ["product_id"],
        "positive_columns": [],
    },
    "sellers": {
        "pk_columns":       ["seller_id"],
        "dedupe_key":       ["seller_id"],
        "positive_columns": [],
    },
    "geolocation": {
        "pk_columns":       [],   # intentionally no PK — duplicates are expected
        "dedupe_key":       [],
        "positive_columns": [],
    },
    "category_translation": {
        "pk_columns":       ["product_category_name"],
        "dedupe_key":       ["product_category_name"],
        "positive_columns": [],
    },
}


def read_csv(spark: SparkSession, file_path: Path, schema) -> DataFrame:
    """Read a single CSV file with explicit schema and standard options."""
    logger.info("Reading CSV: %s", file_path)
    return (
        spark.read.format("csv")
        .option("header", "true")
        .option("quote", '"')
        .option("escape", '"')
        .option("nullValue", "")
        .option("emptyValue", "")
        .schema(schema)
        .load(str(file_path))
    )


def validate_table(
    df: DataFrame,
    table_name: str,
    schema,
) -> list[ValidationResult]:
    """Run all validation checks for a single table."""
    rules = VALIDATION_RULES[table_name]
    results: list[ValidationResult] = []

    # 1. Schema check
    results.append(
        validate_schema(df, table_name, schema.fieldNames())
    )

    # 2. Row count check
    results.append(
        validate_row_count(df, table_name, MIN_ROW_COUNTS[table_name])
    )

    # 3. Null check on primary keys
    if rules["pk_columns"]:
        results.append(
            validate_not_null(df, table_name, rules["pk_columns"])
        )

    # 4. Duplicate check on business key
    if rules["dedupe_key"]:
        results.append(
            validate_no_duplicates(df, table_name, rules["dedupe_key"])
        )

    # 5. Positive value check
    if rules["positive_columns"]:
        results.append(
            validate_positive_values(df, table_name, rules["positive_columns"])
        )

    return results


def write_raw(
    df: DataFrame,
    table_name: str,
    output_path: Path,
    ingestion_date: str,
) -> None:
    """
    Write DataFrame to the Raw landing zone as Parquet.

    Adds metadata columns and partitions by ingestion_date so that
    re-running the pipeline does not overwrite prior runs.
    """
    target = output_path / table_name

    enriched = (
        df
        .withColumn("_ingested_at", F.current_timestamp())
        .withColumn("_ingestion_date", F.lit(ingestion_date))
        .withColumn("_source_table", F.lit(table_name))
    )

    (
        enriched.write
        .format("parquet")
        .mode("overwrite")
        .partitionBy("_ingestion_date")
        .save(str(target))
    )
    logger.info("Written Raw Parquet → %s (partition=%s)", target, ingestion_date)


# ── Main ──────────────────────────────────────────────────────────────────────

def run_ingestion(
    datasets_path: Path,
    output_path: Path,
    spark_master: str = "local[*]",
    raise_on_failure: bool = True,
) -> None:
    """Execute the full ingestion pipeline for all source tables."""

    spark = get_spark_session(app_name="EcommerceIngestion", master=spark_master)
    ingestion_date = date.today().isoformat()
    all_results: list[ValidationResult] = []

    logger.info("=" * 70)
    logger.info("E-Commerce Ingestion Pipeline — %s", ingestion_date)
    logger.info("Datasets path : %s", datasets_path)
    logger.info("Output path   : %s", output_path)
    logger.info("=" * 70)

    for table_name, (file_name, schema) in SOURCE_REGISTRY.items():
        file_path = datasets_path / file_name

        if not file_path.exists():
            logger.error("Source file not found: %s — skipping table '%s'", file_path, table_name)
            continue

        logger.info("── Processing: %s ──", table_name)

        # Read
        df = read_csv(spark, file_path, schema)

        # Validate
        results = validate_table(df, table_name, schema)
        all_results.extend(results)

        # Write (even if some non-critical checks failed; let caller decide)
        output_path.mkdir(parents=True, exist_ok=True)
        write_raw(df, table_name, output_path, ingestion_date)

    # Final summary
    logger.info("=" * 70)
    logger.info("Validation Summary")
    logger.info("=" * 70)
    run_all_validations(all_results, raise_on_failure=raise_on_failure)

    spark.stop()
    logger.info("Ingestion pipeline complete.")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Olist E-Commerce CSV Ingestion Pipeline")
    parser.add_argument(
        "--datasets",
        type=Path,
        default=Path(os.getenv("DATASETS_PATH", "../Datasets")),
        help="Path to the Datasets/ directory containing source CSV files.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path(os.getenv("RAW_PATH", "./data/raw")),
        help="Output path for Raw Parquet files.",
    )
    parser.add_argument(
        "--spark-master",
        default=os.getenv("SPARK_MASTER", "local[*]"),
        help="Spark master URL.",
    )
    parser.add_argument(
        "--no-fail",
        action="store_true",
        help="Log validation failures but do not raise an exception.",
    )
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    run_ingestion(
        datasets_path=args.datasets,
        output_path=args.output,
        spark_master=args.spark_master,
        raise_on_failure=not args.no_fail,
    )
