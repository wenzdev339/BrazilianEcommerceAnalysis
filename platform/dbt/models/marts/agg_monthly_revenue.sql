{{
  config(
    materialized = 'table',
    description  = 'Pre-aggregated monthly revenue summary — powers the Metabase revenue trend chart.'
  )
}}

with fact as (
    select * from {{ ref('fact_orders') }}
    where order_status = 'delivered'
),

dim_date as (
    select * from {{ ref('dim_date') }}
),

monthly as (
    select
        d.year,
        d.month,
        d.month_name,
        -- Format as YYYY-MM for time-series charts
        d.year || '-' || lpad(d.month::text, 2, '0')   as year_month,

        count(distinct f.order_id)                      as total_orders,
        count(*)                                        as total_items,
        count(distinct f.customer_key)                  as unique_customers,

        -- Revenue
        sum(f.price)::numeric(14, 2)                    as product_revenue,
        sum(f.freight_value)::numeric(14, 2)            as freight_revenue,
        sum(f.item_total)::numeric(14, 2)               as total_revenue,

        -- Order value stats (at order level via payment_value_alloc aggregated)
        avg(f.payment_value_alloc)::numeric(10, 2)      as avg_item_value,

        -- Delivery quality
        avg(f.delivery_days)::numeric(6, 1)             as avg_delivery_days,
        sum(case when f.is_late_delivery then 1 else 0 end)::float
            / nullif(count(*), 0)                       as late_delivery_rate,

        -- Review quality
        avg(f.review_score)::numeric(4, 2)              as avg_review_score

    from fact f
    join dim_date d on f.order_date_key = d.date_key
    group by d.year, d.month, d.month_name
)

select
    *,
    -- Month-over-month growth (use lag for trend analysis)
    round(
        (total_revenue - lag(total_revenue) over (order by year, month))
        / nullif(lag(total_revenue) over (order by year, month), 0) * 100,
        2
    ) as mom_revenue_growth_pct
from monthly
order by year, month
