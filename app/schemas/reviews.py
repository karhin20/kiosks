from pydantic import BaseModel
from typing import Optional, Dict, Any
from datetime import datetime
from uuid import UUID

class ReviewBase(BaseModel):
    rating: int
    comment: Optional[str] = None

class ReviewCreate(ReviewBase):
    product_id: str

class ReviewResponse(ReviewBase):
    id: UUID
    user_id: UUID
    product_id: str
    created_at: datetime
    # We will enrich this with user metadata in the router or via a join view if feasible, 
    # but for now let's return the raw data and let backend/frontend handle user profile fetching 
    # OR simpler: return a computed 'user_name' if we fetch it.
    user_metadata: Optional[Dict[str, Any]] = None

    class Config:
        from_attributes = True
