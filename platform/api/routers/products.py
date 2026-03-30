"""
Products router — category performance and quality analysis.
"""

from fastapi import APIRouter, Depends, Query
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from api.database import get_db
from api.schemas.products import TopCategoriesResponse

router = APIRouter()

DWH = "olist_dwh"


@router.get(
    "/top-categories",
    response_model=TopCategoriesResponse,
    summary="Top product categories by revenue",
    description="""
    Returns the top N product categories ranked by total delivered revenue.
    Includes average review score and late delivery rate per category.
    """,
)
async def get_top_categories(
    limit: int = Query(10, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
):
    sql = text(f"""
        select
            dp.product_category_name_english,
            count(*)                                     as total_items_sold,
            sum(f.item_total)::numeric(14,2)             as total_revenue,
            avg(f.price)::numeric(10,2)                  as avg_price,
            avg(f.review_score)::numeric(4,2)            as avg_review_score,
            avg(case when f.is_late_delivery then 1.0 else 0.0 end)::numeric(6,4)
                                                         as late_delivery_rate
        from {DWH}.fact_orders f
        join {DWH}.dim_product dp using (product_key)
        where f.order_status = 'delivered'
        group by dp.product_category_name_english
        order by total_revenue desc
        limit :limit
    """)
    result = await db.execute(sql, {"limit": limit})
    rows = result.mappings().all()

    count_sql = text(f"""
        select count(distinct product_category_name_english) as n
        from {DWH}.dim_product
    """)
    total = (await db.execute(count_sql)).scalar()

    return TopCategoriesResponse(data=list(rows), total_categories=total)


@router.get(
    "/worst-reviewed",
    summary="Lowest-rated categories",
    description=f"""
    Categories with the worst average review scores.
    Only includes categories with at least 50 reviews (configurable).
    """,
)
async def get_worst_reviewed_categories(
    limit: int = Query(10, ge=1, le=50),
    min_reviews: int = Query(50, ge=1),
    db: AsyncSession = Depends(get_db),
):
    sql = text(f"""
        select
            dp.product_category_name_english,
            count(f.review_score) filter (where f.review_score is not null) as review_count,
            avg(f.review_score)::numeric(4,2)            as avg_review_score,
            avg(case when f.is_late_delivery then 1.0 else 0.0 end)::numeric(6,4)
                                                         as late_delivery_rate
        from {DWH}.fact_orders f
        join {DWH}.dim_product dp using (product_key)
        where f.order_status = 'delivered'
        group by dp.product_category_name_english
        having count(f.review_score) filter (where f.review_score is not null) >= :min_reviews
        order by avg_review_score asc
        limit :limit
    """)
    result = await db.execute(sql, {"limit": limit, "min_reviews": min_reviews})
    return {"data": list(result.mappings().all())}
