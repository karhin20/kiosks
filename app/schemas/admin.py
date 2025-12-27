from datetime import datetime
from pydantic import BaseModel
from .order import OrderOut


class AdminSummary(BaseModel):
    total_revenue: float
    total_orders: int
    total_customers: int
    total_products: int
    recent_orders: list[OrderOut]


class AdminCustomer(BaseModel):
    user_id: str | None
    name: str
    phone: str | None = None
    email: str | None = None
    orders: int
    total_spent: float
    joined_at: datetime

