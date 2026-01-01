from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException
from supabase import Client

from ..schemas.order import OrderCreate, OrderOut, OrderStatusUpdate
from ..dependencies import get_current_user, require_admin
from ..supabase_client import get_supabase_client

router = APIRouter(prefix="/orders", tags=["orders"])


@router.get("", response_model=list[OrderOut])
def list_orders(user=Depends(get_current_user), supabase: Client = Depends(get_supabase_client)):
    response = (
        supabase.table("orders")
        .select("*")
        .eq("user_id", user["id"])
        .order("created_at", desc=True)
        .execute()
    )
    return response.data or []


@router.post("", response_model=OrderOut)
def create_order(
    payload: OrderCreate,
    user=Depends(get_current_user),
    supabase: Client = Depends(get_supabase_client),
):
    if not payload.items:
        raise HTTPException(status_code=400, detail="Order must contain at least one item")

    order_payload = {
        "user_id": user["id"],
        "status": "pending",
        "total": payload.total,
        "items": [item.model_dump() for item in payload.items],
        "shipping": payload.shipping.model_dump(),
        # Removing created_at to let the database handle it with its default
    }
    
    try:
        # Use upsert or insert? Insert is better for new orders.
        # select("*") ensures we get all fields back including auto-generated ID and created_at
        response = supabase.table("orders").insert(order_payload).execute()
        
        if not response.data or len(response.data) == 0:
            print(f"DEBUG: Insert failed? Response: {response}")
            raise HTTPException(status_code=500, detail="Failed to create order record")
            
        return response.data[0]
    except Exception as exc:
        print(f"CRITICAL ERROR creating order: {type(exc).__name__}: {exc}")
        # Try to provide more detail in the exception if possible
        error_msg = str(exc)
        if "id" in error_msg.lower() and "already exists" in error_msg.lower():
            raise HTTPException(status_code=400, detail="Order already exists")
            
        raise HTTPException(
            status_code=500, 
            detail=f"Internal Server Error: {error_msg}"
        ) from exc


@router.get("/admin/all", response_model=list[OrderOut], dependencies=[Depends(require_admin)])
def list_all_orders(supabase: Client = Depends(get_supabase_client)):
    response = supabase.table("orders").select("*").order("created_at", desc=True).execute()
    return response.data or []


@router.patch("/admin/{order_id}/status", response_model=OrderOut, dependencies=[Depends(require_admin)])
def update_order_status(
    order_id: str,
    payload: OrderStatusUpdate,
    supabase: Client = Depends(get_supabase_client),
):
    response = (
        supabase.table("orders")
        .update({"status": payload.status})
        .eq("id", order_id)
        .select("*")
        .single()
        .execute()
    )
    if not response.data:
        raise HTTPException(status_code=404, detail="Order not found")
    return response.data


@router.get("/{order_id}", response_model=OrderOut)
def get_order(
    order_id: str,
    user=Depends(get_current_user),
    supabase: Client = Depends(get_supabase_client),
):
    response = supabase.table("orders").select("*").eq("id", order_id).single().execute()
    if not response.data:
        raise HTTPException(status_code=404, detail="Order not found")
    order = response.data
    if order["user_id"] != user["id"] and user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Not allowed")
    return order

