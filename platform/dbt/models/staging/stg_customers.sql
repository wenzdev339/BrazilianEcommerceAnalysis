{{
  config(
    materialized = 'view',
    description  = 'Staging customers — normalise city/state casing, pad ZIP prefix.'
  )
}}

with source as (
    select * from {{ source('olist_raw', 'customers') }}
),

cleaned as (
    select
        customer_id,
        customer_unique_id,
        -- Pad ZIP to 5 chars (leading zeros may be stripped by CSV reader)
        lpad(customer_zip_code_prefix::text, 5, '0')     as customer_zip_code_prefix,
        initcap(lower(trim(customer_city)))               as customer_city,
        upper(trim(customer_state))                       as customer_state
    from source
)

select * from cleaned
