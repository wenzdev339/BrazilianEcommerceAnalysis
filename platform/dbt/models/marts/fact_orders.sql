{{
  config(
    materialized = 'table',
    description  = 'Central fact table — grain: one row per order_item. FK to all dimensions.'
  )
}}

with enriched as (
    select * from {{ ref('int_orders_enriched') }}
),

dim_customer as (
    select customer_key, customer_unique_id
    from {{ ref('dim_customer') }}
),

dim_product as (
    select product_key, product_id
    from {{ ref('dim_product') }}
),

stg_customers as (
    select customer_id, customer_unique_id
    from {{ ref('stg_customers') }}
),

dim_date as (
    select date_key, full_date
    from {{ ref('dim_date') }}
),

-- Resolve customer_id → customer_key via customer_unique_id
customer_key_map as (
    select
        sc.customer_id,
        dc.customer_key
    from stg_customers sc
    join dim_customer dc using (customer_unique_id)
),

fact as (
    select
        -- Natural keys (for debugging / traceability)
        e.order_id,
        e.order_item_id,

        -- Foreign keys
        ck.customer_key,
        dp.product_key,
        e.seller_id,                                           -- seller natural key
        dd_order.date_key                as order_date_key,
        dd_delivery.date_key             as delivery_date_key,

        -- Order attributes
        e.order_status,

        -- Measures
        e.price,
        e.freight_value,
        e.item_total,
        e.payment_value_alloc,
        e.primary_payment_type,
        e.payment_installments,

        -- Review
        e.review_score,
        e.has_written_review,

        -- Delivery
        e.delivery_days,
        e.is_late_delivery

    from enriched e
    left join customer_key_map ck on e.customer_id = ck.customer_id
    left join dim_product dp       on e.product_id  = dp.product_id
    left join dim_date dd_order
           on to_char(e.order_purchase_timestamp, 'YYYYMMDD')::int = dd_order.date_key
    left join dim_date dd_delivery
           on to_char(e.order_delivered_customer_date, 'YYYYMMDD')::int = dd_delivery.date_key
)

select * from fact
