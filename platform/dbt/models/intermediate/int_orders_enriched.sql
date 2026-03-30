{{
  config(
    materialized = 'ephemeral',
    description  = 'Orders joined with items, payments and reviews. One row per order_item.'
  )
}}

with orders as (
    select * from {{ ref('stg_orders') }}
),

items as (
    select * from {{ ref('stg_order_items') }}
),

-- Order-level payment summary (avoid fan-out with items join)
payments as (
    select
        order_id,
        order_total_payment,
        primary_payment_type,
        max_installments      as payment_installments,
        payment_count
    from {{ ref('stg_payments') }}
    qualify row_number() over (partition by order_id order by order_total_payment desc) = 1
),

-- One review per order (drop duplicates)
reviews as (
    select distinct on (order_id)
        order_id,
        review_score,
        has_written_review
    from {{ ref('stg_reviews') }}
    order by order_id, review_score desc
),

-- Proportional payment allocation denominator
item_totals as (
    select
        order_id,
        sum(price) as order_total_price
    from {{ ref('stg_order_items') }}
    group by order_id
),

joined as (
    select
        i.order_id,
        i.order_item_id,
        o.customer_id,
        i.product_id,
        i.seller_id,
        o.order_status,
        o.order_purchase_timestamp,
        o.order_delivered_customer_date,
        o.delivery_days,
        o.is_late_delivery,
        i.price,
        i.freight_value,
        i.item_total,
        -- Proportional payment allocation
        case
            when it.order_total_price > 0
            then round(
                (i.price / it.order_total_price) * p.order_total_payment,
                2
            )
        end::numeric(10, 2)            as payment_value_alloc,
        p.primary_payment_type,
        p.payment_installments,
        p.order_total_payment,
        r.review_score,
        r.has_written_review
    from items i
    join orders  o  using (order_id)
    left join item_totals it using (order_id)
    left join payments    p  using (order_id)
    left join reviews     r  using (order_id)
)

select * from joined
