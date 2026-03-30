-- Initialise the ecommerce database schemas.
-- Called automatically by Postgres on first start via entrypoint.

-- Schema for raw/staging tables (loaded by dbt staging models)
CREATE SCHEMA IF NOT EXISTS bronze;
CREATE SCHEMA IF NOT EXISTS silver;
CREATE SCHEMA IF NOT EXISTS olist_dwh;   -- Gold / mart tables

-- Airflow uses the default public schema in the same DB for simplicity.
-- In production you would use a separate database for Airflow metadata.
