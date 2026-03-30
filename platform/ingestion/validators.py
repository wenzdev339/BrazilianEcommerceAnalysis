"""
Data quality validators for the ingestion layer.

Each validator raises DataQualityError on failure so that Airflow marks
the task as FAILED rather than silently continuing with bad data.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import List

from pyspark.sql import DataFrame

logger = logging.getLogger(__name__)


class DataQualityError(Exception):
    """Raised when a data quality assertion fails."""


@dataclass
class ValidationResult:
    table: str
    passed: List[str] = field(default_factory=list)
    failed: List[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return len(self.failed) == 0

    def __str__(self) -> str:
        status = "PASSED" if self.ok else "FAILED"
        lines = [f"[{status}] {self.table} — {len(self.passed)} checks OK, {len(self.failed)} FAILED"]
        for msg in self.failed:
            lines.append(f"  ✗ {msg}")
        return "\n".join(lines)


# ── Schema Validator ──────────────────────────────────────────────────────────

def validate_schema(df: DataFrame, table: str, expected_columns: list[str]) -> ValidationResult:
    """
    Assert that all expected columns are present in the DataFrame.
    Extra columns in the DataFrame are allowed (additive contract).
    """
    result = ValidationResult(table=table)
    actual = set(df.columns)
    missing = [c for c in expected_columns if c not in actual]

    if missing:
        msg = f"Missing columns: {missing}"
        result.failed.append(msg)
        logger.error("[%s] Schema check FAILED — %s", table, msg)
    else:
        result.passed.append(f"All {len(expected_columns)} expected columns present")
        logger.info("[%s] Schema check PASSED", table)

    return result


# ── Row Count Validator ───────────────────────────────────────────────────────

def validate_row_count(
    df: DataFrame,
    table: str,
    min_rows: int,
) -> ValidationResult:
    """
    Assert that the DataFrame has at least `min_rows` rows.
    A 1% tolerance is not applied here — we use a hard minimum based on
    known dataset sizes to catch truncated file reads.
    """
    result = ValidationResult(table=table)
    actual_count = df.count()

    if actual_count < min_rows:
        msg = (
            f"Row count {actual_count:,} is below minimum threshold {min_rows:,}. "
            "Possible truncated or missing source file."
        )
        result.failed.append(msg)
        logger.error("[%s] Row count check FAILED — %s", table, msg)
    else:
        result.passed.append(f"Row count {actual_count:,} ≥ {min_rows:,}")
        logger.info("[%s] Row count check PASSED (%d rows)", table, actual_count)

    return result


# ── Null Validator ────────────────────────────────────────────────────────────

def validate_not_null(
    df: DataFrame,
    table: str,
    primary_key_columns: list[str],
) -> ValidationResult:
    """
    Assert that primary key columns contain no null values.
    Also logs null rates for non-PK columns as informational.
    """
    result = ValidationResult(table=table)

    for col_name in primary_key_columns:
        null_count = df.filter(df[col_name].isNull()).count()
        if null_count > 0:
            msg = f"Column '{col_name}' has {null_count:,} null values (PK must be non-null)"
            result.failed.append(msg)
            logger.error("[%s] Null check FAILED — %s", table, msg)
        else:
            result.passed.append(f"'{col_name}' has no nulls")
            logger.info("[%s] Null check PASSED for '%s'", table, col_name)

    return result


# ── Duplicate Validator ───────────────────────────────────────────────────────

def validate_no_duplicates(
    df: DataFrame,
    table: str,
    key_columns: list[str],
) -> ValidationResult:
    """
    Assert that the combination of `key_columns` is unique across all rows.
    Logs the duplicate count but only fails if duplicates exist.
    """
    result = ValidationResult(table=table)
    total = df.count()
    distinct = df.dropDuplicates(key_columns).count()
    duplicates = total - distinct

    if duplicates > 0:
        msg = (
            f"Found {duplicates:,} duplicate rows on key {key_columns} "
            f"(total={total:,}, distinct={distinct:,})"
        )
        result.failed.append(msg)
        logger.warning("[%s] Duplicate check WARNING — %s", table, msg)
    else:
        result.passed.append(f"No duplicates on {key_columns}")
        logger.info("[%s] Duplicate check PASSED on %s", table, key_columns)

    return result


# ── Range Validator ───────────────────────────────────────────────────────────

def validate_positive_values(
    df: DataFrame,
    table: str,
    numeric_columns: list[str],
) -> ValidationResult:
    """Assert that numeric columns contain only positive values (> 0)."""
    result = ValidationResult(table=table)

    for col_name in numeric_columns:
        invalid_count = df.filter(
            df[col_name].isNotNull() & (df[col_name] <= 0)
        ).count()

        if invalid_count > 0:
            msg = f"Column '{col_name}' has {invalid_count:,} non-positive values"
            result.failed.append(msg)
            logger.error("[%s] Range check FAILED — %s", table, msg)
        else:
            result.passed.append(f"'{col_name}' all values > 0")
            logger.info("[%s] Range check PASSED for '%s'", table, col_name)

    return result


# ── Composite runner ──────────────────────────────────────────────────────────

def run_all_validations(results: list[ValidationResult], raise_on_failure: bool = True) -> None:
    """
    Print all validation results and optionally raise DataQualityError
    if any check failed.
    """
    failed_tables = []
    for r in results:
        print(r)
        if not r.ok:
            failed_tables.append(r.table)

    if raise_on_failure and failed_tables:
        raise DataQualityError(
            f"Data quality checks FAILED for tables: {failed_tables}. "
            "Fix source data or adjust thresholds before proceeding."
        )
