{{
  config(
    materialized = 'ephemeral',
    description  = 'Customer lifetime value and order history aggregated to customer_unique_id.'
  )
}}

with customers as (
    select * from {{ ref('stg_customers') }}
),

orders as (
    select * from {{ ref('stg_orders') }}
    where order_status = 'delivered'
),

payments as (
    select
        order_id,
        order_total_payment
    from {{ ref('stg_payments') }}
    qualify row_number() over (partition by order_id order by order_total_payment desc) = 1
),

-- Map customer_id → customer_unique_id
id_mapped as (
    select
        o.order_id,
        c.customer_unique_id,
        o.order_purchase_timestamp,
        p.order_total_payment
    from orders o
    join customers c using (customer_id)
    left join payments p using (order_id)
),

aggregated as (
    select
        customer_unique_id,
        min(order_purchase_timestamp)              as customer_since,
        count(order_id)                            as total_orders,
        sum(order_total_payment)::numeric(12, 2)   as lifetime_value,
        avg(order_total_payment)::numeric(10, 2)   as avg_order_value
    from id_mapped
    group by customer_unique_id
),

segmented as (
    select
        *,
        case
            when lifetime_value >= {{ var('high_value_threshold') }}   then 'High'
            when lifetime_value >= {{ var('medium_value_threshold') }} then 'Medium'
            else 'Low'
        end as customer_segment
    from aggregated
)

select * from segmented
