from collections import defaultdict
from datetime import datetime
from fastapi import APIRouter, Depends, Query, HTTPException
from supabase import Client

from ..dependencies import require_vendor_admin, get_vendor_for_user
from ..schemas.admin import AdminSummary, AdminCustomer, TopProduct, DailyStat
from ..supabase_client import get_supabase_client

router = APIRouter(prefix="/admin", tags=["admin"], dependencies=[Depends(require_vendor_admin)])


@router.get("/summary", response_model=AdminSummary)
def get_admin_summary(
    supabase: Client = Depends(get_supabase_client),
    user=Depends(require_vendor_admin),
    vendor_id: str | None = Depends(get_vendor_for_user)
):
    """
    Get summary stats. 
    Super admins see site-wide data.
    Vendors see only their own data.
    """
    is_super_admin = user.get("role") in ["admin", "super_admin"]

    # Fetch orders
    orders_response = supabase.table("orders").select("*").order("created_at", desc=True).execute()
    all_orders = orders_response.data or []

    # Fetch all products to map product_id -> (vendor_id, name)
    products_resp = supabase.table("products").select("id, name, vendor_id").execute()
    products_data = products_resp.data or []
    product_meta = {p["id"]: {"vendor_id": p.get("vendor_id"), "name": p["name"]} for p in products_data}
    
    # Fetch all vendors for naming
    vendors_resp = supabase.table("vendors").select("id, name").execute()
    vendors_data = vendors_resp.data or []
    vendor_names = {v["id"]: v["name"] for v in vendors_data}

    # Process Stats
    total_revenue = 0.0
    total_orders_count = 0
    unique_customer_ids = set()
    
    # Growth metrics tracking
    now = datetime.utcnow()
    # 30 day windows
    current_start = now.timestamp() - (30 * 24 * 60 * 60)
    previous_start = now.timestamp() - (60 * 24 * 60 * 60)
    
    stats_current = {"rev": 0.0, "orders": 0, "custs": set()}
    stats_prev = {"rev": 0.0, "orders": 0, "custs": set()}
    
    vendor_stats_map = defaultdict(lambda: {"revenue": 0.0, "sales": 0})
    product_stats_map = defaultdict(lambda: {"revenue": 0.0, "sales": 0, "name": ""})
    daily_stats_map = defaultdict(lambda: {"revenue": 0.0, "orders": 0})
    
    recent_orders = []

    for order in all_orders:
        created_at_str = order.get("created_at")
        if not created_at_str: continue
        
        # Convert to local date string YYYY-MM-DD and timestamp
        dt = datetime.fromisoformat(created_at_str.replace('Z', '+00:00'))
        order_ts = dt.timestamp()
        date_str = dt.strftime("%Y-%m-%d")
        
        items = order.get("items", [])
        order_vendor_items = []
        order_vendor_subtotal = 0.0
        
        for item in items:
            p_id = item.get("product_id")
            meta = product_meta.get(p_id, {})
            v_id = meta.get("vendor_id")
            
            if not v_id: continue
            
            qty = item.get("quantity", 0)
            price = item.get("price", 0)
            item_total = float(qty * price)
            
            # Global stats accumulation for super admin comparison
            vendor_stats_map[v_id]["revenue"] += item_total
            vendor_stats_map[v_id]["sales"] += qty
            
            # Filtering for specific user dashboard
            if is_super_admin or v_id == vendor_id:
                total_revenue += item_total
                product_stats_map[p_id]["revenue"] += item_total
                product_stats_map[p_id]["sales"] += qty
                product_stats_map[p_id]["name"] = meta.get("name", "Unknown")
                order_vendor_items.append(item)
                order_vendor_subtotal += item_total
                # Accumulate daily stats
                daily_stats_map[date_str]["revenue"] += item_total
                
                # Growth filtering
                if order_ts >= current_start:
                    stats_current["rev"] += item_total
                elif order_ts >= previous_start:
                    stats_prev["rev"] += item_total

        if order_vendor_items:
            # We count an order if it contains at least one relevant item
            total_orders_count += 1
            daily_stats_map[date_str]["orders"] += 1
            u_id = order.get("user_id")
            if u_id:
                unique_customer_ids.add(u_id)
                # Growth customers
                if order_ts >= current_start:
                    stats_current["custs"].add(u_id)
                elif order_ts >= previous_start:
                    stats_prev["custs"].add(u_id)

            # Growth orders
            if order_ts >= current_start:
                stats_current["orders"] += 1
            elif order_ts >= previous_start:
                stats_prev["orders"] += 1
            
            if len(recent_orders) < 5:
                # Copy order and adjust for vendor view if not super admin
                order_copy = dict(order)
                if not is_super_admin:
                    order_copy["items"] = order_vendor_items
                    order_copy["total"] = order_vendor_subtotal
                recent_orders.append(order_copy)

    # Calculate percentage changes helper
    def calc_pct(cur, prev):
        if prev == 0: return 100.0 if cur > 0 else 0.0
        return ((cur - prev) / prev) * 100.0

    rev_change = calc_pct(stats_current["rev"], stats_prev["rev"])
    orders_change = calc_pct(stats_current["orders"], stats_prev["orders"])
    custs_change = calc_pct(len(stats_current["custs"]), len(stats_prev["custs"]))
    
    # For products, we calculate how many new products were added in last 30 days vs 30 before that
    prods_current = 0
    prods_prev = 0
    for p in products_data:
        if not (is_super_admin or p.get("vendor_id") == vendor_id): continue
        p_created = p.get("created_at")
        if not p_created: continue
        p_dt = datetime.fromisoformat(p_created.replace('Z', '+00:00'))
        p_ts = p_dt.timestamp()
        
        if p_ts >= current_start:
            prods_current += 1
        elif p_ts >= previous_start:
            prods_prev += 1
    
    prods_change = calc_pct(prods_current, prods_prev)

    # Finalize vendor stats (only for super admin)
    vendor_stats = []
    if is_super_admin:
        for v_id, stats in vendor_stats_map.items():
            vendor_stats.append({
                "vendor_id": v_id,
                "vendor_name": vendor_names.get(v_id, "Unknown Vendor"),
                "total_revenue": stats["revenue"],
                "total_sales": stats["sales"]
            })
        vendor_stats.sort(key=lambda x: x["total_revenue"], reverse=True)

    # Finalize top products
    top_products_list = []
    # Sort products by revenue
    sorted_prods = sorted(product_stats_map.values(), key=lambda x: x["revenue"], reverse=True)
    for p in sorted_prods[:5]:
        top_products_list.append(TopProduct(
            name=p["name"],
            sales=p["sales"],
            revenue=p["revenue"]
        ))
        
    # Finalize daily stats (last 30 days)
    # Sort dates and return list
    sorted_dates = sorted(daily_stats_map.keys())
    # If we have too many, we could slice them, but for now we'll just return all found.
    # Usually you'd want to fill in empty days too, but let's see.
    daily_stats = []
    for d in sorted_dates:
        s = daily_stats_map[d]
        daily_stats.append(DailyStat(
            date=d,
            revenue=s["revenue"],
            orders=s["orders"]
        ))

    return AdminSummary(
        total_revenue=total_revenue,
        total_orders=total_orders_count,
        total_customers=len(unique_customer_ids),
        total_products=len([p for p in products_data if is_super_admin or p.get("vendor_id") == vendor_id]),
        revenue_change=rev_change,
        orders_change=orders_change,
        customers_change=custs_change,
        products_change=prods_change,
        recent_orders=recent_orders,
        vendor_stats=vendor_stats,
        top_products=top_products_list,
        daily_stats=daily_stats
    )


@router.get("/customers", response_model=list[AdminCustomer])
def get_admin_customers(
    supabase: Client = Depends(get_supabase_client),
    user=Depends(require_vendor_admin),
    vendor_id: str | None = Depends(get_vendor_for_user)
):
    is_super_admin = user.get("role") in ["admin", "super_admin"]
    
    # Fetch all users who are customers
    users_response = supabase.table("users").select("*").eq("user_type", "customer").execute()
    all_users = users_response.data or []

    # Fetch all orders to calculate stats
    orders_response = supabase.table("orders").select("*").execute()
    all_orders = orders_response.data or []

    # Fetch products to identify vendor items
    products_resp = supabase.table("products").select("id, vendor_id").execute()
    product_to_vendor = {p["id"]: p.get("vendor_id") for p in products_resp.data or []}

    # Calculate stats per user
    user_stats = defaultdict(lambda: {"orders": 0, "total_spent": 0.0})
    for order in all_orders:
        u_id = order.get("user_id")
        if not u_id: continue
        
        items = order.get("items", [])
        user_vendor_subtotal = 0.0
        has_vendor_item = False
        
        for item in items:
            v_id = product_to_vendor.get(item.get("product_id"))
            if is_super_admin or v_id == vendor_id:
                user_vendor_subtotal += float(item.get("price", 0) * item.get("quantity", 0))
                has_vendor_item = True
        
        if has_vendor_item:
            user_stats[u_id]["orders"] += 1
            user_stats[u_id]["total_spent"] += user_vendor_subtotal

    customers: list[AdminCustomer] = []
    for user_data in all_users:
        u_id = user_data["id"]
        # Only include customers who have purchased from the relevant vendor(s)
        if u_id not in user_stats: continue
        
        stats = user_stats[u_id]
        customers.append(
            AdminCustomer(
                user_id=u_id,
                name=user_data.get("full_name") or user_data.get("email") or "Unknown",
                phone=user_data.get("phone"),
                email=user_data.get("email"),
                orders=stats["orders"],
                total_spent=stats["total_spent"],
                joined_at=user_data.get("created_at") or datetime.utcnow(),
            )
        )

    # Sort by joined_at descending (newest first)
    customers.sort(key=lambda c: c.joined_at, reverse=True)
    return customers
