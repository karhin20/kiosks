from uuid import uuid4
from pathlib import Path
from fastapi import APIRouter, Depends, HTTPException, UploadFile, Query
from supabase import Client

from ..schemas.product import ProductCreate, ProductOut, ProductUpdate
from ..dependencies import (
    get_current_user,
    require_admin,
    require_vendor_admin,
    get_vendor_for_user,
)
from ..supabase_client import get_supabase_client
from ..config import get_settings

router = APIRouter(prefix="/products", tags=["products"])


@router.get("", response_model=list[ProductOut])
def list_products(
    vendor_id: str | None = Query(None, description="Filter products by vendor ID"),
    supabase: Client = Depends(get_supabase_client),
):
    """List all products. Optionally filter by vendor_id."""
    query = supabase.table("products").select("*").order("created_at", desc=True)
    
    if vendor_id:
        query = query.eq("vendor_id", vendor_id)
    
    response = query.execute()
    return response.data or []


@router.get("/flash-sales")
def get_flash_sales(supabase: Client = Depends(get_supabase_client)):
    """Get products marked as flash sale items"""
    response = supabase.table("products").select("*").eq("is_flash_sale", True).order("created_at", desc=True).execute()
    return response.data or []


@router.get("/best-selling")
def get_best_selling(supabase: Client = Depends(get_supabase_client)):
    """Get best selling products sorted by sales count"""
    response = supabase.table("products").select("*").order("sales_count", desc=True).limit(8).execute()
    return response.data or []


@router.get("/new-arrivals")
def get_new_arrivals(supabase: Client = Depends(get_supabase_client)):
    """Get featured products or recent arrivals"""
    # First try to get featured products
    response = supabase.table("products").select("*").eq("is_featured", True).order("created_at", desc=True).limit(4).execute()
    if response.data and len(response.data) > 0:
        return response.data
    # Fallback to newest products
    response = supabase.table("products").select("*").order("created_at", desc=True).limit(4).execute()
    return response.data or []


@router.delete("/storage/image")
async def delete_storage_image(
    file_path: str = Query(..., description="The object key/path in Supabase storage"),
    supabase: Client = Depends(get_supabase_client),
    user=Depends(require_vendor_admin),
):
    """
    Delete an image from the storage bucket.
    Restricted to admins and vendor admins.
    """
    settings = get_settings()
    
    # Basic path safety check
    if not file_path.startswith("products/"):
        raise HTTPException(status_code=400, detail="Access denied to this storage path")

    try:
        storage = supabase.storage.from_(settings.SUPABASE_STORAGE_BUCKET)
        # Note: .remove() expects a list of paths
        response = storage.remove([file_path])
        return {"status": "success", "data": response}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to delete image: {str(exc)}")


@router.get("/{product_id}")
def get_product(product_id: str, supabase: Client = Depends(get_supabase_client)):
    response = supabase.table("products").select("*").eq("id", product_id).single().execute()
    if not response.data:
        raise HTTPException(status_code=404, detail="Product not found")
    return response.data


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
    
    slug = "-".join(payload.name.lower().split())
    product_data = {
        "id": slug,
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
        "sales_count": payload.sales_count if hasattr(payload, 'sales_count') else 0,
        "is_featured": payload.is_featured if hasattr(payload, 'is_featured') else False,
        "vendor_id": vendor_id,  # Assign to vendor
    }
    response = (
        supabase.table("products")
        .upsert(product_data, on_conflict="id")
        .execute()
    )
    return response.data[0] if response.data else None


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
    
    response = (
        supabase.table("products")
        .update(payload.model_dump(exclude_none=True))
        .eq("id", product_id)
        .execute()
    )
    if not response.data:
        raise HTTPException(status_code=404, detail="Product not found")
    return response.data[0]


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
    return {"status": "deleted", "id": product_id}


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



