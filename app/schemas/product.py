from datetime import datetime
from typing import Optional
from pydantic import BaseModel, HttpUrl, Field


class ProductBase(BaseModel):
    name: str = Field(..., max_length=200)
    description: str
    category: str
    price: float = Field(..., ge=0)
    original_price: Optional[float] = Field(None, ge=0)
    is_new: bool = False
    details: list[str] = []
    images: list[str] = []
    is_flash_sale: bool = False
    sales_count: int = Field(0, ge=0)
    is_featured: bool = False
    flash_sale_end_time: Optional[datetime] = None
    video_url: Optional[str] = None
    status: str = "pending"


class ProductCreate(ProductBase):
    pass


class ProductUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    category: Optional[str] = None
    price: Optional[float] = Field(None, ge=0)
    original_price: Optional[float] = Field(None, ge=0)
    is_new: Optional[bool] = None
    details: Optional[list[str]] = None
    images: Optional[list[str]] = None
    is_flash_sale: Optional[bool] = None
    sales_count: Optional[int] = Field(None, ge=0)
    is_featured: Optional[bool] = None
    flash_sale_end_time: Optional[datetime] = None
    video_url: Optional[str] = None
    status: Optional[str] = None


class ProductOut(ProductBase):
    id: str
    image_url: Optional[str] = None
    images: list[str] = []
    is_flash_sale: bool = False
    sales_count: int = 0
    is_featured: bool = False
    rating: float = 0.0
    reviews_count: int = 0
    flash_sale_end_time: Optional[datetime] = None
    video_url: Optional[str] = None
    vendor_name: Optional[str] = None
    vendor_slug: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True

