from decimal import Decimal
from typing import List, Optional

from pydantic import BaseModel


class MonthlyRevenue(BaseModel):
    year: int
    month: int
    month_name: str
    year_month: str
    total_orders: int
    total_items: int
    unique_customers: int
    product_revenue: Decimal
    freight_revenue: Decimal
    total_revenue: Decimal
    avg_delivery_days: Optional[float]
    late_delivery_rate: Optional[float]
    avg_review_score: Optional[float]
    mom_revenue_growth_pct: Optional[float]

    class Config:
        from_attributes = True


class OrderSummary(BaseModel):
    total_orders: int
    total_revenue: Decimal
    avg_order_value: Decimal
    median_order_value: Optional[Decimal]
    late_delivery_rate: float
    avg_delivery_days: float
    avg_review_score: float


class MonthlyRevenueResponse(BaseModel):
    data: List[MonthlyRevenue]
    total_months: int
