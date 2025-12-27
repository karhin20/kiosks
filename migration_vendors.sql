-- =====================================================
-- Multi-Vendor System Migration
-- =====================================================
-- This migration adds support for multiple vendors with their own admins
-- and associates products with specific vendors.

-- 1. Create vendors table
-- =====================================================
CREATE TABLE IF NOT EXISTS public.vendors (
  id uuid DEFAULT gen_random_uuid() PRIMARY KEY,
  name text NOT NULL,
  description text,
  logo_url text,
  banner_url text,
  contact_email text,
  contact_phone text,
  address jsonb,
  is_active boolean DEFAULT true,
  created_at timestamp with time zone DEFAULT timezone('utc'::text, now()) NOT NULL,
  updated_at timestamp with time zone DEFAULT timezone('utc'::text, now()) NOT NULL
);

-- Enable RLS on vendors table
ALTER TABLE public.vendors ENABLE ROW LEVEL SECURITY;

-- Policy: Everyone can view active vendors
CREATE POLICY "Active vendors are viewable by everyone"
  ON public.vendors FOR SELECT
  USING (is_active = true);

-- Policy: Only authenticated users can view all vendors (including inactive)
CREATE POLICY "Authenticated users can view all vendors"
  ON public.vendors FOR SELECT
  USING (auth.uid() IS NOT NULL);

-- Policy: Only super admins can insert vendors
CREATE POLICY "Super admins can insert vendors"
  ON public.vendors FOR INSERT
  WITH CHECK (
    EXISTS (
      SELECT 1 FROM public.users
      WHERE id = auth.uid() AND user_type = 'super_admin'
    )
  );

-- Policy: Super admins and vendor admins can update their vendor
CREATE POLICY "Admins can update vendors"
  ON public.vendors FOR UPDATE
  USING (
    EXISTS (
      SELECT 1 FROM public.users
      WHERE id = auth.uid() AND user_type = 'super_admin'
    )
    OR
    EXISTS (
      SELECT 1 FROM public.vendor_admins
      WHERE vendor_id = vendors.id AND user_id = auth.uid()
    )
  );

-- 2. Create vendor_admins junction table
-- =====================================================
CREATE TABLE IF NOT EXISTS public.vendor_admins (
  vendor_id uuid REFERENCES public.vendors(id) ON DELETE CASCADE,
  user_id uuid REFERENCES public.users(id) ON DELETE CASCADE,
  created_at timestamp with time zone DEFAULT timezone('utc'::text, now()) NOT NULL,
  PRIMARY KEY (vendor_id, user_id)
);

-- Enable RLS on vendor_admins table
ALTER TABLE public.vendor_admins ENABLE ROW LEVEL SECURITY;

-- Policy: Users can view their own vendor admin relationships
CREATE POLICY "Users can view their vendor admin relationships"
  ON public.vendor_admins FOR SELECT
  USING (user_id = auth.uid() OR EXISTS (
    SELECT 1 FROM public.users
    WHERE id = auth.uid() AND user_type = 'super_admin'
  ));

-- Policy: Only super admins can manage vendor admin assignments
CREATE POLICY "Super admins can manage vendor admins"
  ON public.vendor_admins FOR ALL
  USING (
    EXISTS (
      SELECT 1 FROM public.users
      WHERE id = auth.uid() AND user_type = 'super_admin'
    )
  );

-- 3. Add vendor_id to products table
-- =====================================================
ALTER TABLE public.products 
ADD COLUMN IF NOT EXISTS vendor_id uuid REFERENCES public.vendors(id) ON DELETE SET NULL;

-- Create index for better query performance
CREATE INDEX IF NOT EXISTS idx_products_vendor_id ON public.products(vendor_id);

-- 4. Create default "Platform" vendor for existing products
-- =====================================================
INSERT INTO public.vendors (id, name, description, is_active)
VALUES (
  '00000000-0000-0000-0000-000000000001',
  'Lampo Platform',
  'Official Lampo platform products',
  true
)
ON CONFLICT (id) DO NOTHING;

-- 5. Assign existing products to default vendor
-- =====================================================
UPDATE public.products
SET vendor_id = '00000000-0000-0000-0000-000000000001'
WHERE vendor_id IS NULL;

-- 6. Update user_type values (migrate admin to super_admin)
-- =====================================================
-- First, update existing admin users to super_admin
UPDATE public.users
SET user_type = 'super_admin'
WHERE user_type = 'admin';

-- 7. Add updated_at trigger for vendors table
-- =====================================================
CREATE OR REPLACE FUNCTION public.update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = timezone('utc'::text, now());
    RETURN NEW;
END;
$$ language 'plpgsql';

CREATE TRIGGER update_vendors_updated_at
    BEFORE UPDATE ON public.vendors
    FOR EACH ROW
    EXECUTE FUNCTION public.update_updated_at_column();

-- 8. Create helper function to get vendor for user
-- =====================================================
CREATE OR REPLACE FUNCTION public.get_vendor_for_user(user_uuid uuid)
RETURNS uuid AS $$
DECLARE
  vendor_uuid uuid;
BEGIN
  SELECT vendor_id INTO vendor_uuid
  FROM public.vendor_admins
  WHERE user_id = user_uuid
  LIMIT 1;
  
  RETURN vendor_uuid;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

-- =====================================================
-- Migration Complete
-- =====================================================
-- Summary of changes:
-- 1. Created vendors table with RLS policies
-- 2. Created vendor_admins junction table
-- 3. Added vendor_id column to products table
-- 4. Created default "Lampo Platform" vendor
-- 5. Assigned existing products to default vendor
-- 6. Migrated 'admin' user_type to 'super_admin'
-- 7. Added updated_at trigger for vendors
-- 8. Created helper function to get vendor for user
