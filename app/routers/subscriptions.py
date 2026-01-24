from fastapi import APIRouter, Depends, HTTPException, Body
from supabase import Client
from ..supabase_client import get_supabase_client
from ..schemas.subscription import SubscriptionCreate, SubscriptionOut

router = APIRouter(prefix="/subscriptions", tags=["subscriptions"])

@router.post("", response_model=SubscriptionOut)
def subscribe(
    payload: SubscriptionCreate,
    supabase: Client = Depends(get_supabase_client)
):
    """Subscribe a new email address."""
    try:
        # Check if already exists (optional, or rely on unique constraint exception)
        existing = supabase.table("subscriptions").select("id").eq("email", payload.email).maybe_single().execute()
        if existing.data:
            raise HTTPException(status_code=400, detail="This email is already subscribed.")

        response = supabase.table("subscriptions").insert({"email": payload.email}).execute()
        if not response.data:
             raise HTTPException(status_code=500, detail="Failed to create subscription")
             
        return response.data[0]
        
    except HTTPException:
        raise
    except Exception as exc:
        if "duplicate key" in str(exc) or "unique constraint" in str(exc):
             raise HTTPException(status_code=400, detail="This email is already subscribed.")
        raise HTTPException(status_code=500, detail=str(exc))
