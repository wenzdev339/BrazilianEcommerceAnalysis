-- Singular test: every order_item in fact_orders must resolve to a customer_key.
-- Returns rows on failure (dbt fails the test if any rows returned).

select
    order_id,
    order_item_id
from {{ ref('fact_orders') }}
where customer_key is null
