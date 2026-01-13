-- Migration: Add slug column to products table
-- Date: 2026-01-13
-- Description: Adds a 'slug' column to store URL-friendly product names
--              This is necessary because product IDs are now UUIDs instead of slugs

-- 1. Add slug column to products table
ALTER TABLE public.products 
ADD COLUMN IF NOT EXISTS slug text;

-- 2. Populate slug for existing products
-- Since existing products used their ID as slug, copy the ID to the slug field
UPDATE public.products 
SET slug = id 
WHERE slug IS NULL;

-- 3. Create an index on slug for faster lookups (optional but recommended)
CREATE INDEX IF NOT EXISTS idx_products_slug ON public.products(slug);

-- 4. Note: We intentionally do NOT add a unique constraint on slug
--    because multiple vendors might create products with similar names.
--    The UUID id remains the primary key for uniqueness.

-- After running this migration:
-- - Existing products will have their current ID copied to the slug field
-- - New products will get a UUID id and a generated slug from the product name
-- - You can update your frontend to use slug for URLs instead of id for prettier URLs
