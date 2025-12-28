from collections import defaultdict
from datetime import datetime
from fastapi import APIRouter, Depends
from supabase import Client

from ..dependencies import require_admin
from ..schemas.admin import AdminSummary, AdminCustomer
from ..supabase_client import get_supabase_client

router = APIRouter(prefix="/admin", tags=["admin"], dependencies=[Depends(require_admin)])


# Simple in-memory cache for admin summary
_summary_cache = {
    "data": None,
    "timestamp": None
}
CACHE_TTL_SECONDS = 60

@router.get("/summary", response_model=AdminSummary)
def get_admin_summary(supabase: Client = Depends(get_supabase_client)):
    # Check cache
    now = datetime.utcnow()
    if (
        _summary_cache["data"] is not None and 
        _summary_cache["timestamp"] is not None and 
        (now - _summary_cache["timestamp"]).total_seconds() < CACHE_TTL_SECONDS
    ):
        return _summary_cache["data"]

    # Fetch orders
    orders_response = supabase.table("orders").select("*").order("created_at", desc=True).execute()
    orders = orders_response.data or []

    # Fetch all products to map product_id -> vendor_id
    products_resp = supabase.table("products").select("id, name, vendor_id").execute()
    products_data = products_resp.data or []
    product_to_vendor = {p["id"]: p.get("vendor_id") for p in products_data}
    
    # Fetch all vendors to map vendor_id -> vendor_name
    vendors_resp = supabase.table("vendors").select("id, name").execute()
    vendors_data = vendors_resp.data or []
    vendor_names = {v["id"]: v["name"] for v in vendors_data}

    total_revenue = sum(order.get("total", 0) for order in orders)
    total_orders = len(orders)
    total_customers = len({order.get("user_id") for order in orders if order.get("user_id")})
    total_products = len(products_data)

    # Calculate vendor stats
    vendor_stats_map = defaultdict(lambda: {"revenue": 0.0, "sales": 0})
    
    for order in orders:
        items = order.get("items", [])
        for item in items:
            p_id = item.get("product_id")
            v_id = product_to_vendor.get(p_id)
            if v_id:
                qty = item.get("quantity", 0)
                price = item.get("price", 0)
                vendor_stats_map[v_id]["revenue"] += float(qty * price)
                vendor_stats_map[v_id]["sales"] += qty

    vendor_stats = []
    for v_id, stats in vendor_stats_map.items():
        vendor_stats.append({
            "vendor_id": v_id,
            "vendor_name": vendor_names.get(v_id, "Unknown Vendor"),
            "total_revenue": stats["revenue"],
            "total_sales": stats["sales"]
        })

    # Sort vendor stats by revenue descending
    vendor_stats.sort(key=lambda x: x["total_revenue"], reverse=True)

    recent_orders = orders[:5]

    result = AdminSummary(
        total_revenue=total_revenue,
        total_orders=total_orders,
        total_customers=total_customers,
        total_products=total_products,
        recent_orders=recent_orders,
        vendor_stats=vendor_stats
    )

    # Update cache
    _summary_cache["data"] = result
    _summary_cache["timestamp"] = datetime.utcnow()

    return result


@router.get("/customers", response_model=list[AdminCustomer])
def get_admin_customers(supabase: Client = Depends(get_supabase_client)):
    orders_response = supabase.table("orders").select("*").execute()
    orders = orders_response.data or []

    grouped: dict[str | None, dict] = defaultdict(
        lambda: {
            "user_id": None,
            "name": "",
            "phone": None,
            "email": None,
            "orders": 0,
            "total_spent": 0.0,
            "joined_at": None,
        }
    )

    for order in orders:
        user_id = order.get("user_id")
        shipping = order.get("shipping") or {}
        created_at_str = order.get("created_at")
        created_at = (
            datetime.fromisoformat(created_at_str.replace("Z", ""))
            if isinstance(created_at_str, str)
            else datetime.utcnow()
        )

        g = grouped[user_id]
        g["user_id"] = user_id
        # Prefer existing non-empty name/phone
        if not g["name"] and shipping.get("name"):
            g["name"] = shipping.get("name")
        if not g["phone"] and shipping.get("phone"):
            g["phone"] = shipping.get("phone")
        g["orders"] += 1
        g["total_spent"] += float(order.get("total") or 0)
        if g["joined_at"] is None or created_at < g["joined_at"]:
            g["joined_at"] = created_at

    customers: list[AdminCustomer] = []
    for g in grouped.values():
        if not g["name"]:
            g["name"] = "Unknown"
        customers.append(
            AdminCustomer(
                user_id=g["user_id"],
                name=g["name"],
                phone=g["phone"],
                email=g["email"],
                orders=g["orders"],
                total_spent=g["total_spent"],
                joined_at=g["joined_at"] or datetime.utcnow(),
            )
        )

    # Sort by joined_at ascending like "joinedAt"
    customers.sort(key=lambda c: c.joined_at)
    return customers

