from fastapi import APIRouter, Depends, Query
from supabase import Client

from ..dependencies import require_super_admin
from ..schemas.audit import AuditLogOut
from ..supabase_client import get_supabase_client

router = APIRouter(prefix="/audit", tags=["audit"], dependencies=[Depends(require_super_admin)])

@router.get("/logs", response_model=list[AuditLogOut])
def get_audit_logs(
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    resource_type: str | None = Query(None),
    supabase: Client = Depends(get_supabase_client)
):
    """Fetch system audit logs. Super Admin only."""
    query = supabase.table("audit_logs").select("*").order("created_at", desc=True).range(offset, offset + limit - 1)
    
    if resource_type:
        query = query.eq("resource_type", resource_type)
        
    response = query.execute()
    return response.data or []
