from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field


class OrderItem(BaseModel):
    product_id: str
    name: str
    quantity: int = Field(..., gt=0)
    price: float = Field(..., ge=0)
    image_url: Optional[str] = None


class ShippingAddress(BaseModel):
    name: str
    phone: str
    street: str
    city: str
    region: str


class OrderCreate(BaseModel):
    items: list[OrderItem]
    shipping: ShippingAddress
    total: float = Field(..., ge=0)


class OrderOut(BaseModel):
    id: str
    user_id: Optional[str] = None
    status: str
    total: float
    items: list[OrderItem]
    shipping: ShippingAddress
    created_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class OrderStatusUpdate(BaseModel):
    status: str

