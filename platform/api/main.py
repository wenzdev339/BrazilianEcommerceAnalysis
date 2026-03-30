"""
E-Commerce Data Platform — FastAPI Data API

Exposes the Gold layer (olist_dwh schema) via REST endpoints.
Each endpoint maps to one of the business questions from the original SQL analysis.

Docs: http://localhost:8000/docs
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api.routers import customers, health, orders, products

app = FastAPI(
    title="E-Commerce Data Platform API",
    description="""
    REST API over the Olist Brazilian E-Commerce Gold layer.

    Built on top of the **olist_dwh** PostgreSQL schema produced by the dbt pipeline.
    All endpoints are read-only and answer the same business questions as the
    original SQL analysis — but served at sub-second latency from pre-aggregated tables.

    **Data source**: Olist Brazilian E-Commerce Public Dataset (2016-2018)
    """,
    version="1.0.0",
    contact={"name": "Data Platform Team"},
    license_info={"name": "MIT"},
)

# Allow Metabase / front-end to call the API
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET"],
    allow_headers=["*"],
)

app.include_router(health.router,    tags=["Health"])
app.include_router(orders.router,    prefix="/orders",    tags=["Orders & Revenue"])
app.include_router(customers.router, prefix="/customers", tags=["Customers"])
app.include_router(products.router,  prefix="/products",  tags=["Products"])
