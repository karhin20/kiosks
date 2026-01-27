from uuid import uuid4
from pathlib import Path
from fastapi import APIRouter, Depends, HTTPException, UploadFile, Query
from supabase import Client

from ..schemas.product import ProductCreate, ProductOut, ProductUpdate
from ..dependencies import (
    get_current_user,
    get_current_user_optional,
    require_admin,
    require_vendor_admin,
    get_vendor_for_user,
)
from ..supabase_client import get_supabase_client
from ..utils.logging import log_action
from ..config import get_settings

router = APIRouter(prefix="/products", tags=["products"])


def _flatten_vendor_data(products: list[dict]) -> list[dict]:
    """Extract vendor name and slug from nested vendors object."""
    for item in products:
        if item.get("vendors"):
            item["vendor_name"] = item["vendors"].get("name")
            item["vendor_slug"] = item["vendors"].get("slug")
    return products


@router.get("", response_model=list[ProductOut])
def list_products(
    vendor_id: str | None = Query(None, description="Filter products by vendor ID"),
    limit: int = Query(50, ge=1, le=100, description="Max number of products to return"),
    offset: int = Query(0, ge=0, description="Number of products to skip"),
    status: str | None = Query(None, description="Filter by status (Admin/Vendor only)"),
    supabase: Client = Depends(get_supabase_client),
    user=Depends(get_current_user_optional),
):
    """List all products with pagination. Optionally filter by vendor_id and status."""
    query = supabase.table("products").select("*, vendors(name, slug)").order("created_at", desc=True)
    
    # Permission check for status filtering
    is_admin = False
    is_vendor = False
    
    if user:
        is_admin = user.get("role") in ["admin", "super_admin"]
        is_vendor = user.get("role") == "vendor_admin"
    
    if not is_admin and not is_vendor:
        # Public users only see published products
        query = query.eq("status", "published")
    elif status:
        # Admins/Vendors can filter by status
        query = query.eq("status", status)
    
    if vendor_id:
        query = query.eq("vendor_id", vendor_id)
    
    # Apply pagination
    query = query.range(offset, offset + limit - 1)
    
    response = query.execute()
    data = response.data or []
    return _flatten_vendor_data(data)


@router.get("/flash-sales")
def get_flash_sales(supabase: Client = Depends(get_supabase_client)):
    """Get products marked as flash sale items"""
    response = supabase.table("products").select("*, vendors(name, slug)").eq("is_flash_sale", True).eq("status", "published").order("created_at", desc=True).execute()
    return _flatten_vendor_data(response.data or [])


@router.get("/best-selling")
def get_best_selling(supabase: Client = Depends(get_supabase_client)):
    """Get best selling products sorted by sales count"""
    response = supabase.table("products").select("*, vendors(name, slug)").eq("status", "published").order("sales_count", desc=True).limit(8).execute()
    return _flatten_vendor_data(response.data or [])


@router.get("/new-arrivals")
def get_new_arrivals(supabase: Client = Depends(get_supabase_client)):
    """Get featured products or recent arrivals"""
    # First try to get featured products
    response = supabase.table("products").select("*, vendors(name, slug)").eq("is_featured", True).order("created_at", desc=True).limit(4).execute()
    
    data = response.data or []
    if len(data) > 0:
        return _flatten_vendor_data(data)

    # Fallback to newest products
    response = supabase.table("products").select("*, vendors(name, slug)").order("created_at", desc=True).limit(4).execute()
    return _flatten_vendor_data(response.data or [])


@router.delete("/storage/image")
async def delete_storage_image(
    file_path: str = Query(..., description="The object key/path in Supabase storage"),
    supabase: Client = Depends(get_supabase_client),
    user=Depends(require_vendor_admin),
    vendor_id: str | None = Depends(get_vendor_for_user),
):
    """
    Delete an image from the storage bucket.
    Restricted to admins and vendor admins who own the product.
    """
    settings = get_settings()
    
    # 1. Basic path safety check
    if not file_path.startswith("products/"):
        raise HTTPException(status_code=400, detail="Access denied to this storage path")

    # 2. Ownership Check for Vendor Admins
    if user.get("role") == "vendor_admin":
        if not vendor_id:
            raise HTTPException(status_code=403, detail="Vendor admin must be assigned to a vendor")
            
        # Extract product_id from the filename (format: products/product_id-uuid.ext)
        # This assumes the naming convention is strictly followed
        try:
            filename = file_path.split("/")[-1]
            # Filename often looks like "product-slug-someuuid.jpg" 
            # or we can check if any product owns this image URL
            # Best approach: Query products table to see if any product owned by this vendor has this image
            product_search = supabase.table("products").select("id").eq("vendor_id", vendor_id).contains("images", [file_path]).execute()
            
            # If not in 'images' array, check if it's the main 'image_url'
            if not product_search.data:
                product_search = supabase.table("products").select("id").eq("vendor_id", vendor_id).eq("image_url", file_path).execute()
            
            # Simple fallback: if we can't find a direct link, but it's a vendor admin,
            # we should be careful. A more robust way is to check the prefix if product_id is predictable.
            # But searching the images array is most accurate.
            
            if not product_search.data:
                # One last check: maybe the image_url in DB is the FULL URL, but file_path is just the key
                # We'll trust the prefix check if the user is a super_admin, 
                # but for vendor_admins we REQUIRE a match in the products table.
                raise HTTPException(
                    status_code=403, 
                    detail="You do not have permission to delete this image (ownership unverified)"
                )
        except HTTPException:
            raise
        except Exception as exc:
            print(f"Error verifying image ownership: {exc}")
            raise HTTPException(status_code=500, detail="Failed to verify image ownership")

    try:
        storage = supabase.storage.from_(settings.SUPABASE_STORAGE_BUCKET)
        # Note: .remove() expects a list of paths
        response = storage.remove([file_path])
        return {"status": "success", "data": response}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to delete image: {str(exc)}")


@router.get("/{product_id}")
def get_product(product_id: str, supabase: Client = Depends(get_supabase_client)):
    response = supabase.table("products").select("*, vendors(name, slug)").eq("id", product_id).single().execute()
    if not response.data:
        raise HTTPException(status_code=404, detail="Product not found")
    return _flatten_vendor_data([response.data])[0]


@router.post("", response_model=ProductOut)
def create_product(
    payload: ProductCreate,
    supabase: Client = Depends(get_supabase_client),
    user=Depends(require_vendor_admin),
    vendor_id: str | None = Depends(get_vendor_for_user),
):
    """Create a new product. Vendor admins can only create products for their vendor."""
    # For vendor_admins, ensure they have a vendor assigned
    if user.get("role") == "vendor_admin" and not vendor_id:
        raise HTTPException(
            status_code=403,
            detail="Vendor admin must be assigned to a vendor to create products"
        )
    
    # Generate a unique ID (UUID) to prevent user-controlled ID collisions
    product_id = str(uuid4())
    # Slug is for URL readability, not the primary key
    slug = "-".join(payload.name.lower().split())
    
    product_data = {
        "id": product_id,
        "slug": slug,  # Separate field for URL-friendly identifier
        "name": payload.name,
        "description": payload.description,
        "category": payload.category,
        "price": payload.price,
        "original_price": payload.original_price,
        "is_new": payload.is_new,
        "details": payload.details,
        "images": payload.images,
        "image_url": payload.image_url or (payload.images[0] if payload.images else None),
        "is_flash_sale": payload.is_flash_sale if hasattr(payload, 'is_flash_sale') else False,
        "flash_sale_end_time": payload.flash_sale_end_time.isoformat() if payload.flash_sale_end_time else None,
        "sales_count": payload.sales_count if hasattr(payload, 'sales_count') else 0,
        "is_featured": payload.is_featured if hasattr(payload, 'is_featured') else False,
        "video_url": payload.video_url,
        "video_url": payload.video_url,
        "vendor_id": vendor_id,  # Assign to vendor
    }

    # Restrict permissions: Vendor admins cannot set flash_sale or is_featured
    if user.get("role") == "vendor_admin":
        product_data["is_flash_sale"] = False
        product_data["flash_sale_end_time"] = None
        product_data["is_featured"] = False
        product_data["status"] = "pending"  # Always pending for vendors on creation
    elif user.get("role") in ["admin", "super_admin"]:
        # Admins can set status on creation if they want, otherwise default from payload
        product_data["status"] = payload.status if hasattr(payload, 'status') else "published"

    
    try:
        # Use insert (not upsert) to ensure we're creating new records only
        response = supabase.table("products").insert(product_data).execute()
        new_prod = response.data[0] if response.data else None
        
        if new_prod:
            log_action(supabase, user, "create_product", "product", new_prod["id"], {"name": new_prod["name"]})
            
        return new_prod
    except Exception as exc:
        error_msg = str(exc).lower()
        if "duplicate" in error_msg or "already exists" in error_msg:
            raise HTTPException(status_code=400, detail="A product with this name already exists")
        raise HTTPException(status_code=500, detail=f"Failed to create product: {str(exc)}")


@router.put("/{product_id}", response_model=ProductOut)
def update_product(
    product_id: str,
    payload: ProductUpdate,
    supabase: Client = Depends(get_supabase_client),
    user=Depends(require_vendor_admin),
    vendor_id: str | None = Depends(get_vendor_for_user),
):
    """Update a product. Vendor admins can only update their own vendor's products."""
    # First, get the product to check vendor ownership
    product_response = supabase.table("products").select("vendor_id").eq("id", product_id).single().execute()
    if not product_response.data:
        raise HTTPException(status_code=404, detail="Product not found")
    
    # Check vendor ownership for vendor_admins
    if user.get("role") == "vendor_admin":
        if product_response.data.get("vendor_id") != vendor_id:
            raise HTTPException(status_code=403, detail="You can only update products from your vendor")
    # Filter out restricted fields for vendor_admin
    update_data = payload.model_dump(exclude_none=True)
    if user.get("role") == "vendor_admin":
        # Remove these keys if they exist in the payload
        update_data.pop("is_flash_sale", None)
        update_data.pop("flash_sale_end_time", None)
        update_data.pop("is_featured", None)
        # Any edit by a vendor resets status to pending
        update_data["status"] = "pending"
    elif user.get("role") in ["admin", "super_admin"]:
        # Admins can update status directly
        pass

    response = (
        supabase.table("products")
        .update(update_data)
        .eq("id", product_id)
        .execute()
    )
    if not response.data:
        raise HTTPException(status_code=404, detail="Product not found")
        
    updated_prod = response.data[0]
    log_action(supabase, user, "update_product", "product", product_id, update_data)
    
    return updated_prod


@router.delete("/{product_id}")
def delete_product(
    product_id: str,
    supabase: Client = Depends(get_supabase_client),
    user=Depends(require_vendor_admin),
    vendor_id: str | None = Depends(get_vendor_for_user),
):
    """Delete a product. Vendor admins can only delete their own vendor's products."""
    # First, get the product to check vendor ownership
    product_response = supabase.table("products").select("vendor_id").eq("id", product_id).single().execute()
    if not product_response.data:
        raise HTTPException(status_code=404, detail="Product not found")
    
    # Check vendor ownership for vendor_admins
    if user.get("role") == "vendor_admin":
        if product_response.data.get("vendor_id") != vendor_id:
            raise HTTPException(status_code=403, detail="You can only delete products from your vendor")
    
    supabase.table("products").delete().eq("id", product_id).execute()
    log_action(supabase, user, "delete_product", "product", product_id)
    return {"status": "deleted", "id": product_id}


@router.patch("/{product_id}/status", response_model=ProductOut)
def update_product_status(
    product_id: str,
    status: str = Query(..., description="New status (published, rejected, pending, draft)"),
    supabase: Client = Depends(get_supabase_client),
    user=Depends(require_admin), # Only Super Admin can moderate
):
    """Update a product status (Approve/Reject). Super Admin only."""
    response = (
        supabase.table("products")
        .update({"status": status})
        .eq("id", product_id)
        .select("*")
        .single()
        .execute()
    )
    if not response.data:
        raise HTTPException(status_code=404, detail="Product not found")
        
    log_action(supabase, user, f"set_status_{status}", "product", product_id)
    return response.data


@router.post("/{product_id}/image")
async def upload_product_image(
    product_id: str,
    file: UploadFile,
    supabase: Client = Depends(get_supabase_client),
    user=Depends(require_vendor_admin),
    vendor_id: str | None = Depends(get_vendor_for_user),
):
    """Upload product image. Vendor admins can only upload images for their vendor's products."""
    # Check vendor ownership for vendor_admins
    if user.get("role") == "vendor_admin":
        product_response = supabase.table("products").select("vendor_id").eq("id", product_id).single().execute()
        if not product_response.data:
            raise HTTPException(status_code=404, detail="Product not found")
        if product_response.data.get("vendor_id") != vendor_id:
            raise HTTPException(status_code=403, detail="You can only upload images for your vendor's products")
    settings = get_settings()
    if not file.filename:
        raise HTTPException(status_code=400, detail="File name missing")

    extension = Path(file.filename).suffix or ".jpg"
    object_key = f"products/{product_id}-{uuid4()}{extension}"
    content = await file.read()

    storage = supabase.storage.from_(settings.SUPABASE_STORAGE_BUCKET)
    try:
        storage.upload(object_key, content, {"content-type": file.content_type or "application/octet-stream"})
    except Exception as exc:  # pragma: no cover - passthrough
        raise HTTPException(status_code=500, detail="Failed to upload image") from exc

    public_url = storage.get_public_url(object_key)

    # Removed auto-update. Frontend must attach this URL to the product's images list.
    # supabase.table("products").update({"image_url": public_url}).eq("id", product_id).execute()
    
    return {"image_url": public_url}



