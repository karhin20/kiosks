from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException
from supabase import Client

from ..schemas.order import OrderCreate, OrderOut, OrderStatusUpdate
from ..dependencies import get_current_user, require_admin
from ..supabase_client import get_supabase_client

router = APIRouter(prefix="/orders", tags=["orders"])


@router.get("/", response_model=list[OrderOut])
def list_orders(user=Depends(get_current_user), supabase: Client = Depends(get_supabase_client)):
    response = (
        supabase.table("orders")
        .select("*")
        .eq("user_id", user["id"])
        .order("created_at", desc=True)
        .execute()
    )
    return response.data or []


@router.post("/", response_model=OrderOut)
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
        "created_at": datetime.utcnow().isoformat(),
    }
    response = supabase.table("orders").insert(order_payload).select("*").single().execute()
    return response.data


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

