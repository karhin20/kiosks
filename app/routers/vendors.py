from fastapi import APIRouter, Depends, HTTPException, Query
from supabase import Client

from ..schemas.vendor import VendorCreate, VendorOut, VendorUpdate
from ..schemas.product import ProductOut
from ..dependencies import (
    get_current_user,
    require_super_admin,
    require_vendor_admin,
    require_vendor_ownership,
)
from ..supabase_client import get_supabase_client
from ..utils.logging import log_action

router = APIRouter(prefix="/vendors", tags=["vendors"])


@router.get("", response_model=list[VendorOut])
def list_vendors(
    active_only: bool = Query(True, description="Filter to only active vendors"),
    supabase: Client = Depends(get_supabase_client),
):
    """List all vendors. By default shows only active vendors."""
    query = supabase.table("vendors").select("*").order("created_at", desc=True)
    
    if active_only:
        query = query.eq("is_active", True)
    
    response = query.execute()
    return response.data or []


@router.get("/me", response_model=VendorOut | None)
def get_my_vendor(
    user=Depends(get_current_user),
    supabase: Client = Depends(get_supabase_client),
):
    """Get the vendor associated with the current vendor_admin user."""
    # Super admins don't have a specific vendor
    if user.get("role") in ["admin", "super_admin"]:
        return None
    
    # Get vendor for vendor_admin
    if user.get("role") == "vendor_admin":
        vendor_admin_response = (
            supabase.table("vendor_admins")
            .select("vendor_id")
            .eq("user_id", user["id"])
            .limit(1)
            .execute()
        )
        
        if vendor_admin_response.data and len(vendor_admin_response.data) > 0:
            vendor_id = vendor_admin_response.data[0]["vendor_id"]
            vendor_response = supabase.table("vendors").select("*").eq("id", vendor_id).single().execute()
            if vendor_response.data:
                return vendor_response.data
    
    return None



@router.get("/{vendor_identifier}", response_model=VendorOut)
def get_vendor(vendor_identifier: str, supabase: Client = Depends(get_supabase_client)):
    """Get a specific vendor by ID or slug."""
    # Try to find by slug first (more user-friendly)
    response = supabase.table("vendors").select("*").eq("slug", vendor_identifier).execute()
    
    # If not found by slug, try by ID (for backwards compatibility)
    if not response.data or len(response.data) == 0:
        response = supabase.table("vendors").select("*").eq("id", vendor_identifier).execute()
    
    if not response.data or len(response.data) == 0:
        raise HTTPException(status_code=404, detail="Vendor not found")
    
    return response.data[0]


@router.get("/{vendor_identifier}/products", response_model=list[ProductOut])
def get_vendor_products(
    vendor_identifier: str,
    supabase: Client = Depends(get_supabase_client),
):
    """Get all products for a specific vendor by ID or slug."""
    # Try to find vendor by slug first, then by ID
    vendor_response = supabase.table("vendors").select("id").eq("slug", vendor_identifier).execute()
    
    if not vendor_response.data or len(vendor_response.data) == 0:
        vendor_response = supabase.table("vendors").select("id").eq("id", vendor_identifier).execute()
    
    if not vendor_response.data or len(vendor_response.data) == 0:
        raise HTTPException(status_code=404, detail="Vendor not found")
    
    vendor_id = vendor_response.data[0]["id"]
    
    # Get published products for this vendor (public endpoint only shows published)
    response = (
        supabase.table("products")
        .select("*")
        .eq("vendor_id", vendor_id)
        .eq("status", "published")
        .order("created_at", desc=True)
        .execute()
    )
    return response.data or []

@router.post("", response_model=VendorOut)
def create_vendor(
    payload: VendorCreate,
    supabase: Client = Depends(get_supabase_client),
    user=Depends(require_super_admin)
):
    """Create a new vendor. Only super admins can create vendors."""
    vendor_data = payload.model_dump()
    
    response = supabase.table("vendors").insert(vendor_data).execute()
    
    if not response.data:
        raise HTTPException(status_code=500, detail="Failed to create vendor")
    
    new_vendor = response.data[0]
    log_action(supabase, user, "create_vendor", "vendor", new_vendor["id"], {"name": new_vendor["name"]})
    
    return new_vendor


@router.put("/{vendor_id}", response_model=VendorOut)
def update_vendor(
    vendor_id: str,
    payload: VendorUpdate,
    supabase: Client = Depends(get_supabase_client),
    user=Depends(require_vendor_ownership),
):
    """
    Update a vendor. Super admins can update any vendor.
    Vendor admins can only update their own vendor.
    """
    update_data = payload.model_dump(exclude_none=True)
    
    if not update_data:
        raise HTTPException(status_code=400, detail="No fields to update")
    
    response = (
        supabase.table("vendors")
        .update(update_data)
        .eq("id", vendor_id)
        .execute()
    )
    
    updated_vendor = response.data[0]
    log_action(supabase, user, "update_vendor", "vendor", vendor_id, update_data)
    
    return updated_vendor


@router.delete("/{vendor_id}")
def delete_vendor(
    vendor_id: str, 
    supabase: Client = Depends(get_supabase_client),
    user=Depends(require_super_admin)
):
    """
    Deactivate a vendor (soft delete). Only super admins can deactivate vendors.
    This sets is_active to false rather than deleting the record.
    """
    response = (
        supabase.table("vendors")
        .update({"is_active": False})
        .eq("id", vendor_id)
        .execute()
    )
    
    if not response.data:
        raise HTTPException(status_code=404, detail="Vendor not found")
    
    log_action(supabase, user, "deactivate_vendor", "vendor", vendor_id)
    return {"status": "deactivated", "id": vendor_id}


@router.post("/{vendor_id}/admins")
def assign_vendor_admin(
    vendor_id: str,
    user_id: str = Query(..., description="User ID to assign as vendor admin"),
    supabase: Client = Depends(get_supabase_client),
    user=Depends(require_super_admin)
):
    """
    Assign a user as admin for a vendor. Only super admins can assign vendor admins.
    This also updates the user's role to vendor_admin if not already.
    """
    # Verify vendor exists
    vendor_response = supabase.table("vendors").select("id").eq("id", vendor_id).single().execute()
    if not vendor_response.data:
        raise HTTPException(status_code=404, detail="Vendor not found")
    
    # Verify user exists
    user_response = supabase.table("users").select("id, user_type").eq("id", user_id).single().execute()
    if not user_response.data:
        raise HTTPException(status_code=404, detail="User not found")
    
    # Update user role to vendor_admin if not already admin
    if user_response.data["user_type"] not in ["admin", "super_admin", "vendor_admin"]:
        supabase.table("users").update({"user_type": "vendor_admin"}).eq("id", user_id).execute()
    
    # Create vendor_admin relationship
    try:
        response = supabase.table("vendor_admins").insert({
            "vendor_id": vendor_id,
            "user_id": user_id,
        }).execute()
        
        log_action(supabase, user, "assign_vendor_admin", "vendor", vendor_id, {"target_user_id": user_id})
        return {"status": "assigned", "vendor_id": vendor_id, "user_id": user_id}
    except Exception as exc:
        # Check if already assigned
        if "duplicate key" in str(exc).lower():
            raise HTTPException(status_code=400, detail="User is already admin of this vendor")
        raise HTTPException(status_code=500, detail="Failed to assign vendor admin") from exc


@router.delete("/{vendor_id}/admins/{user_id}")
def remove_vendor_admin(
    vendor_id: str,
    user_id: str,
    supabase: Client = Depends(get_supabase_client),
    user=Depends(require_super_admin)
):
    """Remove a user from being admin of a vendor. Only super admins can remove vendor admins."""
    response = (
        supabase.table("vendor_admins")
        .delete()
        .eq("vendor_id", vendor_id)
        .eq("user_id", user_id)
        .execute()
    )
    
    log_action(supabase, user, "remove_vendor_admin", "vendor", vendor_id, {"target_user_id": user_id})
    return {"status": "removed", "vendor_id": vendor_id, "user_id": user_id}


@router.get("/{vendor_id}/admins")
def list_vendor_admins(
    vendor_id: str,
    supabase: Client = Depends(get_supabase_client),
    user=Depends(require_vendor_ownership),
):
    """
    List all admins for a vendor. Super admins can view any vendor's admins.
    Vendor admins can only view admins of their own vendor.
    """
    # Get vendor_admin relationships
    response = (
        supabase.table("vendor_admins")
        .select("user_id, created_at")
        .eq("vendor_id", vendor_id)
        .execute()
    )
    
    if not response.data:
        return []
    
    # Get user details for each admin
    user_ids = [item["user_id"] for item in response.data]
    users_response = (
        supabase.table("users")
        .select("id, email, full_name, user_type")
        .in_("id", user_ids)
        .execute()
    )
    
    return users_response.data or []
