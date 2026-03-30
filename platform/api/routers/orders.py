"""
Orders router — revenue and delivery metrics.

Endpoints mirror the original SQL analysis from the README:
  - GET /orders/summary       → overall KPIs
  - GET /orders/monthly-trend → monthly revenue time series
  - GET /orders/payment-mix   → payment method breakdown
"""

from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from api.database import get_db
from api.schemas.orders import MonthlyRevenueResponse, OrderSummary

router = APIRouter()

DWH = "olist_dwh"


@router.get(
    "/summary",
    response_model=OrderSummary,
    summary="Overall order KPIs",
    description="""
    Returns headline metrics for all **delivered** orders:
    total orders, total revenue, average/median order value,
    late delivery rate, and average review score.
    """,
)
async def get_order_summary(db: AsyncSession = Depends(get_db)):
    sql = text(f"""
        with delivered as (
            select
                f.order_id,
                f.price,
                f.freight_value,
                f.item_total,
                f.payment_value_alloc,
                f.delivery_days,
                f.is_late_delivery,
                f.review_score
            from {DWH}.fact_orders f
            where f.order_status = 'delivered'
        ),
        order_level as (
            select
                order_id,
                sum(item_total)          as order_total,
                max(delivery_days)       as delivery_days,
                bool_or(is_late_delivery) as is_late,
                max(review_score)        as review_score
            from delivered
            group by order_id
        )
        select
            count(distinct order_id)                                  as total_orders,
            sum(order_total)::numeric(14,2)                           as total_revenue,
            avg(order_total)::numeric(10,2)                           as avg_order_value,
            percentile_cont(0.5) within group (order by order_total)::numeric(10,2)
                                                                      as median_order_value,
            avg(case when is_late then 1.0 else 0.0 end)::numeric(6,4)
                                                                      as late_delivery_rate,
            avg(delivery_days)::numeric(6,2)                          as avg_delivery_days,
            avg(review_score)::numeric(4,2)                           as avg_review_score
        from order_level
    """)
    result = await db.execute(sql)
    row = result.mappings().first()
    return OrderSummary(**row)


@router.get(
    "/monthly-trend",
    response_model=MonthlyRevenueResponse,
    summary="Monthly revenue time series",
    description="Returns pre-aggregated monthly revenue from the agg_monthly_revenue mart table.",
)
async def get_monthly_trend(
    year: Optional[int] = Query(None, description="Filter to a specific year (2016-2018)"),
    db: AsyncSession = Depends(get_db),
):
    where = "where 1=1"
    params: dict = {}
    if year:
        where += " and year = :year"
        params["year"] = year

    sql = text(f"""
        select
            year, month, month_name, year_month,
            total_orders, total_items, unique_customers,
            product_revenue, freight_revenue, total_revenue,
            avg_delivery_days, late_delivery_rate,
            avg_review_score, mom_revenue_growth_pct
        from {DWH}.agg_monthly_revenue
        {where}
        order by year, month
    """)
    result = await db.execute(sql, params)
    rows = result.mappings().all()
    return MonthlyRevenueResponse(data=list(rows), total_months=len(rows))


@router.get(
    "/payment-mix",
    summary="Payment method distribution",
    description="Breakdown of orders and revenue by payment type.",
)
async def get_payment_mix(db: AsyncSession = Depends(get_db)):
    sql = text(f"""
        select
            primary_payment_type                              as payment_type,
            count(distinct order_id)                         as order_count,
            sum(payment_value_alloc)::numeric(14,2)          as total_value,
            avg(payment_value_alloc)::numeric(10,2)          as avg_value,
            round(
                count(distinct order_id)::numeric /
                sum(count(distinct order_id)) over () * 100, 2
            )                                                as pct_orders
        from {DWH}.fact_orders
        where order_status = 'delivered'
          and primary_payment_type is not null
        group by primary_payment_type
        order by order_count desc
    """)
    result = await db.execute(sql)
    return {"data": list(result.mappings().all())}
