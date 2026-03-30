{{
  config(
    materialized = 'view',
    description  = 'Staging payments — validate values, add order-level aggregates.'
  )
}}

with source as (
    select * from {{ source('olist_raw', 'payments') }}
    where payment_value is not null
      and payment_value > 0
),

order_agg as (
    select
        order_id,
        sum(payment_value)::numeric(12, 2)   as order_total_payment,
        count(payment_sequential)            as payment_count,
        max(payment_installments)            as max_installments,
        -- Primary payment type = the type with the highest value
        (array_agg(payment_type order by payment_value desc))[1] as primary_payment_type
    from source
    group by order_id
),

joined as (
    select
        s.order_id,
        s.payment_sequential,
        s.payment_type,
        s.payment_installments,
        s.payment_value::numeric(10, 2)  as payment_value,
        a.order_total_payment,
        a.payment_count,
        a.max_installments,
        a.primary_payment_type
    from source s
    join order_agg a using (order_id)
)

select * from joined
