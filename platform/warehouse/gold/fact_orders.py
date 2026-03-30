"""
Gold Layer — fact_orders

Grain: one row per order_item (order_id + order_item_id).

An order can have multiple items from different sellers/products, so we
model at order-item grain to allow clean slicing by product and seller.

Foreign keys:
  customer_key    → dim_customer
  product_key     → dim_product
  seller_key      → dim_seller (seller_id used directly, no separate dim built here)
  order_date_key  → dim_date (YYYYMMDD integer)
  delivery_date_key → dim_date

Measures:
  price                  DECIMAL  Item price (from order_items)
  freight_value          DECIMAL  Freight for this item
  item_total             DECIMAL  price + freight_value
  payment_value_alloc    DECIMAL  Proportional payment allocation (see note below)
  review_score           INTEGER  Nullable — not all orders have reviews
  delivery_days          INTEGER  Nullable — only for delivered orders
  is_late_delivery       BOOLEAN  Nullable

Note on payment allocation:
  Payments are at order level, not item level. We allocate payment_value
  proportionally by item price / order total price. This is disclosed in
  data_dictionary.md and is within 0.1% of total due to rounding.
"""

from __future__ import annotations

import logging
import os
import sys
from pathlib import Path

from pyspark.sql import DataFrame, SparkSession
from pyspark.sql import functions as F
from pyspark.sql.types import DecimalType
from pyspark.sql.window import Window

sys.path.insert(0, str(Path(__file__).parent.parent.parent))
from ingestion.spark_session import get_spark_session

logger = logging.getLogger(__name__)


def date_to_key(col_name: str) -> F.Column:
    """Convert a TimestampType column to an integer YYYYMMDD date key."""
    return F.date_format(F.col(col_name), "yyyyMMdd").cast("int")


def build_fact_orders(
    silver_orders: DataFrame,
    silver_order_items: DataFrame,
    silver_payments: DataFrame,
    silver_reviews: DataFrame,
    silver_customers: DataFrame,
    dim_customer: DataFrame,
    dim_product: DataFrame,
) -> DataFrame:

    # ── Step 1: Order-level payment totals ────────────────────────────────────
    order_payments = (
        silver_payments
        .groupBy("order_id")
        .agg(
            F.sum("payment_value").cast(DecimalType(12, 2)).alias("order_total_payment"),
            F.first("primary_payment_type").alias("primary_payment_type"),
            F.max("max_installments").alias("payment_installments"),
        )
    )

    # ── Step 2: Order-level totals for proportional allocation ────────────────
    order_item_totals = (
        silver_order_items
        .groupBy("order_id")
        .agg(F.sum("price").alias("order_total_price"))
    )

    # ── Step 3: Review per order (one review per order, take first if multiple)──
    reviews_dedup = (
        silver_reviews
        .select("order_id", "review_score", "has_written_review")
        .dropDuplicates(["order_id"])
    )

    # ── Step 4: Map customer_id → customer_key ────────────────────────────────
    id_to_unique = silver_customers.select("customer_id", "customer_unique_id")
    unique_to_key = dim_customer.select("customer_unique_id", "customer_key")
    customer_key_map = (
        id_to_unique
        .join(unique_to_key, on="customer_unique_id", how="left")
        .select("customer_id", "customer_key")
    )

    # ── Step 5: Map product_id → product_key ─────────────────────────────────
    product_key_map = dim_product.select("product_id", "product_key")

    # ── Step 6: Build fact table ──────────────────────────────────────────────
    fact = (
        silver_order_items
        # Join order-level attributes
        .join(silver_orders.select(
            "order_id", "customer_id", "order_status",
            "order_purchase_timestamp", "order_delivered_customer_date",
            "delivery_days", "is_late_delivery",
        ), on="order_id", how="inner")
        # Join payment info
        .join(order_payments, on="order_id", how="left")
        .join(order_item_totals, on="order_id", how="left")
        # Join reviews
        .join(reviews_dedup, on="order_id", how="left")
        # Join dimension keys
        .join(customer_key_map, on="customer_id", how="left")
        .join(product_key_map, on="product_id", how="left")
    )

    # ── Step 7: Proportional payment allocation ───────────────────────────────
    fact = fact.withColumn(
        "payment_value_alloc",
        F.when(
            F.col("order_total_price") > 0,
            (F.col("price") / F.col("order_total_price") * F.col("order_total_payment"))
            .cast(DecimalType(10, 2)),
        ).otherwise(F.lit(None).cast(DecimalType(10, 2))),
    )

    # ── Step 8: Date keys ─────────────────────────────────────────────────────
    fact = (
        fact
        .withColumn("order_date_key",    date_to_key("order_purchase_timestamp"))
        .withColumn("delivery_date_key", date_to_key("order_delivered_customer_date"))
    )

    # ── Step 9: Final column selection ────────────────────────────────────────
    return fact.select(
        # Keys
        F.col("order_id"),
        F.col("order_item_id"),
        F.col("customer_key"),
        F.col("product_key"),
        F.col("seller_id"),          # seller dimension kept as natural key for simplicity
        F.col("order_date_key"),
        F.col("delivery_date_key"),
        # Order attributes
        F.col("order_status"),
        # Measures
        F.col("price"),
        F.col("freight_value"),
        F.col("item_total"),
        F.col("payment_value_alloc"),
        F.col("primary_payment_type"),
        F.col("payment_installments"),
        # Review
        F.col("review_score"),
        F.col("has_written_review"),
        # Delivery
        F.col("delivery_days"),
        F.col("is_late_delivery"),
    )


def run_fact_orders(
    silver_path: Path,
    gold_path: Path,
    spark: SparkSession | None = None,
) -> None:
    own_spark = spark is None
    if own_spark:
        spark = get_spark_session("GoldFactOrders")

    logger.info("Building fact_orders from Silver + Gold dims")

    silver_orders      = spark.read.parquet(str(silver_path / "orders"))
    silver_order_items = spark.read.parquet(str(silver_path / "order_items"))
    silver_payments    = spark.read.parquet(str(silver_path / "payments"))
    silver_reviews     = spark.read.parquet(str(silver_path / "reviews"))
    silver_customers   = spark.read.parquet(str(silver_path / "customers"))
    dim_customer       = spark.read.parquet(str(gold_path   / "dim_customer"))
    dim_product        = spark.read.parquet(str(gold_path   / "dim_product"))

    fact = build_fact_orders(
        silver_orders,
        silver_order_items,
        silver_payments,
        silver_reviews,
        silver_customers,
        dim_customer,
        dim_product,
    )

    target = gold_path / "fact_orders"
    target.mkdir(parents=True, exist_ok=True)

    (
        fact.write
        .format("parquet")
        .mode("overwrite")
        .partitionBy("order_date_key")
        .save(str(target))
    )
    logger.info("fact_orders written → %s (%d rows)", target, fact.count())

    if own_spark:
        spark.stop()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    run_fact_orders(
        silver_path=Path(os.getenv("SILVER_PATH", "./data/silver")),
        gold_path=Path(os.getenv("GOLD_PATH", "./data/gold")),
    )
