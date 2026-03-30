# Data Dictionary — Gold Layer (olist_dwh)

## dim_customer

| Column               | Type     | Source                           | Description                                      |
|----------------------|----------|----------------------------------|--------------------------------------------------|
| customer_key         | VARCHAR  | MD5 surrogate key                | Unique identifier for dimension joins            |
| customer_unique_id   | VARCHAR  | customers.customer_unique_id     | True unique customer (person) identifier         |
| customer_city        | VARCHAR  | customers.customer_city          | Title-cased city name                            |
| customer_state       | VARCHAR  | customers.customer_state         | 2-letter Brazilian state code (uppercase)        |
| region               | VARCHAR  | brazil_state_region_map seed     | Brazilian macro-region (Sudeste, Sul, Nordeste…) |
| customer_since       | TIMESTAMP| orders.order_purchase_timestamp  | Earliest delivered order date for this customer  |
| total_orders         | INTEGER  | Aggregated from fact_orders      | Count of delivered orders per unique customer    |
| lifetime_value       | DECIMAL  | Aggregated from payments         | Total payment value across all delivered orders  |
| avg_order_value      | DECIMAL  | Derived                          | lifetime_value / total_orders                    |
| customer_segment     | VARCHAR  | Derived from lifetime_value      | High (≥R$500) / Medium (≥R$200) / Low (<R$200)  |

**Note**: `customer_id` is a per-order ID in the source. `customer_unique_id` identifies the person.
Multiple `customer_id` values can map to the same `customer_unique_id`.

---

## dim_product

| Column                          | Type    | Source                                    | Description                      |
|---------------------------------|---------|-------------------------------------------|----------------------------------|
| product_key                     | VARCHAR | MD5 surrogate key                         | Unique identifier for joins      |
| product_id                      | VARCHAR | products.product_id                       | Source product UUID              |
| product_category_name           | VARCHAR | products.product_category_name            | Portuguese category name         |
| product_category_name_english   | VARCHAR | product_category_name_translation         | English category name            |
| product_name_length             | INTEGER | products.product_name_lenght (typo fixed) | Character count of product name  |
| product_description_length      | INTEGER | products.product_description_lenght       | Character count of description   |
| product_photos_qty              | INTEGER | products.product_photos_qty               | Number of product photos         |
| product_weight_g                | INTEGER | products.product_weight_g                 | Weight in grams                  |
| product_length_cm               | INTEGER | products.product_length_cm                | Length in centimeters            |
| product_height_cm               | INTEGER | products.product_height_cm                | Height in centimeters            |
| product_width_cm                | INTEGER | products.product_width_cm                 | Width in centimeters             |
| product_volume_cm3              | INTEGER | Derived: length × height × width          | Volume in cubic centimeters      |

**Note**: The source CSV has typo columns `product_name_lenght` and `product_description_lenght`.
These are corrected to `product_name_length` and `product_description_length` in Silver and Gold.

---

## dim_date

| Column        | Type    | Description                                          |
|---------------|---------|------------------------------------------------------|
| date_key      | INTEGER | YYYYMMDD integer — used as FK in fact tables         |
| full_date     | DATE    | Calendar date                                        |
| year          | INTEGER | Calendar year (2016-2019)                            |
| quarter       | INTEGER | 1-4                                                  |
| month         | INTEGER | 1-12                                                 |
| month_name    | VARCHAR | "January" … "December"                               |
| week_of_year  | INTEGER | ISO week number (1-53)                               |
| day_of_week   | INTEGER | ISO day of week (1=Monday, 7=Sunday)                 |
| day_name      | VARCHAR | "Monday" … "Sunday"                                  |
| day_of_month  | INTEGER | 1-31                                                 |
| is_weekend    | BOOLEAN | True for Saturday (6) and Sunday (7)                 |
| semester      | INTEGER | 1 (Jan-Jun) or 2 (Jul-Dec) — common in BR reporting |

**Note**: Generated entirely in code — no source data dependency.
Covers 2016-01-01 to 2019-12-31 (the full Olist dataset time range).

---

## fact_orders

**Grain**: one row per order_item (order_id + order_item_id).

| Column               | Type    | Source / Derivation                                     | Description                                     |
|----------------------|---------|---------------------------------------------------------|-------------------------------------------------|
| order_id             | VARCHAR | order_items.order_id                                    | Natural key — traces back to source             |
| order_item_id        | INTEGER | order_items.order_item_id                               | Item sequence within an order                   |
| customer_key         | VARCHAR | FK → dim_customer                                       | Resolved via customer_id → customer_unique_id   |
| product_key          | VARCHAR | FK → dim_product                                        |                                                 |
| seller_id            | VARCHAR | order_items.seller_id (natural key)                     | No separate seller dim in current version       |
| order_date_key       | INTEGER | FK → dim_date (from order_purchase_timestamp)           |                                                 |
| delivery_date_key    | INTEGER | FK → dim_date (from order_delivered_customer_date)      | Null for undelivered orders                     |
| order_status         | VARCHAR | orders.order_status                                     | Lowercase: delivered, shipped, canceled…        |
| price                | DECIMAL | order_items.price                                       | Item price in BRL                               |
| freight_value        | DECIMAL | order_items.freight_value                               | Freight charge for this item                    |
| item_total           | DECIMAL | price + freight_value                                   | Total cost for this item                        |
| payment_value_alloc  | DECIMAL | Derived: proportional allocation of order payment       | See note below                                  |
| primary_payment_type | VARCHAR | payments.payment_type (highest-value method)            | credit_card / boleto / voucher / debit_card     |
| payment_installments | INTEGER | payments.payment_installments (max across sequences)    | Number of installments for primary payment      |
| review_score         | INTEGER | reviews.review_score                                    | 1-5 star rating; NULL if no review submitted    |
| has_written_review   | BOOLEAN | Derived from review_comment_message is not null         |                                                 |
| delivery_days        | INTEGER | Derived: purchase → delivered (calendar days)           | NULL for non-delivered orders                   |
| is_late_delivery     | BOOLEAN | delivered_date > estimated_date                         | NULL for non-delivered orders                   |

**Payment allocation note**:
Payments are recorded at order level (not item level). `payment_value_alloc` allocates the
order total proportionally: `payment_value_alloc = (item_price / order_total_price) × order_total_payment`.
This approach is within 0.1% of the total payment sum due to rounding (validated by dbt test
`assert_payment_totals_match`).

---

## agg_monthly_revenue

Pre-aggregated from `fact_orders` for BI dashboard performance.
Filters to `order_status = 'delivered'` only.

| Column                  | Type    | Description                                           |
|-------------------------|---------|-------------------------------------------------------|
| year                    | INTEGER | Calendar year                                         |
| month                   | INTEGER | Calendar month (1-12)                                 |
| month_name              | VARCHAR | Month name                                            |
| year_month              | VARCHAR | "YYYY-MM" format for time-series charts               |
| total_orders            | INTEGER | Distinct delivered orders                             |
| total_items             | INTEGER | Total order items (sum of order_item_id counts)       |
| unique_customers        | INTEGER | Distinct customers (by customer_key)                  |
| product_revenue         | DECIMAL | Sum of price (excluding freight)                      |
| freight_revenue         | DECIMAL | Sum of freight_value                                  |
| total_revenue           | DECIMAL | product_revenue + freight_revenue                     |
| avg_delivery_days       | FLOAT   | Average delivery time in calendar days                |
| late_delivery_rate      | FLOAT   | Proportion of items with is_late_delivery = true      |
| avg_review_score        | FLOAT   | Average review score (1-5)                            |
| mom_revenue_growth_pct  | FLOAT   | Month-over-month revenue growth percentage            |
