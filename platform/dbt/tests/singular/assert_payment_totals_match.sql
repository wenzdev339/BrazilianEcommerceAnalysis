-- Singular test: total payment_value_alloc in fact_orders must be within 0.1%
-- of the raw payments total. Validates the proportional allocation logic.

with raw_total as (
    select sum(payment_value) as raw_sum
    from {{ source('olist_raw', 'payments') }}
    where payment_value > 0
),

fact_total as (
    select sum(payment_value_alloc) as fact_sum
    from {{ ref('fact_orders') }}
),

comparison as (
    select
        r.raw_sum,
        f.fact_sum,
        abs(r.raw_sum - f.fact_sum) / r.raw_sum as discrepancy_pct
    from raw_total r
    cross join fact_total f
)

-- Return rows only if discrepancy exceeds 0.1% (test failure condition)
select *
from comparison
where discrepancy_pct > 0.001
