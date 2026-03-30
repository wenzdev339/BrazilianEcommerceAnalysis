{{
  config(
    materialized = 'view',
    description  = 'Staging orders — column renames, type casts, status normalisation.'
  )
}}

with source as (
    select * from {{ source('olist_raw', 'orders') }}
),

renamed as (
    select
        order_id,
        customer_id,
        lower(trim(order_status))                                as order_status,

        -- Parse timestamp strings; format in source: "M/D/YYYY H:MM"
        to_timestamp(order_purchase_timestamp,     'FMMM/FMDD/YYYY HH24:MI') as order_purchase_timestamp,
        to_timestamp(order_approved_at,            'FMMM/FMDD/YYYY HH24:MI') as order_approved_at,
        to_timestamp(order_delivered_carrier_date, 'FMMM/FMDD/YYYY HH24:MI') as order_delivered_carrier_date,
        to_timestamp(order_delivered_customer_date,'FMMM/FMDD/YYYY HH24:MI') as order_delivered_customer_date,
        to_timestamp(order_estimated_delivery_date,'FMMM/FMDD/YYYY HH24:MI') as order_estimated_delivery_date,

        -- Derived delivery metrics (pre-compute here for use in all downstream models)
        case
            when order_delivered_customer_date is not null
             and order_purchase_timestamp is not null
            then date_part(
                'day',
                to_timestamp(order_delivered_customer_date, 'FMMM/FMDD/YYYY HH24:MI')
                - to_timestamp(order_purchase_timestamp,    'FMMM/FMDD/YYYY HH24:MI')
            )::int
        end                                                      as delivery_days,

        case
            when order_delivered_customer_date is not null
             and order_estimated_delivery_date is not null
            then to_timestamp(order_delivered_customer_date, 'FMMM/FMDD/YYYY HH24:MI')
               > to_timestamp(order_estimated_delivery_date, 'FMMM/FMDD/YYYY HH24:MI')
        end                                                      as is_late_delivery

    from source
)

select * from renamed
