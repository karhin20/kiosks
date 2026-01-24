from datetime import datetime
from pydantic import BaseModel
from .order import OrderOut


class VendorStat(BaseModel):
    vendor_id: str
    vendor_name: str
    total_revenue: float
    total_sales: int


class TopProduct(BaseModel):
    name: str
    sales: int
    revenue: float


class DailyStat(BaseModel):
    date: str
    revenue: float
    orders: int


class AdminSummary(BaseModel):
    total_revenue: float
    total_orders: int
    total_customers: int
    total_products: int
    revenue_change: float = 0.0
    orders_change: float = 0.0
    customers_change: float = 0.0
    products_change: float = 0.0
    recent_orders: list[OrderOut]
    vendor_stats: list[VendorStat] = []
    top_products: list[TopProduct] = []
    daily_stats: list[DailyStat] = []


class AdminCustomer(BaseModel):
    user_id: str | None
    name: str
    phone: str | None = None
    email: str | None = None
    orders: int
    total_spent: float
    joined_at: datetime

