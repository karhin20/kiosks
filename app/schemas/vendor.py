from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field


class VendorBase(BaseModel):
    name: str = Field(..., max_length=200)
    slug: Optional[str] = Field(None, max_length=200)
    description: Optional[str] = None
    logo_url: Optional[str] = None
    banner_url: Optional[str] = None
    contact_email: Optional[str] = None
    contact_phone: Optional[str] = None
    address: Optional[dict] = None
    is_active: bool = True


class VendorCreate(VendorBase):
    pass


class VendorUpdate(BaseModel):
    name: Optional[str] = Field(None, max_length=200)
    slug: Optional[str] = Field(None, max_length=200)
    description: Optional[str] = None
    logo_url: Optional[str] = None
    banner_url: Optional[str] = None
    contact_email: Optional[str] = None
    contact_phone: Optional[str] = None
    address: Optional[dict] = None
    is_active: Optional[bool] = None


class VendorOut(VendorBase):
    id: str
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class VendorAdmin(BaseModel):
    vendor_id: str
    user_id: str
    created_at: datetime

    class Config:
        from_attributes = True
