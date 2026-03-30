{{
  config(
    materialized = 'view',
    description  = 'Staging reviews — parse timestamps, null-ify empty strings, derive flags.'
  )
}}

with source as (
    select * from {{ source('olist_raw', 'reviews') }}
    where review_score between 1 and 5
      or  review_score is null
),

cleaned as (
    select
        review_id,
        order_id,
        review_score,

        -- Null-ify empty comment strings
        nullif(trim(review_comment_title),   '') as review_comment_title,
        nullif(trim(review_comment_message), '') as review_comment_message,

        to_timestamp(review_creation_date,  'FMMM/FMDD/YYYY HH24:MI') as review_creation_date,
        to_timestamp(review_answer_timestamp,'FMMM/FMDD/YYYY HH24:MI') as review_answer_timestamp,

        -- Derived flags
        (nullif(trim(review_comment_message), '') is not null) as has_written_review,

        -- Response time in hours
        case
            when review_answer_timestamp is not null
             and review_creation_date    is not null
            then extract(epoch from (
                to_timestamp(review_answer_timestamp, 'FMMM/FMDD/YYYY HH24:MI')
                - to_timestamp(review_creation_date,  'FMMM/FMDD/YYYY HH24:MI')
            )) / 3600.0
        end as response_time_hours

    from source
)

select * from cleaned
