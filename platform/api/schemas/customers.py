from decimal import Decimal
from typing import List, Optional

from pydantic import BaseModel


class CustomerSegmentCount(BaseModel):
    customer_segment: str
    customer_count: int
    total_lifetime_value: Decimal
    avg_lifetime_value: Decimal
    pct_of_customers: float


class TopState(BaseModel):
    customer_state: str
    region: str
    customer_count: int
    total_revenue: Decimal
    avg_order_value: Decimal


class CustomerSegmentsResponse(BaseModel):
    data: List[CustomerSegmentCount]
    total_customers: int


class TopStatesResponse(BaseModel):
    data: List[TopState]
