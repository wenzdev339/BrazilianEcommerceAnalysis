# Platform Runbook

## Prerequisites

- Docker Desktop (with at least 6 GB RAM allocated to Docker)
- Python 3.11+ (for running scripts locally without Docker)
- Java 11+ (required by PySpark — check with `java -version`)

## Quick Start (Docker)

```bash
# 1. Clone and navigate
cd platform/

# 2. Set up environment variables
cp .env.example .env
# Edit .env with your PostgreSQL password (POSTGRES_PASSWORD=)

# 3. Start all services
docker-compose up -d

# 4. Initialise Airflow (first time only)
docker-compose run --rm airflow-init

# 5. Open Airflow UI
open http://localhost:8080
# Default credentials: admin / admin

# 6. Trigger the full pipeline
# In Airflow UI: enable DAG "00_full_pipeline" → Trigger DAG ▶

# 7. Open API docs
open http://localhost:8000/docs

# 8. Open Metabase (first-time setup wizard)
open http://localhost:3000
# Connect to: postgres / ecommerce / olist_dwh schema
```

## Running Locally (Without Docker)

```bash
# Install dependencies
pip install -r requirements.txt

# Set env vars
export $(cat .env | xargs)

# 1. Run ingestion pipeline
python -m ingestion.ingest_raw --datasets ../Datasets --output ./data/raw

# 2. Write Bronze
python warehouse/bronze/write_bronze.py

# 3. Transform Silver (run in order: geolocation first)
python warehouse/silver/silver_geolocation.py
python warehouse/silver/silver_customers.py
python warehouse/silver/silver_sellers.py
python warehouse/silver/silver_orders.py
python warehouse/silver/silver_order_items.py
python warehouse/silver/silver_payments.py
python warehouse/silver/silver_reviews.py
python warehouse/silver/silver_products.py

# 4. Build Gold
python warehouse/gold/dim_date.py
python warehouse/gold/dim_customer.py
python warehouse/gold/dim_product.py
python warehouse/gold/fact_orders.py

# 5. Run dbt (requires PostgreSQL running)
cd dbt/
dbt deps           # install dbt packages (dbt_utils, dbt_expectations)
dbt seed           # load brazil_state_region_map.csv
dbt build          # run all models + tests
dbt docs generate  # generate documentation site
dbt docs serve     # open http://localhost:8080

# 6. Start FastAPI
cd ..
uvicorn api.main:app --reload
# Open: http://localhost:8000/docs

# 7. Generate report
python reporting/generate_report.py
# Output: reports/output/report_YYYY-MM-DD.html
```

## Data Quality Checks

The pipeline uses fail-fast validation. If any check fails:
- Locally: `DataQualityError` is raised with a descriptive message
- In Airflow: the task is marked FAILED and downstream tasks do not run

To skip validation failures (development only):
```bash
python -m ingestion.ingest_raw --no-fail
```

## Troubleshooting

### PySpark out of memory on geolocation table
The geolocation table has 1M rows. If you get OOM errors:
```bash
export SPARK_DRIVER_MEMORY=4g
python warehouse/silver/silver_geolocation.py
```

### dbt connection refused
Ensure PostgreSQL is running and `.env` credentials match:
```bash
psql -h $POSTGRES_HOST -U $POSTGRES_USER -d $POSTGRES_DB -c "SELECT 1"
```

### dbt "relation does not exist" on staging models
The staging models expect the raw tables to be in the `public` schema.
Load the data using the PostgreSQL dump: `psql ecommerce < "Brazilian E-Commerce.sql"`

### Airflow "No module named ingestion"
Ensure the project directory is mounted at `/opt/airflow/project` and
`PYTHONPATH=/opt/airflow/project` is set in the Airflow environment.

### Metabase shows no data
- Verify dbt ran successfully: `dbt build` should complete with no test failures
- Check that the `olist_dwh` schema exists: `\dn` in psql
- In Metabase: Settings → Admin → Databases → Sync database

## Service URLs

| Service        | URL                        | Credentials      |
|----------------|----------------------------|------------------|
| Airflow UI     | http://localhost:8080       | admin / admin    |
| FastAPI Docs   | http://localhost:8000/docs  | —                |
| Metabase       | http://localhost:3000       | setup on first run|
| Spark UI       | http://localhost:8090       | —                |
| Adminer (DB)   | http://localhost:8888       | postgres / changeme|
