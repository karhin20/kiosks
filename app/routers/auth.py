from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, EmailStr, model_validator
import json
import time
from collections import defaultdict
from supabase import Client

from ..supabase_client import get_supabase_client, get_supabase_anon_client
from ..dependencies import get_current_user

router = APIRouter(prefix="/auth", tags=["auth"])

# Simple in-memory rate limiter storage
_rate_limit_storage = defaultdict(list)

def rate_limit(limit: int = 5, window: int = 60):
    """
    Very simple in-memory rate limiter.
    Defaults to 5 requests per 60 seconds per IP.
    """
    def dependency(request: Request):
        client_ip = request.client.host if request.client else "unknown"
        now = time.time()
        
        # Remove old timestamps
        _rate_limit_storage[client_ip] = [t for t in _rate_limit_storage[client_ip] if now - t < window]
        
        if len(_rate_limit_storage[client_ip]) >= limit:
            raise HTTPException(
                status_code=429, 
                detail="Too many attempts. Please try again later."
            )
        
        _rate_limit_storage[client_ip].append(now)
        return True
    
    return dependency


class AuthResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: dict


class LoginPayload(BaseModel):
    email: EmailStr
    password: str

    @model_validator(mode='before')
    @classmethod
    def parse_input(cls, v):
        if isinstance(v, bytes):
            v = v.decode("utf-8")
        if isinstance(v, str):
            try:
                return json.loads(v)
            except ValueError:
                pass
        return v


class SignupPayload(BaseModel):
    email: EmailStr
    password: str
    name: str
    phone: str | None = None

    @model_validator(mode='before')
    @classmethod
    def parse_input(cls, v):
        if isinstance(v, bytes):
            v = v.decode("utf-8")
        if isinstance(v, str):
            try:
                return json.loads(v)
            except ValueError:
                pass
        return v


class ProfileUpdatePayload(BaseModel):
    name: str | None = None
    avatar_url: str | None = None
    phone: str | None = None
    email: str | None = None # Allow updating email in profile if needed, though usually requires verification
    address: dict | None = None # Address as dict with name, phone, street, city, region

    @model_validator(mode='before')
    @classmethod
    def parse_input(cls, v):
        if isinstance(v, bytes):
            v = v.decode("utf-8")
        if isinstance(v, str):
            try:
                return json.loads(v)
            except ValueError:
                pass
        return v


@router.post("/login", response_model=AuthResponse, dependencies=[Depends(rate_limit(limit=10, window=60))])
def login(payload: LoginPayload, supabase: Client = Depends(get_supabase_anon_client)):
    try:
        res = supabase.auth.sign_in_with_password(
            {"email": payload.email, "password": payload.password}
        )
        if not res.session or not res.user:
            raise HTTPException(status_code=401, detail="Invalid credentials")

        # Fetch detailed profile from users table
        user_data = res.user.model_dump()
        try:
            profile_res = supabase.table("users").select("*").eq("id", res.user.id).single().execute()
            if profile_res.data:
                profile = profile_res.data
                # Map user_type to role in the response
                user_data["role"] = profile.get("user_type", "customer")
                user_data["name"] = profile.get("full_name") or user_data.get("user_metadata", {}).get("name")
                user_data["phone"] = profile.get("phone") or user_data.get("phone")
                user_data["favorites"] = profile.get("favorites", [])
                user_data["address"] = profile.get("address")
        except Exception:
            # Fallback to defaults if profile fetch fails
            pass

        return {
            "access_token": res.session.access_token,
            "user": user_data,
        }
    except Exception as e:
        raise HTTPException(status_code=401, detail=str(e))


@router.post("/signup", response_model=AuthResponse, dependencies=[Depends(rate_limit(limit=5, window=300))])
def signup(payload: SignupPayload, supabase: Client = Depends(get_supabase_anon_client)):
    try:
        res = supabase.auth.sign_up(
            {
                "email": payload.email,
                "password": payload.password,
                "options": {
                    "data": {
                        "name": payload.name,
                        "role": "customer",
                        "phone": payload.phone, # Pass phone to metadata
                    }
                },
            }
        )
        if not res.user:
            raise HTTPException(status_code=400, detail="Unable to sign up")

        return {
            "access_token": res.session.access_token if res.session else "",
            "user": res.user.model_dump(),
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/me")
def me(user=Depends(get_current_user)):
    return user


@router.patch("/me", response_model=dict)
def update_profile(
    payload: ProfileUpdatePayload,
    user=Depends(get_current_user),
    supabase: Client = Depends(get_supabase_client),
):
    # Update public.users directly for profile data
    public_updates = {}
    if payload.name is not None:
        public_updates["full_name"] = payload.name
    if payload.phone is not None:
        public_updates["phone"] = payload.phone
    if payload.email is not None:
        public_updates["email"] = payload.email
    if payload.address is not None:
        public_updates["address"] = payload.address

    if public_updates:
        supabase.table("users").update(public_updates).eq("id", user["id"]).execute()

    # Return updated user dict
    updated_user = user.copy()
    if payload.name: 
        updated_user["name"] = payload.name
    if payload.phone: 
        updated_user["phone"] = payload.phone
    if payload.email: 
        updated_user["email"] = payload.email
    if payload.address is not None:
        updated_user["address"] = payload.address
    # Preserve created_at from original user object
    if "created_at" in user:
        updated_user["created_at"] = user["created_at"]
    
    return {"user": updated_user}


class ToggleFavoritePayload(BaseModel):
    product_id: str


@router.post("/favorites", response_model=list[str])
def toggle_favorite(
    payload: ToggleFavoritePayload,
    user=Depends(get_current_user),
    supabase: Client = Depends(get_supabase_client),
):
    """
    Toggles a product_id in the user's favorites list.
    Returns the updated list of favorites.
    """
    current_favorites = user.get("favorites", []) or []
    
    # Ensure it's a list (in case of None)
    if not isinstance(current_favorites, list):
        current_favorites = []
        
    pid = payload.product_id
    
    if pid in current_favorites:
        current_favorites.remove(pid)
    else:
        current_favorites.append(pid)
        
    # Update database
    supabase.table("users").update({"favorites": current_favorites}).eq("id", user["id"]).execute()
    
    return current_favorites


@router.get("/google-url")
def get_google_auth_url(supabase: Client = Depends(get_supabase_anon_client)):
    """
    Returns the Google OAuth URL for signing in.
    Redirects back to the frontend application after successful login.
    """
    from ..config import get_settings
    settings = get_settings()
    
    try:
        redirect_to = settings.OAUTH_REDIRECT_URL
        
        res = supabase.auth.get_url_for_provider(
            provider="google",
            redirect_to=redirect_to,
            scopes=["email", "profile"]
        )
        return {"url": res}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


class RefreshTokenPayload(BaseModel):
    refresh_token: str


@router.post("/refresh", response_model=AuthResponse)
def refresh_token(payload: RefreshTokenPayload, supabase: Client = Depends(get_supabase_anon_client)):
    """
    Refreshes the access token using the refresh token.
    """
    try:
        res = supabase.auth.refresh_session(payload.refresh_token)
        
        if not res.session or not res.user:
            raise HTTPException(status_code=401, detail="Invalid refresh token")

        # Fetch detailed profile from users table
        user_data = res.user.model_dump()
        try:
            profile_res = supabase.table("users").select("*").eq("id", res.user.id).single().execute()
            if profile_res.data:
                profile = profile_res.data
                user_data["role"] = profile.get("user_type", "customer")
                user_data["name"] = profile.get("full_name") or user_data.get("user_metadata", {}).get("name")
                user_data["phone"] = profile.get("phone") or user_data.get("phone")
                user_data["favorites"] = profile.get("favorites", [])
                user_data["address"] = profile.get("address")
        except Exception:
            pass

        return {
            "access_token": res.session.access_token,
            "user": user_data,
            # We might want to return the new refresh token too if it rotates
        }
    except Exception as e:
        raise HTTPException(status_code=401, detail=str(e))


@router.delete("/me", status_code=204)
def delete_account(
    user=Depends(get_current_user),
    supabase: Client = Depends(get_supabase_client),
):
    """
    Permanently delete the current user's account.
    """
    user_id = user["id"]
    
    try:
        # Delete from auth.users (requires service role key)
        # We use supabase.auth.admin.delete_user(user_id) 
        # Note: Depending on the library version, it might be supabase.auth.admin.delete_user
        
        # The supabase-py client (gotrue) exposes admin interface
        res = supabase.auth.admin.delete_user(user_id)
        
        # Optionally, we could manually delete from public.users if CASCADE isn't set up
        # supabase.table("users").delete().eq("id", user_id).execute()
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to delete account: {str(e)}")

    return None
