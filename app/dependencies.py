from fastapi import Depends, HTTPException, Security
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from supabase import Client
from .supabase_client import get_supabase_client

security = HTTPBearer(auto_error=False)


def get_current_user(
    credentials: HTTPAuthorizationCredentials = Security(security),
    supabase: Client = Depends(get_supabase_client),
):
    """
    Validates the incoming Supabase access token and returns the user object.
    """
    if credentials is None:
        raise HTTPException(status_code=401, detail="Missing authorization header")

    token = credentials.credentials
    try:
        # Use anon key to verify the user token
        auth_client = supabase.auth
        user_response = auth_client.get_user(token)
    except Exception as exc:  # pragma: no cover - passthrough
        raise HTTPException(status_code=401, detail="Session expired. Please sign in again.") from exc

    if not user_response or not user_response.user:
        raise HTTPException(status_code=401, detail="Session expired. Please sign in again.")

    supa_user = user_response.user
    
    # Fetch public profile data (e.g. favorites)
    # We use a try/except or check for data because the trigger might have failed case (rare)
    # or if we haven't run migration yet, this might fail.
    # Ideally schema is applied.
    # Fetch public profile data
    profile_data = {}
    favorites = []
    
    try:
        profile_res = supabase.table("users").select("*").eq("id", supa_user.id).single().execute()
        if profile_res.data:
            profile_data = profile_res.data
            favorites = profile_data.get("favorites", []) or []
    except Exception:
        pass

    return {
        "id": supa_user.id,
        "email": supa_user.email, # Keep email from auth as source of truth for now, or use profile_data.get('email')
        "phone": profile_data.get("phone") or supa_user.phone, # Prefer profile phone
        "name": profile_data.get("full_name") or (supa_user.user_metadata or {}).get("name") or "", # Prefer profile name
        "role": profile_data.get("user_type", "customer"),  # Use user_type from database as source of truth
        "favorites": favorites,
        "created_at": profile_data.get("created_at") or supa_user.created_at,
        "address": profile_data.get("address"), # Address stored as JSONB
    }


def get_current_user_optional(
    credentials: HTTPAuthorizationCredentials | None = Security(security),
    supabase: Client = Depends(get_supabase_client),
):
    """
    Returns the user object if authenticated, otherwise returns None.
    Does NOT raise 401.
    """
    if credentials is None:
        return None

    token = credentials.credentials
    try:
        # Use anon key to verify the user token
        auth_client = supabase.auth
        user_response = auth_client.get_user(token)
    except Exception:
        return None

    if not user_response or not user_response.user:
        return None

    supa_user = user_response.user
    
    # Fetch public profile data
    profile_data = {}
    favorites = []
    
    try:
        profile_res = supabase.table("users").select("*").eq("id", supa_user.id).single().execute()
        if profile_res.data:
            profile_data = profile_res.data
            favorites = profile_data.get("favorites", []) or []
    except Exception:
        pass

    return {
        "id": supa_user.id,
        "email": supa_user.email,
        "phone": profile_data.get("phone") or supa_user.phone,
        "name": profile_data.get("full_name") or (supa_user.user_metadata or {}).get("name") or "",
        "role": profile_data.get("user_type", "customer"),
        "favorites": favorites,
        "created_at": profile_data.get("created_at") or supa_user.created_at,
        "address": profile_data.get("address"),
    }


def require_admin(user=Depends(get_current_user)):
    """Requires user to be super_admin (legacy admin role)"""
    if user.get("role") not in ["admin", "super_admin"]:
        raise HTTPException(status_code=403, detail="Admin privileges required")
    return user


def require_super_admin(user=Depends(get_current_user)):
    """Requires user to be super_admin ONLY (highest privilege level)"""
    if user.get("role") != "super_admin":
        raise HTTPException(status_code=403, detail="Super admin privileges required")
    return user


def require_vendor_admin(user=Depends(get_current_user)):
    """Requires user to be vendor_admin or super_admin"""
    if user.get("role") not in ["admin", "super_admin", "vendor_admin"]:
        raise HTTPException(status_code=403, detail="Vendor admin privileges required")
    return user


def get_vendor_for_user(
    user=Depends(get_current_user),
    supabase: Client = Depends(get_supabase_client),
) -> str | None:
    """
    Gets the vendor_id associated with the current vendor_admin user.
    Returns None if user is not a vendor_admin or has no vendor assigned.
    Super admins return None (they can access all vendors).
    """
    if user.get("role") in ["admin", "super_admin"]:
        return None  # Super admins can access all vendors
    
    if user.get("role") != "vendor_admin":
        return None
    
    # Query vendor_admins table to find vendor for this user
    try:
        response = (
            supabase.table("vendor_admins")
            .select("vendor_id")
            .eq("user_id", user["id"])
            .limit(1)
            .execute()
        )
        if response.data and len(response.data) > 0:
            return response.data[0]["vendor_id"]
    except Exception:
        pass
    
    return None


def require_vendor_ownership(
    vendor_id: str,
    user=Depends(get_current_user),
    supabase: Client = Depends(get_supabase_client),
):
    """
    Ensures that the current user has access to the specified vendor.
    Super admins can access any vendor.
    Vendor admins can only access their own vendor.
    """
    if user.get("role") in ["admin", "super_admin"]:
        return user  # Super admins can access any vendor
    
    if user.get("role") != "vendor_admin":
        raise HTTPException(status_code=403, detail="Vendor admin privileges required")
    
    # Check if user is admin of this vendor
    try:
        response = (
            supabase.table("vendor_admins")
            .select("*")
            .eq("vendor_id", vendor_id)
            .eq("user_id", user["id"])
            .execute()
        )
        if not response.data or len(response.data) == 0:
            raise HTTPException(status_code=403, detail="You don't have access to this vendor")
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail="Failed to verify vendor ownership") from exc
    
    return user

