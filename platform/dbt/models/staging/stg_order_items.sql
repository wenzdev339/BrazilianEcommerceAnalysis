{{
  config(
    materialized = 'view',
    description  = 'Staging order_items — cast decimals, derive item_total.'
  )
}}

with source as (
    select * from {{ source('olist_raw', 'order_items') }}
),

cleaned as (
    select
        order_id,
        order_item_id,
        product_id,
        seller_id,
        to_timestamp(shipping_limit_date, 'FMMM/FMDD/YYYY HH24:MI') as shipping_limit_date,
        price::numeric(10, 2)                                          as price,
        freight_value::numeric(10, 2)                                  as freight_value,
        (price + freight_value)::numeric(10, 2)                        as item_total
    from source
    -- Remove orphaned items (no product or seller)
    where product_id is not null
      and seller_id  is not null
)

select * from cleaned
