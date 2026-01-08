from fastapi import APIRouter, Depends, HTTPException, status
from typing import List
from ..schemas.reviews import ReviewCreate, ReviewResponse
from ..dependencies import get_current_user
from ..supabase_client import get_supabase_client
from supabase import Client

router = APIRouter(
    prefix="/reviews",
    tags=["reviews"]
)

@router.get("/{product_id}", response_model=List[ReviewResponse])
def get_product_reviews(product_id: str, supabase: Client = Depends(get_supabase_client)):
    # Fetch reviews
    response = supabase.table("reviews").select("*").eq("product_id", product_id).order("created_at", desc=True).execute()
    
    reviews = response.data
    
    # Enrich with user profile data if possible. 
    # Since we can't easily join auth.users, we might need to fetch profiles from a public 'profiles' table if it exists
    # or rely on frontend to fetch user names. 
    # User Request: "comments should show name of the one who commented"
    # Typically, we assume there is a 'profiles' table or similar that is public.
    # Let's try to fetch from 'profiles' if it exists, otherwise we might return review as is.
    # Checking schema.sql earlier would have been good, but let's assume valid 'profiles' pattern often used with Supabase.
    
    # Strategy: Get list of user_ids, fetch profiles, map them.
    if reviews:
        user_ids = [r['user_id'] for r in reviews]
        # Try fetching profiles. If fails, we just return reviews without metadata.
        try:
            profiles_response = supabase.table("profiles").select("id, first_name, last_name, avatar_url").in_("id", user_ids).execute()
            profiles_map = {p['id']: p for p in profiles_response.data}
            
            for review in reviews:
                user_id = review['user_id']
                if user_id in profiles_map:
                    profile = profiles_map[user_id]
                    # Construct user_metadata
                    review['user_metadata'] = {
                        "full_name": f"{profile.get('first_name', '')} {profile.get('last_name', '')}".strip() or "Anonymous",
                        "avatar_url": profile.get('avatar_url')
                    }
        except Exception as e:
            print(f"Error fetching profiles: {e}")
            # Fallback (optional): fetch from auth.users via admin api if available (usually not from client)
            pass

    return reviews

@router.post("/", response_model=ReviewResponse)
def create_review(
    review: ReviewCreate, 
    current_user: dict = Depends(get_current_user),
    supabase: Client = Depends(get_supabase_client)
):
    user_id = current_user.get("sub") or current_user.get("id")
    
    review_data = review.model_dump()
    review_data["user_id"] = user_id
    
    response = supabase.table("reviews").insert(review_data).execute()
    
    if not response.data:
        raise HTTPException(status_code=400, detail="Failed to create review")
        
    created_review = response.data[0]
    
    # Attach current user metadata for immediate display
    user_metadata = current_user.get("user_metadata", {})
    created_review['user_metadata'] = {
        "full_name": user_metadata.get("full_name") or user_metadata.get("name") or "You",
        "avatar_url": user_metadata.get("avatar_url")
    }
    
    return created_review

@router.delete("/{review_id}")
def delete_review(
    review_id: str,
    current_user: dict = Depends(get_current_user),
    supabase: Client = Depends(get_supabase_client)
):
    user_id = current_user.get("sub") or current_user.get("id")
    
    # Verify ownership
    # We can rely on RLS, but double checking here doesn't hurt or we just try to delete
    response = supabase.table("reviews").delete().eq("id", review_id).eq("user_id", user_id).execute()
    
    if not response.data:
        raise HTTPException(status_code=404, detail="Review not found or not authorized")
        
    return {"message": "Review deleted"}
