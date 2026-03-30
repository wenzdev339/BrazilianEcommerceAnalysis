"""
Customers router — segmentation and geographic analysis.
"""

from fastapi import APIRouter, Depends, Query
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from api.database import get_db
from api.schemas.customers import CustomerSegmentsResponse, TopStatesResponse

router = APIRouter()

DWH = "olist_dwh"


@router.get(
    "/segments",
    response_model=CustomerSegmentsResponse,
    summary="Customer segmentation by lifetime value",
    description="""
    Segments customers into High (≥ R$500), Medium (≥ R$200), and Low (< R$200)
    tiers based on total lifetime spend on delivered orders.
    """,
)
async def get_customer_segments(db: AsyncSession = Depends(get_db)):
    sql = text(f"""
        with totals as (
            select count(*) as total_customers from {DWH}.dim_customer
        )
        select
            dc.customer_segment,
            count(*)                                as customer_count,
            sum(dc.lifetime_value)::numeric(14,2)   as total_lifetime_value,
            avg(dc.lifetime_value)::numeric(10,2)   as avg_lifetime_value,
            round(count(*)::numeric / t.total_customers * 100, 2) as pct_of_customers
        from {DWH}.dim_customer dc
        cross join totals t
        group by dc.customer_segment, t.total_customers
        order by avg_lifetime_value desc
    """)
    result = await db.execute(sql)
    rows = result.mappings().all()

    total_sql = text(f"select count(*) as n from {DWH}.dim_customer")
    total_result = await db.execute(total_sql)
    total = total_result.scalar()

    return CustomerSegmentsResponse(data=list(rows), total_customers=total)


@router.get(
    "/top-states",
    response_model=TopStatesResponse,
    summary="Top states by revenue and customer count",
    description="Ranks Brazilian states by total delivered order revenue.",
)
async def get_top_states(
    limit: int = Query(10, ge=1, le=27, description="Number of states to return"),
    db: AsyncSession = Depends(get_db),
):
    sql = text(f"""
        select
            dc.customer_state,
            dc.region,
            count(distinct dc.customer_unique_id)   as customer_count,
            sum(f.item_total)::numeric(14,2)        as total_revenue,
            avg(f.item_total)::numeric(10,2)        as avg_order_value
        from {DWH}.fact_orders f
        join {DWH}.dim_customer dc using (customer_key)
        where f.order_status = 'delivered'
        group by dc.customer_state, dc.region
        order by total_revenue desc
        limit :limit
    """)
    result = await db.execute(sql, {"limit": limit})
    return TopStatesResponse(data=list(result.mappings().all()))


@router.get(
    "/repeat-rate",
    summary="Repeat customer rate",
    description="Percentage of customers who placed more than one delivered order.",
)
async def get_repeat_rate(db: AsyncSession = Depends(get_db)):
    sql = text(f"""
        select
            count(*) filter (where total_orders > 1) as repeat_customers,
            count(*)                                  as total_customers,
            round(
                count(*) filter (where total_orders > 1)::numeric / count(*) * 100,
                2
            )                                         as repeat_rate_pct
        from {DWH}.dim_customer
    """)
    result = await db.execute(sql)
    return dict(result.mappings().first())
