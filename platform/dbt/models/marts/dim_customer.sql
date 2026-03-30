{{
  config(
    materialized = 'table',
    description  = 'Customer dimension — SCD Type 1, grain: one row per customer_unique_id.'
  )
}}

with customers as (
    select * from {{ ref('stg_customers') }}
),

lifetime as (
    select * from {{ ref('int_customer_lifetime') }}
),

region_map as (
    select * from {{ ref('brazil_state_region_map') }}
),

-- Canonical customer record: one row per unique person
canonical as (
    select distinct on (customer_unique_id)
        customer_unique_id,
        customer_city,
        customer_state
    from customers
    order by customer_unique_id
),

dim as (
    select
        {{ dbt_utils.generate_surrogate_key(['c.customer_unique_id']) }} as customer_key,
        c.customer_unique_id,
        c.customer_city,
        c.customer_state,
        coalesce(r.region, 'Unknown')      as region,
        l.customer_since,
        coalesce(l.total_orders,    0)     as total_orders,
        coalesce(l.lifetime_value,  0)     as lifetime_value,
        coalesce(l.avg_order_value, 0)     as avg_order_value,
        coalesce(l.customer_segment, 'Low') as customer_segment
    from canonical c
    left join lifetime   l using (customer_unique_id)
    left join region_map r on c.customer_state = r.state_code
)

select * from dim
