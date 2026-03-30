{{
  config(
    materialized = 'table',
    description  = 'Date dimension — complete spine from start_date to end_date.'
  )
}}

with date_spine as (
    {{ dbt_utils.date_spine(
        datepart   = "day",
        start_date = "cast('" ~ var('start_date') ~ "' as date)",
        end_date   = "cast('" ~ var('end_date')   ~ "' as date) + interval '1 day'"
    ) }}
),

dim as (
    select
        to_char(date_day, 'YYYYMMDD')::int      as date_key,
        date_day                                 as full_date,
        extract(year    from date_day)::int      as year,
        extract(quarter from date_day)::int      as quarter,
        extract(month   from date_day)::int      as month,
        to_char(date_day, 'Month')               as month_name,
        extract(week    from date_day)::int      as week_of_year,
        extract(isodow  from date_day)::int      as day_of_week,   -- 1=Mon, 7=Sun
        to_char(date_day, 'Day')                 as day_name,
        extract(day     from date_day)::int      as day_of_month,
        extract(isodow  from date_day) in (6, 7) as is_weekend,
        case when extract(month from date_day) <= 6 then 1 else 2 end as semester
    from date_spine
)

select * from dim
