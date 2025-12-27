from collections import defaultdict
from datetime import datetime
from fastapi import APIRouter, Depends
from supabase import Client

from ..dependencies import require_admin
from ..schemas.admin import AdminSummary, AdminCustomer
from ..supabase_client import get_supabase_client

router = APIRouter(prefix="/admin", tags=["admin"], dependencies=[Depends(require_admin)])


@router.get("/summary", response_model=AdminSummary)
def get_admin_summary(supabase: Client = Depends(get_supabase_client)):
    orders_response = supabase.table("orders").select("*").order("created_at", desc=True).execute()
    orders = orders_response.data or []

    total_revenue = sum(order.get("total", 0) for order in orders)
    total_orders = len(orders)
    total_customers = len({order.get("user_id") for order in orders if order.get("user_id")})

    products_resp = supabase.table("products").select("id").execute()
    total_products = len(products_resp.data or [])

    recent_orders = orders[:5]

    return AdminSummary(
        total_revenue=total_revenue,
        total_orders=total_orders,
        total_customers=total_customers,
        total_products=total_products,
        recent_orders=recent_orders,
    )


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

