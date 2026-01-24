from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks, Query
import httpx
from supabase import Client

from ..schemas.order import OrderCreate, OrderOut, OrderStatusUpdate
from ..dependencies import get_current_user, require_admin, require_vendor_admin, get_vendor_for_user
from ..supabase_client import get_supabase_client
from ..config import get_settings

router = APIRouter(prefix="/orders", tags=["orders"])


async def notify_purchase(order_data: dict, supabase: Client):
    """Send notification to the messenger service."""
    settings = get_settings()
    if not settings.MESSENGER_URL:
        return

    try:
        order_id = order_data["id"]
        total = order_data["total"]
        user_phone = order_data["shipping"].get("phone")
        
        # Construct items preview
        items = order_data.get("items", [])
        items_preview = ", ".join([f"{item['quantity']}x {item['name']}" for item in items[:2]])
        if len(items) > 2:
            items_preview += "..."

        # Get vendor phone (simplified: take first vendor found in items)
        vendor_phone = None
        if items:
            product_id = items[0].get("product_id")
            # Get product to find vendor_id
            prod_res = supabase.table("products").select("vendor_id").eq("id", product_id).single().execute()
            if prod_res.data and prod_res.data.get("vendor_id"):
                vendor_id = prod_res.data["vendor_id"]
                # Get vendor to find contact_phone
                vend_res = supabase.table("vendors").select("contact_phone").eq("id", vendor_id).single().execute()
                if vend_res.data:
                    vendor_phone = vend_res.data.get("contact_phone")

        payload = {
            "type": "purchase",
            "order_id": order_id,
            "user_phone": user_phone,
            "items_preview": items_preview,
            "total": total,
            "vendor_phone": vendor_phone
        }

        async with httpx.AsyncClient() as client:
            await client.post(
                settings.MESSENGER_URL,
                json=payload,
                headers={"x-messenger-secret": settings.MESSENGER_SECRET},
                timeout=10.0
            )
    except Exception as e:
        print(f"FAILED to send notification: {e}")


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
    background_tasks: BackgroundTasks,
    user=Depends(get_current_user),
    supabase: Client = Depends(get_supabase_client),
):
    if not payload.items:
        raise HTTPException(status_code=400, detail="Order must contain at least one item")

    # Best Practice: Recalculate total on server-side using current DB prices
    # This prevents users from manipulating the price in the frontend
    order_items = []
    final_total = 0.0

    # Fetch product IDs from payload
    product_ids = [item.product_id for item in payload.items]
    
    # Query database for current prices
    products_res = supabase.table("products").select("id, price, name, image_url").in_("id", product_ids).execute()
    db_products = {p["id"]: p for p in products_res.data}

    for item in payload.items:
        if item.product_id not in db_products:
            raise HTTPException(
                status_code=400, 
                detail=f"Product not found: {item.product_id}"
            )
        
        current_db_product = db_products[item.product_id]
        db_price = current_db_product["price"]
        item_total = db_price * item.quantity
        final_total += item_total

        # Use verified price from DB
        item_dict = item.model_dump()
        item_dict["price"] = db_price  # Overwrite with verified price
        order_items.append(item_dict)

    order_payload = {
        "user_id": user["id"],
        "status": "pending",
        "total": final_total,
        "items": order_items,
        "shipping": payload.shipping.model_dump(),
    }
    
    try:
        # select("*") ensures we get all fields back including auto-generated ID and created_at
        response = supabase.table("orders").insert(order_payload).execute()
        
        if not response.data or len(response.data) == 0:
            raise HTTPException(status_code=500, detail="Failed to create order record")
            
        order_data = response.data[0]
        # Trigger notification
        background_tasks.add_task(notify_purchase, order_data, supabase)
        
        return order_data
    except Exception as exc:
        print(f"CRITICAL ERROR creating order: {type(exc).__name__}: {exc}")
        error_msg = str(exc)
        if "id" in error_msg.lower() and "already exists" in error_msg.lower():
            raise HTTPException(status_code=400, detail="Order already exists")
            
        raise HTTPException(
            status_code=500, 
            detail=f"Internal Server Error: {error_msg}"
        ) from exc


@router.get("/admin/all", response_model=list[OrderOut])
def list_all_orders(
    limit: int = Query(50, ge=1, le=200, description="Max orders to return"),
    offset: int = Query(0, ge=0, description="Orders to skip"),
    supabase: Client = Depends(get_supabase_client),
    user=Depends(require_vendor_admin),
    vendor_id: str | None = Depends(get_vendor_for_user),
):
    """
    List all orders. 
    Super admins see everything. 
    Vendor admins see orders containing their products, with other vendors' items stripped.
    """
    if user.get("role") in ["admin", "super_admin"]:
        response = supabase.table("orders").select("*").order("created_at", desc=True).range(offset, offset + limit - 1).execute()
        return response.data or []
    
    # Vendor Admin Logic
    # 1. First, we need to find orders that contain products belonging to this vendor.
    # Since items are in JSONB, we'll fetch a wider range and filter in Python for now, 
    # as Supabase JSONB filtering for 'any item in list has vendor_id=X' is tricky with current schema.
    # Better: Query products for this vendor first.
    vend_prods_res = supabase.table("products").select("id").eq("vendor_id", vendor_id).execute()
    vend_prod_ids = {p["id"] for p in vend_prods_res.data}
    
    # Fetch recent orders
    response = supabase.table("orders").select("*").order("created_at", desc=True).range(offset, offset + limit - 1).execute()
    all_orders = response.data or []
    
    filtered_orders = []
    for order in all_orders:
        vendor_items = [item for item in order["items"] if item.get("product_id") in vend_prod_ids]
        if vendor_items:
            # Strip competitor items and adjust total for vendor view
            # Note: We create a copy to avoid modifying original if cached
            vendor_order = dict(order)
            vendor_order["items"] = vendor_items
            vendor_order["total"] = sum(item["price"] * item["quantity"] for item in vendor_items)
            filtered_orders.append(vendor_order)
            
    return filtered_orders


from ..utils.logging import log_action

@router.patch("/admin/{order_id}/status", response_model=OrderOut)
def update_order_status(
    order_id: str,
    payload: OrderStatusUpdate,
    supabase: Client = Depends(get_supabase_client),
    user=Depends(require_vendor_admin),
    vendor_id: str | None = Depends(get_vendor_for_user),
):
    """Update a product status. Vendor admins can only update if it's their vendor's product exclusively (simplified)."""
    # Verify access
    order_res = supabase.table("orders").select("*").eq("id", order_id).single().execute()
    if not order_res.data:
        raise HTTPException(status_code=404, detail="Order not found")
    
    if user.get("role") == "vendor_admin":
        # Check if they own ANY item in the order
        vend_prods_res = supabase.table("products").select("id").eq("vendor_id", vendor_id).execute()
        vend_prod_ids = {p["id"] for p in vend_prods_res.data}
        has_ownership = any(item.get("product_id") in vend_prod_ids for item in order_res.data["items"])
        
        if not has_ownership:
            raise HTTPException(status_code=403, detail="You do not have access to this order")

    response = (
        supabase.table("orders")
        .update({"status": payload.status})
        .eq("id", order_id)
        .select("*")
        .single()
        .execute()
    )
    
    log_action(supabase, user, "update_order_status", "order", order_id, {"new_status": payload.status})
    
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

