from decimal import Decimal
from typing import List, Optional

from pydantic import BaseModel


class TopCategory(BaseModel):
    product_category_name_english: str
    total_items_sold: int
    total_revenue: Decimal
    avg_price: Decimal
    avg_review_score: Optional[float]
    late_delivery_rate: Optional[float]


class TopCategoriesResponse(BaseModel):
    data: List[TopCategory]
    total_categories: int
