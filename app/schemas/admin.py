from datetime import datetime
from pydantic import BaseModel
from .order import OrderOut


class VendorStat(BaseModel):
    vendor_id: str
    vendor_name: str
    total_revenue: float
    total_sales: int


class AdminSummary(BaseModel):
    total_revenue: float
    total_orders: int
    total_customers: int
    total_products: int
    recent_orders: list[OrderOut]
    vendor_stats: list[VendorStat] = []


class AdminCustomer(BaseModel):
    user_id: str | None
    name: str
    phone: str | None = None
    email: str | None = None
    orders: int
    total_spent: float
    joined_at: datetime

