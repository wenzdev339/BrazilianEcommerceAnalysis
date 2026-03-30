# Platform Architecture

## Overview

This platform transforms the raw Olist Brazilian E-Commerce CSV files into a
production-quality data lakehouse with a serving layer, following the
**Medallion Architecture** (Bronze → Silver → Gold).

```
┌─────────────────────────────────────────────────────────────┐
│  Data Sources                                               │
│  9 × CSV files  (104 MB, 9 tables, ~1.5M total rows)       │
└──────────────────────────┬──────────────────────────────────┘
                           │  PySpark ingestion pipeline
                           ▼
┌─────────────────────────────────────────────────────────────┐
│  Raw Landing Zone  (Parquet, partitioned by ingestion_date) │
│  Adds: _ingested_at, _ingestion_date, _source_table         │
└──────────────────────────┬──────────────────────────────────┘
                           │  write_bronze.py
                           ▼
┌─────────────────────────────────────────────────────────────┐
│  BRONZE  (1:1 from source + pipeline metadata)              │
│  Adds: _bronze_loaded_at, _pipeline_version                 │
└──────────────────────────┬──────────────────────────────────┘
                           │  silver_*.py (one per table)
                           ▼
┌─────────────────────────────────────────────────────────────┐
│  SILVER  (cleansed, deduplicated, type-cast, enriched)      │
│  Key transforms:                                            │
│    orders      — timestamp parsing, delivery_days derived   │
│    customers   — ZIP pad, city/state normalise, region join │
│    geolocation — 1M rows → 19k unique zip+state (avg lat/lng)│
│    products    — typo columns fixed, English category joined│
│    sellers     — geolocation enrichment                     │
└──────────────────────────┬──────────────────────────────────┘
                           │  dim_*.py, fact_orders.py
                           ▼
┌─────────────────────────────────────────────────────────────┐
│  GOLD  (Star Schema — Parquet + PostgreSQL via dbt)         │
│                                                             │
│    dim_customer  — 1 row / customer_unique_id, LTV, segment │
│    dim_product   — 1 row / product_id, English category     │
│    dim_date      — Generated date spine 2016-2019           │
│    fact_orders   — Grain: order_item, all FKs + measures    │
│    agg_monthly_revenue — Pre-aggregated for BI              │
└──────┬──────────────────┬──────────────────────────────────┘
       │                  │
       ▼                  ▼
 FastAPI REST API    Metabase Dashboard
 /orders /customers  Revenue · Categories
 /products           Customer · Delivery
       │
       ▼
  Airflow Orchestration (weekly pipeline, 4 chained DAGs)
```

## Layer Details

### Layer 1 — Ingestion (PySpark)
- Reads CSVs with explicit `StructType` schemas (no inferSchema)
- Validates: schema completeness, row count minimums, PK nulls, positive values
- Raises `DataQualityError` on failure → Airflow marks task FAILED
- Writes Raw Parquet partitioned by `_ingestion_date`

### Layer 2 — Bronze
- 1:1 copy from Raw with pipeline metadata columns
- Forensic record — never modified after writing

### Layer 2 — Silver
- All type casting happens here (timestamps, decimals)
- Geolocation deduplicated from 1M → ~19k rows using avg lat/lng per zip+state
- Products: source typo columns renamed, English categories joined
- Customers/Sellers: enriched with canonical geolocation coordinates

### Layer 3 — Gold (Star Schema)
- **dim_date**: generated entirely in code — no source data needed
- **dim_customer**: resolved to `customer_unique_id`, includes LTV + segment
- **fact_orders**: grain = order_item; `payment_value_alloc` proportionally allocated
- **agg_monthly_revenue**: pre-aggregated for sub-second BI query response

### dbt Layer
- Targets the same PostgreSQL database
- Staging models: thin views over raw tables with renames + casts
- Intermediate models: ephemeral CTEs (no physical tables)
- Mart models: permanent tables in `olist_dwh` schema
- Tests: generic (not_null, unique, range) + singular (payment totals match, no orphans)

### Serving Layer
- **FastAPI** (`api/`): async REST API over `olist_dwh` schema
- **Metabase**: connects to PostgreSQL, uses `agg_monthly_revenue` for dashboards
- **Automated Reports** (`reporting/`): weekly HTML with embedded Matplotlib charts

### Orchestration
- **Airflow**: 4 independently triggerable DAGs + 1 master orchestrator
- DAG chaining via `TriggerDagRunOperator` with `wait_for_completion=True`
- `dag_bronze_silver`: geolocation runs before customers/sellers (dependency)
- `dag_gold_dbt`: dims in parallel → fact → dbt build → dbt test (fail-fast)
