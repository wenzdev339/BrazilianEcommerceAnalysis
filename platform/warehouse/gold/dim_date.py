"""
Gold Layer — dim_date

Generates a complete date dimension from 2016-01-01 to 2019-12-31.
This dimension is produced entirely in code — no source data needed.

Columns:
  date_key        INTEGER   YYYYMMDD (surrogate key used in fact table)
  full_date       DATE
  year            INTEGER
  quarter         INTEGER   1-4
  month           INTEGER   1-12
  month_name      STRING    "January" … "December"
  week_of_year    INTEGER   ISO week number
  day_of_week     INTEGER   1=Monday … 7=Sunday (ISO)
  day_name        STRING    "Monday" … "Sunday"
  day_of_month    INTEGER   1-31
  is_weekend      BOOLEAN
  semester        INTEGER   1 or 2 (common in Brazilian reporting)
"""

from __future__ import annotations

import logging
import os
import sys
from pathlib import Path

import pandas as pd
from pyspark.sql import SparkSession
from pyspark.sql import functions as F

sys.path.insert(0, str(Path(__file__).parent.parent.parent))
from ingestion.spark_session import get_spark_session

logger = logging.getLogger(__name__)

START_DATE = "2016-01-01"
END_DATE   = "2019-12-31"


def build_dim_date(spark: SparkSession) -> None:
    """Generate date dimension and return as a Spark DataFrame."""

    # Build with pandas — date spine is small enough
    dates = pd.date_range(start=START_DATE, end=END_DATE, freq="D")

    rows = []
    for d in dates:
        rows.append(
            {
                "date_key":     int(d.strftime("%Y%m%d")),
                "full_date":    d.date().isoformat(),
                "year":         d.year,
                "quarter":      d.quarter,
                "month":        d.month,
                "month_name":   d.strftime("%B"),
                "week_of_year": d.isocalendar().week,
                "day_of_week":  d.isoweekday(),         # 1=Mon, 7=Sun
                "day_name":     d.strftime("%A"),
                "day_of_month": d.day,
                "is_weekend":   d.isoweekday() in (6, 7),
                "semester":     1 if d.month <= 6 else 2,
            }
        )

    pdf = pd.DataFrame(rows)
    df = spark.createDataFrame(pdf)

    # Ensure date_key is unique (sanity check)
    assert df.select("date_key").distinct().count() == len(rows), "Duplicate date_keys!"

    logger.info(
        "dim_date generated: %d rows (%s → %s)", len(rows), START_DATE, END_DATE
    )
    return df


def run_dim_date(gold_path: Path, spark: SparkSession | None = None) -> None:
    own_spark = spark is None
    if own_spark:
        spark = get_spark_session("GoldDimDate")

    df = build_dim_date(spark)

    target = gold_path / "dim_date"
    target.mkdir(parents=True, exist_ok=True)
    df.write.format("parquet").mode("overwrite").save(str(target))
    logger.info("dim_date written → %s", target)

    if own_spark:
        spark.stop()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    run_dim_date(gold_path=Path(os.getenv("GOLD_PATH", "./data/gold")))
