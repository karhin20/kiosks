from pydantic import BaseModel, EmailStr
from datetime import datetime

class SubscriptionCreate(BaseModel):
    email: EmailStr

class SubscriptionOut(BaseModel):
    id: str
    email: str
    created_at: datetime

    class Config:
        from_attributes = True
