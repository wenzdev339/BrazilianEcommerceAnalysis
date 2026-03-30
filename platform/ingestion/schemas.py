"""
Explicit PySpark StructType schemas for all 9 Olist source CSV files.

Design decision: We define schemas explicitly rather than using inferSchema=True.
This makes contract violations visible at ingestion time (fail fast) instead of
silently producing incorrect types (e.g. numeric zip codes, wrong timestamp types).

Note on timestamps: order timestamps arrive as "M/D/YYYY H:MM" strings.
They are kept as StringType here and cast to TimestampType in the Silver layer.
"""

from pyspark.sql.types import (
    DecimalType,
    DoubleType,
    IntegerType,
    StringType,
    StructField,
    StructType,
)

# ── Customers ─────────────────────────────────────────────────────────────────
CUSTOMERS_SCHEMA = StructType(
    [
        StructField("customer_id", StringType(), nullable=False),
        StructField("customer_unique_id", StringType(), nullable=False),
        StructField("customer_zip_code_prefix", StringType(), nullable=True),
        StructField("customer_city", StringType(), nullable=True),
        StructField("customer_state", StringType(), nullable=True),
    ]
)

# ── Orders ────────────────────────────────────────────────────────────────────
# All timestamp columns arrive as strings; cast happens in Silver.
ORDERS_SCHEMA = StructType(
    [
        StructField("order_id", StringType(), nullable=False),
        StructField("customer_id", StringType(), nullable=False),
        StructField("order_status", StringType(), nullable=True),
        StructField("order_purchase_timestamp", StringType(), nullable=True),
        StructField("order_approved_at", StringType(), nullable=True),
        StructField("order_delivered_carrier_date", StringType(), nullable=True),
        StructField("order_delivered_customer_date", StringType(), nullable=True),
        StructField("order_estimated_delivery_date", StringType(), nullable=True),
    ]
)

# ── Order Items ───────────────────────────────────────────────────────────────
ORDER_ITEMS_SCHEMA = StructType(
    [
        StructField("order_id", StringType(), nullable=False),
        StructField("order_item_id", IntegerType(), nullable=False),
        StructField("product_id", StringType(), nullable=False),
        StructField("seller_id", StringType(), nullable=False),
        StructField("shipping_limit_date", StringType(), nullable=True),
        StructField("price", DecimalType(10, 2), nullable=True),
        StructField("freight_value", DecimalType(10, 2), nullable=True),
    ]
)

# ── Payments ──────────────────────────────────────────────────────────────────
PAYMENTS_SCHEMA = StructType(
    [
        StructField("order_id", StringType(), nullable=False),
        StructField("payment_sequential", IntegerType(), nullable=True),
        StructField("payment_type", StringType(), nullable=True),
        StructField("payment_installments", IntegerType(), nullable=True),
        StructField("payment_value", DecimalType(10, 2), nullable=True),
    ]
)

# ── Reviews ───────────────────────────────────────────────────────────────────
REVIEWS_SCHEMA = StructType(
    [
        StructField("review_id", StringType(), nullable=True),
        StructField("order_id", StringType(), nullable=False),
        StructField("review_score", IntegerType(), nullable=True),
        StructField("review_comment_title", StringType(), nullable=True),
        StructField("review_comment_message", StringType(), nullable=True),
        StructField("review_creation_date", StringType(), nullable=True),
        StructField("review_answer_timestamp", StringType(), nullable=True),
    ]
)

# ── Products ──────────────────────────────────────────────────────────────────
# Note: "product_name_lenght" (sic) is the actual column name in the source CSV.
PRODUCTS_SCHEMA = StructType(
    [
        StructField("product_id", StringType(), nullable=False),
        StructField("product_category_name", StringType(), nullable=True),
        StructField("product_name_lenght", IntegerType(), nullable=True),   # typo in source
        StructField("product_description_lenght", IntegerType(), nullable=True),  # typo in source
        StructField("product_photos_qty", IntegerType(), nullable=True),
        StructField("product_weight_g", IntegerType(), nullable=True),
        StructField("product_length_cm", IntegerType(), nullable=True),
        StructField("product_height_cm", IntegerType(), nullable=True),
        StructField("product_width_cm", IntegerType(), nullable=True),
    ]
)

# ── Sellers ───────────────────────────────────────────────────────────────────
SELLERS_SCHEMA = StructType(
    [
        StructField("seller_id", StringType(), nullable=False),
        StructField("seller_zip_code_prefix", StringType(), nullable=True),
        StructField("seller_city", StringType(), nullable=True),
        StructField("seller_state", StringType(), nullable=True),
    ]
)

# ── Geolocation ───────────────────────────────────────────────────────────────
# zip_code_prefix is numeric in the file but must be treated as a padded string.
# We read as StringType and keep it that way throughout the pipeline.
GEOLOCATION_SCHEMA = StructType(
    [
        StructField("geolocation_zip_code_prefix", StringType(), nullable=True),
        StructField("geolocation_lat", DoubleType(), nullable=True),
        StructField("geolocation_lng", DoubleType(), nullable=True),
        StructField("geolocation_city", StringType(), nullable=True),
        StructField("geolocation_state", StringType(), nullable=True),
    ]
)

# ── Category Name Translation ─────────────────────────────────────────────────
CATEGORY_TRANSLATION_SCHEMA = StructType(
    [
        StructField("product_category_name", StringType(), nullable=False),
        StructField("product_category_name_english", StringType(), nullable=False),
    ]
)

# ── Registry: table name → (file name, schema) ────────────────────────────────
SOURCE_REGISTRY: dict[str, tuple[str, StructType]] = {
    "customers":           ("olist_customers_dataset.csv",              CUSTOMERS_SCHEMA),
    "orders":              ("olist_orders_dataset.csv",                 ORDERS_SCHEMA),
    "order_items":         ("olist_order_items_dataset.csv",            ORDER_ITEMS_SCHEMA),
    "payments":            ("olist_order_payments_dataset.csv",         PAYMENTS_SCHEMA),
    "reviews":             ("olist_order_reviews_dataset.csv",          REVIEWS_SCHEMA),
    "products":            ("olist_products_dataset.csv",               PRODUCTS_SCHEMA),
    "sellers":             ("olist_sellers_dataset.csv",                SELLERS_SCHEMA),
    "geolocation":         ("olist_geolocation_dataset.csv",            GEOLOCATION_SCHEMA),
    "category_translation":("product_category_name_translation.csv",   CATEGORY_TRANSLATION_SCHEMA),
}

# Expected minimum row counts — used by RowCountValidator
MIN_ROW_COUNTS: dict[str, int] = {
    "customers":            90_000,
    "orders":               90_000,
    "order_items":         100_000,
    "payments":             95_000,
    "reviews":              95_000,
    "products":             30_000,
    "sellers":               2_500,
    "geolocation":         900_000,
    "category_translation":     70,
}
