from datetime import datetime
from typing import Optional, Any
from pydantic import BaseModel

class AuditLogOut(BaseModel):
    id: str
    created_at: datetime
    user_id: Optional[str] = None
    user_name: Optional[str] = None
    user_role: Optional[str] = None
    action: str
    resource_type: str
    resource_id: Optional[str] = None
    details: Optional[Any] = None
    ip_address: Optional[str] = None

    class Config:
        from_attributes = True
