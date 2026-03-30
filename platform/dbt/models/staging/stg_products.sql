{{
  config(
    materialized = 'view',
    description  = 'Staging products — fix typo column names, join English category, compute volume.'
  )
}}

with source as (
    select * from {{ source('olist_raw', 'products') }}
),

translation as (
    select * from {{ source('olist_raw', 'product_category_name_translation') }}
),

joined as (
    select
        s.product_id,
        coalesce(s.product_category_name, 'uncategorized')         as product_category_name,
        coalesce(t.product_category_name_english, 'uncategorized') as product_category_name_english,

        -- Fix typo column names from source
        s.product_name_lenght        as product_name_length,
        s.product_description_lenght as product_description_length,

        s.product_photos_qty,
        s.product_weight_g,
        s.product_length_cm,
        s.product_height_cm,
        s.product_width_cm,
        (s.product_length_cm * s.product_height_cm * s.product_width_cm) as product_volume_cm3
    from source s
    left join translation t using (product_category_name)
)

select * from joined
