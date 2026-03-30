{{
  config(
    materialized = 'view',
    description  = 'Staging sellers — normalise casing and ZIP prefix.'
  )
}}

with source as (
    select * from {{ source('olist_raw', 'sellers') }}
),

cleaned as (
    select
        seller_id,
        lpad(seller_zip_code_prefix::text, 5, '0') as seller_zip_code_prefix,
        initcap(lower(trim(seller_city)))           as seller_city,
        upper(trim(seller_state))                   as seller_state
    from source
)

select * from cleaned
