"""
Automated Weekly Performance Report

Connects to PostgreSQL Gold tables, runs key queries, renders a Jinja2 HTML
report with embedded Matplotlib charts, and saves to reports/.

Usage:
    python reporting/generate_report.py
    python reporting/generate_report.py --output ./reports/custom_name.html
"""

from __future__ import annotations

import argparse
import base64
import io
import os
import sys
from datetime import date, datetime
from pathlib import Path

import matplotlib
matplotlib.use("Agg")   # Non-interactive backend for server use
import matplotlib.pyplot as plt
import matplotlib.ticker as mticker
import pandas as pd
import psycopg2
from dotenv import load_dotenv
from jinja2 import Environment, FileSystemLoader

load_dotenv()

DWH = "olist_dwh"
REPORTS_DIR = Path(__file__).parent.parent / "reports" / "output"
TEMPLATE_DIR = Path(__file__).parent / "templates"


def get_connection():
    return psycopg2.connect(
        host=os.getenv("POSTGRES_HOST", "localhost"),
        port=int(os.getenv("POSTGRES_PORT", "5432")),
        dbname=os.getenv("POSTGRES_DB", "ecommerce"),
        user=os.getenv("POSTGRES_USER", "postgres"),
        password=os.getenv("POSTGRES_PASSWORD", "changeme"),
    )


def query_df(conn, sql: str) -> pd.DataFrame:
    return pd.read_sql(sql, conn)


# ── Data queries ──────────────────────────────────────────────────────────────

def get_kpis(conn) -> dict:
    sql = f"""
        with delivered as (
            select
                order_id,
                sum(item_total)          as order_total,
                max(delivery_days)       as delivery_days,
                bool_or(is_late_delivery) as is_late,
                max(review_score)        as review_score
            from {DWH}.fact_orders
            where order_status = 'delivered'
            group by order_id
        )
        select
            count(distinct order_id)                              as total_orders,
            sum(order_total)                                      as total_revenue,
            avg(order_total)                                      as avg_order_value,
            percentile_cont(0.5) within group (order by order_total) as median_order_value,
            avg(case when is_late then 1.0 else 0.0 end) * 100   as late_delivery_pct,
            avg(delivery_days)                                    as avg_delivery_days,
            avg(review_score)                                     as avg_review_score
        from delivered
    """
    df = query_df(conn, sql)
    return df.iloc[0].to_dict()


def get_monthly_revenue(conn) -> pd.DataFrame:
    sql = f"""
        select year_month, total_revenue, total_orders, avg_review_score
        from {DWH}.agg_monthly_revenue
        order by year_month
    """
    return query_df(conn, sql)


def get_top_categories(conn, limit: int = 10) -> pd.DataFrame:
    sql = f"""
        select
            dp.product_category_name_english         as category,
            count(*)                                 as items_sold,
            sum(f.item_total)                        as revenue
        from {DWH}.fact_orders f
        join {DWH}.dim_product dp using (product_key)
        where f.order_status = 'delivered'
        group by dp.product_category_name_english
        order by revenue desc
        limit {limit}
    """
    return query_df(conn, sql)


def get_customer_segments(conn) -> pd.DataFrame:
    sql = f"""
        select customer_segment, count(*) as customer_count
        from {DWH}.dim_customer
        group by customer_segment
        order by customer_count desc
    """
    return query_df(conn, sql)


# ── Chart helpers ─────────────────────────────────────────────────────────────

def fig_to_base64(fig) -> str:
    buf = io.BytesIO()
    fig.savefig(buf, format="png", bbox_inches="tight", dpi=120)
    buf.seek(0)
    encoded = base64.b64encode(buf.read()).decode("utf-8")
    plt.close(fig)
    return encoded


def chart_revenue_trend(df: pd.DataFrame) -> str:
    fig, ax = plt.subplots(figsize=(10, 4))
    ax.plot(df["year_month"], df["total_revenue"] / 1_000_000, marker="o", linewidth=2, color="#2196F3")
    ax.set_title("Monthly Revenue Trend", fontsize=14, fontweight="bold")
    ax.set_xlabel("Month")
    ax.set_ylabel("Revenue (R$ millions)")
    ax.yaxis.set_major_formatter(mticker.FormatStrFormatter("R$%.1fM"))
    plt.xticks(rotation=45, ha="right", fontsize=8)
    ax.grid(axis="y", alpha=0.3)
    fig.tight_layout()
    return fig_to_base64(fig)


def chart_top_categories(df: pd.DataFrame) -> str:
    fig, ax = plt.subplots(figsize=(10, 5))
    colors = plt.cm.Blues_r([i / len(df) for i in range(len(df))])
    ax.barh(df["category"][::-1], df["revenue"][::-1] / 1_000, color=colors)
    ax.set_title("Top 10 Product Categories by Revenue", fontsize=14, fontweight="bold")
    ax.set_xlabel("Revenue (R$ thousands)")
    ax.grid(axis="x", alpha=0.3)
    fig.tight_layout()
    return fig_to_base64(fig)


def chart_customer_segments(df: pd.DataFrame) -> str:
    fig, ax = plt.subplots(figsize=(6, 6))
    colors = ["#4CAF50", "#FF9800", "#F44336"]
    ax.pie(
        df["customer_count"],
        labels=df["customer_segment"],
        autopct="%1.1f%%",
        colors=colors,
        startangle=90,
    )
    ax.set_title("Customer Segments by Count", fontsize=14, fontweight="bold")
    fig.tight_layout()
    return fig_to_base64(fig)


# ── Report rendering ──────────────────────────────────────────────────────────

INLINE_TEMPLATE = """
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<title>E-Commerce Weekly Report — {{ report_date }}</title>
<style>
  body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
         margin: 0; padding: 20px; background: #f5f5f5; color: #333; }
  .header { background: #1565C0; color: white; padding: 24px 32px;
             border-radius: 8px; margin-bottom: 24px; }
  .header h1 { margin: 0; font-size: 24px; }
  .header p  { margin: 4px 0 0; opacity: 0.8; font-size: 14px; }
  .kpi-grid { display: grid; grid-template-columns: repeat(4, 1fr);
               gap: 16px; margin-bottom: 24px; }
  .kpi-card { background: white; border-radius: 8px; padding: 20px;
               box-shadow: 0 1px 4px rgba(0,0,0,.1); }
  .kpi-card .label { font-size: 12px; color: #666; text-transform: uppercase;
                      letter-spacing: .5px; margin-bottom: 8px; }
  .kpi-card .value { font-size: 28px; font-weight: 700; color: #1565C0; }
  .kpi-card .unit  { font-size: 13px; color: #888; margin-top: 4px; }
  .chart-section { background: white; border-radius: 8px; padding: 24px;
                    box-shadow: 0 1px 4px rgba(0,0,0,.1); margin-bottom: 24px; }
  .chart-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 24px; }
  img { width: 100%; }
  .footer { text-align: center; color: #999; font-size: 12px; padding: 16px; }
</style>
</head>
<body>
<div class="header">
  <h1>E-Commerce Platform — Weekly Performance Report</h1>
  <p>Generated {{ report_date }} · Data source: Olist Brazilian E-Commerce Dataset (2016-2018)</p>
</div>

<div class="kpi-grid">
  <div class="kpi-card">
    <div class="label">Total Orders (Delivered)</div>
    <div class="value">{{ "{:,.0f}".format(kpis.total_orders) }}</div>
  </div>
  <div class="kpi-card">
    <div class="label">Total Revenue</div>
    <div class="value">R$ {{ "{:,.0f}".format(kpis.total_revenue / 1000) }}K</div>
  </div>
  <div class="kpi-card">
    <div class="label">Avg Order Value</div>
    <div class="value">R$ {{ "{:.0f}".format(kpis.avg_order_value) }}</div>
  </div>
  <div class="kpi-card">
    <div class="label">Avg Review Score</div>
    <div class="value">{{ "{:.2f}".format(kpis.avg_review_score) }} / 5</div>
  </div>
  <div class="kpi-card">
    <div class="label">Late Delivery Rate</div>
    <div class="value">{{ "{:.1f}".format(kpis.late_delivery_pct) }}%</div>
  </div>
  <div class="kpi-card">
    <div class="label">Avg Delivery Days</div>
    <div class="value">{{ "{:.1f}".format(kpis.avg_delivery_days) }}</div>
  </div>
  <div class="kpi-card">
    <div class="label">Median Order Value</div>
    <div class="value">R$ {{ "{:.0f}".format(kpis.median_order_value) }}</div>
  </div>
</div>

<div class="chart-section">
  <img src="data:image/png;base64,{{ chart_revenue }}" alt="Revenue Trend">
</div>

<div class="chart-grid">
  <div class="chart-section">
    <img src="data:image/png;base64,{{ chart_categories }}" alt="Top Categories">
  </div>
  <div class="chart-section">
    <img src="data:image/png;base64,{{ chart_segments }}" alt="Customer Segments">
  </div>
</div>

<div class="footer">
  Generated by E-Commerce Data Platform · Airflow scheduled report
</div>
</body>
</html>
"""


def generate_report(output_path: Path | None = None) -> Path:
    conn = get_connection()

    print("Fetching KPIs...")
    kpis = get_kpis(conn)

    print("Fetching monthly revenue...")
    monthly_df = get_monthly_revenue(conn)

    print("Fetching top categories...")
    categories_df = get_top_categories(conn)

    print("Fetching customer segments...")
    segments_df = get_customer_segments(conn)

    conn.close()

    print("Rendering charts...")
    chart_revenue    = chart_revenue_trend(monthly_df)
    chart_categories = chart_top_categories(categories_df)
    chart_segments   = chart_customer_segments(segments_df)

    from jinja2 import Template
    template = Template(INLINE_TEMPLATE)
    html = template.render(
        report_date=date.today().isoformat(),
        kpis=type("KPIs", (), kpis),
        chart_revenue=chart_revenue,
        chart_categories=chart_categories,
        chart_segments=chart_segments,
    )

    if output_path is None:
        REPORTS_DIR.mkdir(parents=True, exist_ok=True)
        output_path = REPORTS_DIR / f"report_{date.today().isoformat()}.html"

    output_path.write_text(html, encoding="utf-8")
    print(f"Report saved → {output_path}")
    return output_path


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=None)
    args = parser.parse_args()
    generate_report(output_path=args.output)
